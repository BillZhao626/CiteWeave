"""Prepare only real isolated corpus/indexes. Never run paid DEV."""

import argparse

from citeweave.evaluation.dev_environment import prepare_environment

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recover-local-ingestion", action="store_true")
    args = parser.parse_args()
    try:
        receipt = prepare_environment(recover_local_ingestion=args.recover_local_ingestion)
        print(
            "Real isolated DEV corpus ready:",
            len(receipt["bindings"]),
            "sources; no external provider calls.",
        )
    except Exception as exc:
        print("DEV environment preparation failed:", type(exc).__name__)
        raise SystemExit(1) from None
