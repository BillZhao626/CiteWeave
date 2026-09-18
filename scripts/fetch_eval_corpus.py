"""Fetch only frozen public manifest sources into ignored local storage; verify exact bytes."""

import hashlib

import httpx

from citeweave.evaluation.dataset import load_dataset
from citeweave.settings import ROOT


def main():
    dataset, _ = load_dataset()
    folder = ROOT / ".runtime/evaluation/corpus"
    folder.mkdir(parents=True, exist_ok=True)
    for source in dataset["sources"]:
        path = folder / source["filename"]
        if path.exists():
            data = path.read_bytes()
        else:
            response = httpx.get(source["download_url"], timeout=60, follow_redirects=True)
            response.raise_for_status()
            data = response.content
        if hashlib.sha256(data).hexdigest() != source["sha256"]:
            raise ValueError("frozen_source_hash_mismatch:" + source["source_id"])
        if not path.exists():
            path.write_bytes(data)
        print(source["source_id"], "verified", len(data), "bytes", flush=True)


if __name__ == "__main__":
    main()
