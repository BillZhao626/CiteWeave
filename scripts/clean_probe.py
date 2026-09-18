"""Fresh-database and original-PDF smoke checks used by the clean install rehearsal."""

import argparse
import json
import time
from uuid import uuid4

import httpx
from sqlalchemy import text

from citeweave.db import engine
from citeweave.evidence import EvidenceSpan, resolve_span
from citeweave.parsing import parse_simple_pdf
from citeweave.settings import ROOT, settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--before-migration", action="store_true")
    args = parser.parse_args()
    report = ROOT / ".runtime/clean-probe.json"
    if args.before_migration:
        with engine().connect() as connection:
            count = connection.scalar(
                text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
            )
        assert count == 0, "clean_database_not_empty"
        report.write_text(json.dumps(dict(tables_before_migration=count)), encoding="utf-8")
        print("Confirmed empty public schema before startup")
        return
    value = json.loads(report.read_text(encoding="utf-8"))
    with engine().connect() as connection:
        value["migration_head"] = connection.scalar(text("SELECT version_num FROM alembic_version"))
    assert value["migration_head"] == "0004"
    headers = {"Authorization": "Bearer " + settings().admin_token.get_secret_value()}
    with httpx.Client(base_url="http://127.0.0.1:18080", headers=headers, timeout=60, trust_env=False) as api:
        assert api.get("/health/ready").status_code == 200
        assert api.get("/v1/knowledge-bases").json() == [], "clean_workspace_not_empty"
        response = api.post(
            "/v1/knowledge-bases",
            json={"name": "Clean install · 原创手册"},
            headers={"Idempotency-Key": str(uuid4())},
        )
        response.raise_for_status()
        kb = response.json()["id"]
        original = ROOT / "apps/web/public/original-handbook.pdf"
        response = api.post(
            f"/v1/knowledge-bases/{kb}/documents",
            params={"filename": "original-handbook.pdf", "license": "original"},
            content=original.read_bytes(),
            headers={"Idempotency-Key": str(uuid4()), "Content-Type": "application/pdf"},
        )
        response.raise_for_status()
        job = response.json()["job"]["id"]
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            state = api.get("/v1/jobs/" + job).json()
            if state["status"] == "READY":
                break
            assert state["status"] != "FAILED_FINAL", "clean_ingestion_failed"
            time.sleep(1)
        else:
            raise TimeoutError("clean_ingestion_deadline")
        response = api.post(
            "/v1/queries",
            json={"kb_id": kb, "question": "湖畔观测站的温度传感器多久采样一次，原始数据保留多久？"},
            headers={"Idempotency-Key": str(uuid4())},
        )
        response.raise_for_status()
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        assert events[-1]["type"] == "final", "clean_query_not_final"
        answer = events[-1]["answer"]
        assert "30" in answer["text"] and "7" in answer["text"] and answer["citations"]
        for citation in answer["citations"]:
            assert api.get(citation["content_url"]).content == original.read_bytes()
            span = EvidenceSpan.model_validate(citation["span"])
            blocks = {b.block_id: b for b in parse_simple_pdf(original, span.scope)}
            assert resolve_span(span, blocks[span.block_id], span.scope) == span.quote
            resolved = api.get("/v1/evidence/" + citation["evidence_id"], params={"run_id": answer["run_id"]})
            assert resolved.status_code == 200 and resolved.json()["span"] == citation["span"]
        trace = api.get("/v1/runs/" + answer["run_id"]).json()
        assert trace["runtime_config"]["query_profile"] == "m3-context"
        value.update(
            status="PASS",
            kb_id=kb,
            query_run_id=answer["run_id"],
            answer=answer["text"],
            physical_citations=len(answer["citations"]),
            estimated_yuan=answer["estimated_yuan"],
            actual_charge="unavailable",
            default_profile="m3-context",
        )
    report.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Fresh migration, original PDF ingestion, real answer and physical citations passed")


if __name__ == "__main__":
    main()
