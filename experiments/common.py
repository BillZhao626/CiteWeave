"""Read only this project's generated local configuration; never print secrets."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def configure():
    values = dict(
        line.split("=", 1)
        for line in (ROOT / ".env").read_text().splitlines()
        if line and not line.startswith("#")
    )
    os.environ.setdefault(
        "CW_DATABASE_URL", f"postgresql://citeweave:{values['CW_DB_PASSWORD']}@127.0.0.1:15432/citeweave"
    )
    os.environ.setdefault("CW_BROKER_URL", "redis://127.0.0.1:16379/0")
    return values


def report(name, data):
    path = ROOT / "docs" / "reports" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, default=str), flush=True)
