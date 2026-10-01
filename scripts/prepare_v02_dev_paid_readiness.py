"""Offline authorization packet specimens; optional read-only LOCAL binding probe.

No paid launcher, provider construction, application migration or corpus writes.
"""

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from citeweave.domain import VersionRow
from citeweave.embeddings import embedding_identity
from citeweave.evaluation.dev_dataset import canonical
from citeweave.evaluation.dev_paid_readiness import CHECKPOINT_COMMIT, CHECKPOINT_TREE, build_readiness
from citeweave.provider_accounting import DeepSeekAccounting
from citeweave.settings import settings
from citeweave.tokenization import TOKENIZERS

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".runtime/evaluation/v02-dev-paid-readiness"
READINESS_ALLOWLIST = {
    "HANDOFF.md",
    "docs/README.md",
    "docs/V02_DEV_PAID_EXECUTION_AUTHORIZATION.md",
    "src/citeweave/evaluation/dev_paid_readiness.py",
    "scripts/prepare_v02_dev_paid_readiness.py",
    "tests/test_v02_dev_paid_readiness.py",
    "tests/test_v02_dev_paid_postgres.py",
}


def baseline():
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8").strip()

    if git("rev-parse", "HEAD") != CHECKPOINT_COMMIT or git("rev-parse", "HEAD^{tree}") != CHECKPOINT_TREE:
        raise ValueError("readiness_checkpoint_mismatch")
    changed = set(filter(None, git("diff", "--name-only", "HEAD").splitlines()))
    changed.update(filter(None, git("ls-files", "--others", "--exclude-standard").splitlines()))
    if not changed <= READINESS_ALLOWLIST:
        raise ValueError("readiness_unauthorized_worktree_difference")
    return dict(commit=CHECKPOINT_COMMIT, tree=CHECKPOINT_TREE, authorized_readiness_changes=sorted(changed))


def local_bindings(packet):
    """Metadata only, no retrieval substitute and no secrets/error bodies in receipts."""
    config = settings()
    url = make_url(config.db_url())
    if url.host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("readiness_local_pg_required")
    result = dict(postgres="NOT_VERIFIED", migration=None, dev_versions=[], qdrant="NOT_VERIFIED")
    engine = create_engine(url, connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '3000ms'"))
            result["migration"] = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        with Session(engine) as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            session.execute(text("SET LOCAL statement_timeout = '3000ms'"))
            rows = session.scalars(
                select(VersionRow).where(VersionRow.id.in_([s["version_id"] for s in packet["sources"]]))
            ).all()
            result["dev_versions"] = [
                dict(
                    version_id=str(v.id),
                    status=v.status,
                    source_sha256=v.source_sha256,
                    index_collection=v.index_collection,
                )
                for v in rows
            ]
        result["postgres"] = "CONNECTED_READ_ONLY"
    except Exception as exc:
        result["postgres"] = "CHECK_FAILED:" + type(exc).__name__
    finally:
        engine.dispose()
    for name, endpoint in (
        ("qdrant", config.qdrant_url + "/collections"),
        ("model_gateway", config.model_url + "/health"),
    ):
        if urlsplit(endpoint).hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("readiness_local_service_required")
        try:
            with httpx.Client(timeout=3, trust_env=False) as client:
                response = client.get(endpoint)
                result[name] = "HTTP_" + str(response.status_code)
                if response.status_code == 200 and name == "qdrant":
                    names = sorted(x["name"] for x in response.json()["result"]["collections"])
                    result["qdrant_collection_inventory_sha256"] = hashlib.sha256(
                        canonical(names)
                    ).hexdigest()
                    result["qdrant_collection_count"] = len(names)
                elif response.status_code == 200:
                    result["resident_embedding"] = response.json().get("embedding")
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            result[name] = "CHECK_FAILED:" + type(exc).__name__
    result["expected_embedding"] = embedding_identity()
    result["expected_reranker"] = TOKENIZERS["bge"]
    result["local_model_manifests"] = []
    manifest = ROOT / ".runtime/models.json"
    if manifest.is_file():
        values = json.loads(manifest.read_bytes())
        for identity in (result["expected_embedding"], result["expected_reranker"]):
            entry = values.get(identity["model"], {})
            path = entry.get("local_path")
            result["local_model_manifests"].append(
                dict(
                    model=identity["model"],
                    revision=entry.get("revision"),
                    revision_matches=entry.get("revision") == identity["revision"],
                    path_exists=bool(path and Path(path).is_dir()),
                )
            )
    result["checked_utc"] = datetime.now(timezone.utc).isoformat()
    result["real_dev_retrieval"] = "NOT_VERIFIED_NO_READY_CORPUS_BINDING"
    result["fixture_repository_substituted_for_real_binding"] = False
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe-local", action="store_true")
    args = parser.parse_args()
    checkpoint = baseline()
    packet = build_readiness(
        ROOT, DeepSeekAccounting(ROOT / ".runtime/provider-accounting/static_tokenizers_v41_tokenizer.json")
    )
    packet["baseline_verification"] = checkpoint
    packet["readiness_sources"] = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in sorted(READINESS_ALLOWLIST)
        if (ROOT / name).is_file()
    }
    packet["configured_model_alias"] = settings().deepseek_model
    packet["configured_answer_prompt"] = settings().telecom_answer_prompt
    packet["positive_runtime_policy_configured"] = settings().conversation_runtime_policy is not None
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if args.probe_local:
        (OUTPUT / "local-bindings.json").write_bytes(canonical(local_bindings(packet)))
    (OUTPUT / "provider-free-packet.json").write_bytes(canonical(packet))
    print(packet["status"])
    print("24 logical attempts; calls expected36/conditional38/protocol48; live token/CNY bounds UNKNOWN.")
    print("Gold/source identities verified. DEV/HARD/REG NOT_RUN; provider/model/Judge=0; spending=0.")


if __name__ == "__main__":
    main()
