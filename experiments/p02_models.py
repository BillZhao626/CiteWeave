"""GPU encoding and reranking in a separate process, so models never overlap in memory."""

import gc
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["HF_HOME"] = str(ROOT / ".cache" / "huggingface")
os.environ["HF_HUB_OFFLINE"] = "1"
import numpy as np
import psutil
import torch
from sentence_transformers import CrossEncoder, SentenceTransformer


def main():
    torch.set_num_threads(4)
    output = ROOT / ".artifacts" / "p02"
    corpus = json.loads((output / "corpus.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / ".runtime" / "models.json").read_text(encoding="utf-8"))
    mode = sys.argv[1]
    assert torch.cuda.is_available(), "real_gpu_required_for_this_profile"
    torch.cuda.reset_peak_memory_stats()
    start = time.perf_counter()
    identity = "intfloat/multilingual-e5-small" if mode == "embed" else "BAAI/bge-reranker-v2-m3"
    record = manifest[identity]
    if mode == "embed":
        model = SentenceTransformer(
            record["local_path"], device="cuda", model_kwargs={"torch_dtype": torch.float16}
        )
        model.max_seq_length = 256
        load = time.perf_counter() - start
        start = time.perf_counter()
        documents = model.encode(
            ["passage: " + d["text"] for d in corpus["documents"]],
            batch_size=8,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        torch.cuda.synchronize()
        encoding = time.perf_counter() - start
        start = time.perf_counter()
        queries = model.encode(
            ["query: " + q["text"] for q in corpus["queries"]],
            batch_size=8,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        torch.cuda.synchronize()
        np.savez(
            output / "vectors.npz", documents=documents.astype("float32"), queries=queries.astype("float32")
        )
        stats = {
            "corpus_seconds": encoding,
            "queries_batch_seconds": time.perf_counter() - start,
            "dimension": int(documents.shape[1]),
        }
    else:
        model = CrossEncoder(
            record["local_path"], device="cuda", max_length=256, model_kwargs={"torch_dtype": torch.float16}
        )
        load = time.perf_counter() - start
        candidates = json.loads((output / "candidates.json").read_text(encoding="utf-8"))
        by_id = {d["id"]: d["text"] for d in corpus["documents"]}
        rankings, latency = {}, []
        for query in corpus["queries"]:
            ids = candidates[query["id"]]
            start = time.perf_counter()
            values = model.predict(
                [(query["text"], by_id[i]) for i in ids],
                batch_size=4,
                show_progress_bar=False,
                activation_fn=torch.nn.Identity(),
            )
            torch.cuda.synchronize()
            latency.append(time.perf_counter() - start)
            rankings[query["id"]] = [
                i for i, _ in sorted(zip(ids, values.tolist()), key=lambda x: (-x[1], x[0]))
            ]
        (output / "reranked.json").write_text(json.dumps(rankings), encoding="utf-8")
        stats = {
            "per_query_seconds_p50": float(np.percentile(latency, 50)),
            "per_query_seconds_p95": float(np.percentile(latency, 95)),
            "candidate_count": 20,
        }
    stats.update(
        model=identity,
        revision=record["revision"],
        license=record["license"],
        device=torch.cuda.get_device_name(),
        torch=torch.__version__,
        dtype="float16",
        max_length=256,
        load_seconds=load,
        load_kind="local-cache first process load; download excluded",
        process_rss_mb=psutil.Process().memory_info().rss / 2**20,
        gpu_peak_allocated_mb=torch.cuda.max_memory_allocated() / 2**20,
        gpu_peak_reserved_mb=torch.cuda.max_memory_reserved() / 2**20,
        host_available_mb=psutil.virtual_memory().available / 2**20,
    )
    (output / f"{mode}-stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps(stats), flush=True)
    del model
    gc.collect()
    torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
