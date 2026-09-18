"""Read-only Qdrant directory measurements for already registered experiment collections."""

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone

from citeweave.settings import ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", required=True)
    args = parser.parse_args()
    if not args.key.replace("-", "").isalnum():
        raise ValueError("invalid_key")
    folder = ROOT / "docs/reports/m3-revisit"
    rows = json.loads((folder / (args.key + "-indexes.json")).read_text())
    destination = folder / (args.key + "-storage.json")
    if destination.exists():
        raise ValueError("storage_report_exists")
    result = []
    for row in rows:
        name = row["collection"]
        if not re.fullmatch(r"cw3x_[a-f0-9]{32}_[a-f0-9]{32}_a[0-9]+", name):
            raise ValueError("invalid_owned_collection")
        path = "/qdrant/storage/collections/" + name
        values = {}
        for flag, key in [("-sb", "directory_apparent_bytes"), ("-sk", "directory_allocated_kib")]:
            raw = subprocess.check_output(
                ["docker", "exec", "citeweave-m0-qdrant-1", "du", flag, path], text=True, timeout=20
            )
            values[key] = int(raw.split()[0])
        result.append(
            dict(
                collection=name,
                chunk_count=row["chunk_count"],
                dimension=row["embedding"]["dimension"],
                dense_float32_payload_bytes=row["chunk_count"] * row["embedding"]["dimension"] * 4,
                **values,
            )
        )
    destination.write_text(
        json.dumps(
            dict(
                at=datetime.now(timezone.utc).isoformat(),
                collections=result,
                limitation="Collection directories include WAL/segments/metadata and sparse vectors; allocated and apparent bytes differ. Not a vector-only size metric; model cache excluded.",
            ),
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
