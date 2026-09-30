"""Explicit provider-free download of a pinned, licensed offline tokenizer.

No credentials, model weights or inference calls. Never runs during API startup.
"""

import hashlib
import urllib.request

from citeweave.provider_accounting import RECIPE_REVISION, TOKENIZER_SHA256
from citeweave.settings import ROOT


def main():
    base = f"https://raw.githubusercontent.com/deepseek-ai/deepseek-recipe/{RECIPE_REVISION}/"
    output = ROOT / ".runtime/provider-accounting"
    output.mkdir(parents=True, exist_ok=True)
    for remote, local, expected in (
        ("static/tokenizers/v41/tokenizer.json", "static_tokenizers_v41_tokenizer.json", TOKENIZER_SHA256),
        (
            "static/tokenizers/LICENSE",
            "static_tokenizers_LICENSE",
            "f2c6c602815669d292889e5be8c802f2ed950653b77999b1584e8e6aed25d040",
        ),
    ):
        with urllib.request.urlopen(base + remote, timeout=30) as response:
            data = response.read(32 * 1024 * 1024)
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("official_tokenizer_download_hash_mismatch")
        (output / local).write_bytes(data)
    print("Pinned tokenizer and license saved; no inference requested.")


if __name__ == "__main__":
    main()
