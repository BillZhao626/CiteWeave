"""Explicit post-Holdout product launch; reuse an operator-selected existing corpus."""

import argparse
import os
from pathlib import Path
from uuid import UUID

IDENTITY = "citeweave-portfolio-alpha-e0"
PROMPT = "answer-telecom-consistency-v1"


def configure(database_name, workspace_id, blob_root):
    from sqlalchemy import make_url

    from citeweave.settings import Settings, settings

    current = Settings()
    url = current.db_url()
    if isinstance(url, str):
        url = make_url(url)
    os.environ.update(
        CW_DATABASE_URL=url.set(database=database_name).render_as_string(hide_password=False),
        CW_WORKSPACE_ID=str(workspace_id),
        CW_BLOB_ROOT=str(blob_root.resolve()),
        CW_RELEASE_IDENTITY=IDENTITY,
        CW_TELECOM_ANSWER_PROMPT=PROMPT,
        CW_PROVIDER_ATTEMPTS="1",
    )
    settings.cache_clear()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=["api", "worker"])
    parser.add_argument("--database-name", required=True)
    parser.add_argument("--workspace-id", required=True, type=UUID)
    parser.add_argument("--blob-root", required=True, type=Path)
    parser.add_argument("--port", type=int, default=18080)
    args = parser.parse_args()
    if not args.blob_root.is_dir():
        parser.error("blob-root must be an existing directory")
    configure(args.database_name, args.workspace_id, args.blob_root)
    if args.role == "api":
        import uvicorn

        uvicorn.run(
            "citeweave.api:create_app", factory=True, host="127.0.0.1", port=args.port, access_log=False
        )
    else:
        # Reuse durable outbox dispatch/recovery; portfolio smoke never dispatches evaluation.
        from citeweave.worker_runtime import main as worker_main

        worker_main(ingestion_only=True)


if __name__ == "__main__":
    main()
