"""Create personal local-only credentials without printing values."""

import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / ".env"
if not path.exists():
    path.write_text(
        "CW_DB_PASSWORD=" + secrets.token_hex(24) + "\nCW_ADMIN_TOKEN=" + secrets.token_hex(32) + "\n",
        encoding="utf-8",
    )
    print("Created local credentials in ignored .env")
else:
    print("Preserved existing local .env")
