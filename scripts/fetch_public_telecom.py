"""Acquire the approved official PDF editions; retain and verify existing bytes."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pdfplumber

ROOT = Path(__file__).resolve().parents[1]


def verify(path, record):
    raw = path.read_bytes()
    if not raw.startswith(b"%PDF-") or len(raw) != record["byte_length"]:
        raise ValueError("source_signature_or_length_mismatch")
    if hashlib.sha256(raw).hexdigest() != record["raw_sha256"]:
        raise ValueError("source_hash_mismatch")
    with pdfplumber.open(path) as pdf:
        first = pdf.pages[0].extract_text() or ""
        if (
            len(pdf.pages) != record["pages"]
            or hashlib.sha256(first.encode()).hexdigest() != record["first_page_text_sha256"]
        ):
            raise ValueError("source_page_or_identity_mismatch")
    return {
        "source_id": record["source_id"],
        "status": "VERIFIED",
        "raw_sha256": record["raw_sha256"],
        "bytes": len(raw),
        "pages": record["pages"],
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def acquire(record, directory, client):
    url = urlsplit(record["download_url"])
    if url.scheme != "https" or url.netloc not in {"www.rfc-editor.org", "docs.oasis-open.org"}:
        raise ValueError("official_source_url_required")
    destination = directory / (record["source_id"] + ".pdf")
    if destination.exists():
        return verify(destination, record)  # A mismatch is an error, never an implicit overwrite.
    temporary = destination.with_suffix(".pdf.part")
    created = False
    try:
        with client.stream("GET", record["download_url"], follow_redirects=False, timeout=45) as response:
            response.raise_for_status()
            length = 0
            with temporary.open("xb") as output:
                created = True
                for block in response.iter_bytes():
                    length += len(block)
                    if length > record["byte_length"]:
                        raise ValueError("source_byte_limit")
                    output.write(block)
        result = verify(temporary, record)
        temporary.rename(destination)
        return result
    finally:
        if created and temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / ".runtime/private/public-telecom")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "corpus/public_telecom_manifest.json").read_text(encoding="utf-8"))
    args.directory.mkdir(parents=True, exist_ok=True)
    results = []
    with httpx.Client() as client:
        for record in manifest["sources"]:
            try:
                results.append(acquire(record, args.directory, client))
            except (ValueError, OSError, httpx.HTTPError) as exc:
                results.append(
                    {
                        "source_id": record["source_id"],
                        "status": "UNAVAILABLE_OR_MISMATCH",
                        "error": type(exc).__name__,
                        "http_status": exc.response.status_code
                        if isinstance(exc, httpx.HTTPStatusError)
                        else None,
                    }
                )
    report = {"manifest_revision": manifest["manifest_revision"], "sources": results}
    (args.directory / "acquisition-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if all(r["status"] == "VERIFIED" for r in results) else 1)


if __name__ == "__main__":
    main()
