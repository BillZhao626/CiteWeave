"""Ingest the frozen local public corpus only after Dev-only selection is frozen."""

import hashlib
import json
import time

import httpx

from citeweave.evaluation.dataset import load_dataset
from citeweave.evaluation.holdout import HOLDOUT_ID, require_selection
from citeweave.settings import ROOT, settings


def main():
    require_selection("m3-context", "judge-v4", "test")
    dataset, digest = load_dataset(HOLDOUT_ID)
    folder = ROOT / ".runtime/evaluation/holdout-corpus"
    headers = {"Authorization": "Bearer " + settings().admin_token.get_secret_value()}
    with httpx.Client(base_url="http://127.0.0.1:18080", headers=headers, timeout=30, trust_env=False) as api:
        response = api.post(
            "/v1/knowledge-bases",
            json=dict(
                name="公开协议 · M3 冻结 Holdout",
                description="Three new official RFC text sources, locally rendered PDFs; AI-authored frozen Gold, not independent human annotation.",
            ),
            headers={"Idempotency-Key": "m3-holdout-" + digest},
        )
        response.raise_for_status()
        kb = response.json()["id"]
        versions, pending = {}, []
        for source in dataset["sources"]:
            raw = (folder / source["filename"]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != source["sha256"]:
                raise ValueError("holdout_source_integrity_mismatch")
            response = api.post(
                f"/v1/knowledge-bases/{kb}/documents",
                params={"filename": source["filename"], "license": "permission-held"},
                content=raw,
                headers={"Content-Type": "application/pdf", "Idempotency-Key": source["sha256"]},
            )
            response.raise_for_status()
            value = response.json()
            versions[source["source_id"]] = value["version"]["id"]
            pending.append(value["job"]["id"])
        deadline = time.monotonic() + 900
        while pending and time.monotonic() < deadline:
            for identity in pending[:]:
                response = api.get(f"/v1/jobs/{identity}")
                response.raise_for_status()
                job = response.json()
                if job["status"] == "READY":
                    pending.remove(identity)
                    print("HOLDOUT PDF READY", identity, flush=True)
                elif job["status"] == "FAILED_FINAL":
                    raise ValueError("holdout_ingestion_failed:" + str(job["error_code"]))
            if pending:
                time.sleep(3)
        if pending:
            raise TimeoutError("holdout_ingestion_deadline")
    result = dict(kb_id=kb, versions=versions, dataset_hash=digest, model_results_opened=False)
    target = ROOT / ".runtime/evaluation/holdout-binding.json"
    if target.exists() and json.loads(target.read_text()) != result:
        raise ValueError("holdout_binding_changed")
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
