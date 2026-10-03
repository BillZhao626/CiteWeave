"""Explicit bounded PG recovery; never dispatches a provider or installs a job."""

import argparse
import json
from uuid import UUID

from citeweave.conversations import reconcile_batch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=UUID)
    parser.add_argument("--limit", type=int, default=32)
    parser.add_argument(
        "--inspect", action="store_true", help="Read-only snapshot; never reconcile or dispatch"
    )
    parser.add_argument(
        "--include-terminal",
        action="store_true",
        help="Include active/accepted/cancelled/stale in inspection",
    )
    parser.add_argument("--run", type=UUID, help="Inspect one Run within the workspace")
    args = parser.parse_args()
    if args.inspect:
        from citeweave.recovery_inspection import inspect_recovery

        print(
            inspect_recovery(
                args.workspace, limit=args.limit, include_terminal=args.include_terminal, run_id=args.run
            ).model_dump_json()
        )
        return
    if args.include_terminal or args.run:
        parser.error("--include-terminal and --run require --inspect")
    views = reconcile_batch(args.workspace, limit=args.limit)
    print(json.dumps({"scanned": len(views), "conversation_ids": [str(v.id) for v in views]}))


if __name__ == "__main__":
    main()
