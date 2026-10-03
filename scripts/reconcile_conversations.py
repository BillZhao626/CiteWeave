"""Explicit bounded PG recovery; never dispatches a provider or installs a job."""

import argparse
import json
from uuid import UUID

from citeweave.conversations import reconcile_batch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=UUID)
    parser.add_argument("--limit", type=int, default=32)
    args = parser.parse_args()
    views = reconcile_batch(args.workspace, limit=args.limit)
    print(json.dumps({"scanned": len(views), "conversation_ids": [str(v.id) for v in views]}))


if __name__ == "__main__":
    main()
