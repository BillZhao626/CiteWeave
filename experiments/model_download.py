"""Download only public model files to this project's cache; record immutable revisions."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["HF_HOME"] = str(ROOT / ".cache" / "huggingface")
os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "120"
os.environ["HF_HUB_DISABLE_XET"] = "1"
from huggingface_hub import HfApi, snapshot_download

manifest = {}
REVISIONS = {
    "intfloat/multilingual-e5-small": "614241f622f53c4eeff9890bdc4f31cfecc418b3",
    "BAAI/bge-reranker-v2-m3": "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
}
for identity, revision in REVISIONS.items():
    info = HfApi().model_info(identity, revision=revision)
    assert info.sha == revision
    print(f"Downloading {identity} @ {info.sha}", flush=True)
    path = snapshot_download(
        identity,
        revision=info.sha,
        allow_patterns=[
            "*.json",
            "*.safetensors",
            "sentencepiece.bpe.model",
            "*.txt",
            "README.md",
            "LICENSE",
        ],
        max_workers=3,
    )
    manifest[identity] = {
        "revision": info.sha,
        "local_path": path,
        "license": info.card_data.get("license") if info.card_data else None,
    }
    (ROOT / ".runtime" / "models.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Ready {identity}", flush=True)
