"""Fetch one explicitly requested public Dense candidate; preserve the baseline manifest."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["HF_HOME"] = str(ROOT / ".cache/huggingface")
os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "120"
os.environ["HF_HUB_DISABLE_XET"] = "1"

IDENTITY = "BAAI/bge-m3"
REVISION = "5617a9f61b028005a4858fdac845db406aefb181"


def main():
    from huggingface_hub import HfApi, snapshot_download

    info = HfApi().model_info(IDENTITY, revision=REVISION)
    assert info.sha == REVISION and info.card_data.get("license") == "mit"
    path = snapshot_download(
        IDENTITY,
        revision=REVISION,
        allow_patterns=[
            "config.json",
            "config_sentence_transformers.json",
            "modules.json",
            "1_Pooling/config.json",
            "sentence_bert_config.json",
            "sentencepiece.bpe.model",
            "special_tokens_map.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "pytorch_model.bin",
            "README.md",
        ],
        max_workers=2,
    )
    record = dict(
        model=IDENTITY,
        revision=REVISION,
        license="mit",
        local_path=path,
        mode="dense_only",
        dimension=1024,
        sparse=False,
        multivector=False,
    )
    (ROOT / ".runtime/m3-bge-model.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("Pinned BGE-M3 Dense files ready", flush=True)


if __name__ == "__main__":
    main()
