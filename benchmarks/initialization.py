"""Pinned E5 fresh-process versus resident measurement; never a product mode."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def fresh(model_path, device, text):
    import torch
    from sentence_transformers import SentenceTransformer

    from citeweave.embeddings import E5

    if Path(model_path).name != E5["revision"]:
        raise ValueError("initialization_model_revision")
    start = time.perf_counter()
    dtype = torch.float16 if device == "cuda" else torch.float32
    model = SentenceTransformer(
        model_path, device=device, local_files_only=True, model_kwargs={"torch_dtype": dtype}
    )
    model.max_seq_length = E5["max_tokens"]
    if len(model.tokenizer("query: " + text, truncation=False)["input_ids"]) > E5["max_tokens"]:
        raise ValueError("initialization_input_limit")
    loaded = time.perf_counter()
    vectors = model.encode(["query: " + text], normalize_embeddings=True, batch_size=1)
    return dict(
        load_ms=(loaded - start) * 1000,
        first_embed_ms=(time.perf_counter() - loaded) * 1000,
        dimension=len(vectors[0]),
        model=E5,
        device=device,
        batch=1,
        precision=str(model[0].auto_model.dtype),
        disk_cache="uncontrolled_os_cache",
    )


def compare(python, model_path, device, text, count=3):
    import httpx

    from citeweave.embeddings import E5
    from citeweave.model_client import ModelGateway
    from citeweave.settings import ROOT, settings
    from citeweave.structural_contract import QUERY_CONTRACT

    if not 1 <= count <= 12:
        raise ValueError("initialization_sample_limit")
    health = httpx.get(settings().model_url + "/health", timeout=5, trust_env=False).json()
    if health["device"] != device or health["embedding"] != E5:
        raise ValueError("initialization_resident_identity_mismatch")
    rows = []
    for i in range(count):
        child = subprocess.run(
            [
                python,
                "-m",
                "benchmarks.initialization",
                "--fresh",
                "--model-path",
                str(model_path),
                "--device",
                device,
                "--text",
                text,
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=True,
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src") + os.pathsep + str(ROOT), "PYTHONUTF8": "1"},
        )
        rows.append(dict(mode="fresh_process", sequence=i, **json.loads(child.stdout)))
        start = time.perf_counter()
        vectors = ModelGateway().embed([text], query=True, contract=QUERY_CONTRACT)
        rows.append(
            dict(
                mode="resident",
                sequence=i,
                elapsed_ms=(time.perf_counter() - start) * 1000,
                dimension=len(vectors[0]),
                batch=1,
                model=E5,
                device=device,
                precision="torch.float16" if device == "cuda" else "torch.float32",
            )
        )
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--device", choices=["cpu", "cuda"], required=True)
    parser.add_argument("--text", default="HTTP control stream")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--count", type=int, default=3)
    args = parser.parse_args()
    print(
        json.dumps(
            fresh(args.model_path, args.device, args.text)
            if args.fresh
            else compare(args.python, args.model_path, args.device, args.text, args.count)
        )
    )
