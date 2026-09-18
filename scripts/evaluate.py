"""API-only batch runner. Resume by ID without creating a second paid evaluation."""

import argparse
import json
import time
from uuid import UUID, uuid4

import httpx

from citeweave.settings import ROOT, settings


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--kb", type=UUID)
    group.add_argument("--resume", type=UUID)
    parser.add_argument(
        "--dataset",
        default="public-standards-v1",
        choices=["public-standards-v1", "public-protocols-holdout-v1"],
    )
    parser.add_argument("--split", default="dev", choices=["dev", "test", "all"])
    parser.add_argument(
        "--profile",
        default="m3-context",
        choices=["m2", "m3-dedup", "m3-context", "m3-answer", "m3-candidates40", "m3-parent", "m3-bge-dense"],
    )
    parser.add_argument(
        "--judge", default="judge-v4", choices=["judge-v1", "judge-v2", "judge-v3", "judge-v4"]
    )
    parser.add_argument("--replay-source", type=UUID)
    args = parser.parse_args()
    headers = {"Authorization": "Bearer " + settings().admin_token.get_secret_value()}
    with httpx.Client(base_url="http://127.0.0.1:18080", headers=headers, timeout=30, trust_env=False) as api:
        if args.resume:
            identity = str(args.resume)
        else:
            response = api.post(
                "/v1/evaluations",
                headers={"Idempotency-Key": str(uuid4())},
                json={
                    "kb_id": str(args.kb),
                    "dataset_id": args.dataset,
                    "split": args.split,
                    "profile": args.profile,
                    "judge_profile": args.judge,
                    "replay_source": str(args.replay_source) if args.replay_source else None,
                },
            )
            response.raise_for_status()
            identity = response.json()["id"]
        folder = ROOT / ".runtime/evaluation/runs" / identity
        folder.mkdir(parents=True, exist_ok=True)
        print("EVALUATION", identity, "(resume with --resume)", flush=True)
        deadline, previous = time.monotonic() + 7200, None
        while time.monotonic() < deadline:
            response = api.get(f"/v1/evaluations/{identity}")
            response.raise_for_status()
            row = response.json()
            summary = row["summary"]
            status = (row["status"], summary.get("assessed_count"), summary.get("judge_status"))
            if status != previous:
                print(
                    json.dumps({"status": status[0], "assessed": status[1], "judge": status[2]}), flush=True
                )
                previous = status
            if row["status"] in {"COMPLETED", "CANCELLED"}:
                break
            time.sleep(5)
        else:
            raise SystemExit("Runner polling deadline reached; evaluation remains durable. Resume by ID.")
        for route, filename in [("artifact", "artifact.json"), ("report", "report.md")]:
            response = api.get(f"/v1/evaluations/{identity}/{route}")
            response.raise_for_status()
            (folder / filename).write_text(response.text, encoding="utf-8")
        print("ARTIFACTS SAVED", identity, flush=True)


if __name__ == "__main__":
    main()
