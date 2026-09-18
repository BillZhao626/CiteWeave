"""Local authenticated single-GPU adapter, isolated from the business Python environment."""

import argparse
import hashlib
import hmac
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["HF_HOME"] = str(ROOT / ".cache/huggingface")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"


def main():
    import torch
    from sentence_transformers import CrossEncoder, SentenceTransformer

    from citeweave.embeddings import embedding_identity
    from citeweave.reliability import FairGate, ModelCapacityError
    from citeweave.structural_contract import QUERY_CONTRACT, pair_counts, query_counts
    from citeweave.tokenization import CONTRACT, TOKENIZERS, fits, tokenize_response

    parser = argparse.ArgumentParser()
    parser.add_argument("--embedding", choices=["e5-small", "bge-m3"], default="e5-small")
    args = parser.parse_args()
    identity = embedding_identity(args.embedding)

    local = {}
    if (ROOT / ".env").exists():
        local = dict(
            line.split("=", 1)
            for line in (ROOT / ".env").read_text().splitlines()
            if "=" in line and not line.startswith("#")
        )
    admin = os.environ.get("CW_ADMIN_TOKEN") or local.get("CW_ADMIN_TOKEN", "")
    if len(admin) < 24:
        raise RuntimeError("missing_admin_token_run_bootstrap")
    token = (
        os.environ.get("CW_MODEL_TOKEN") or hashlib.sha256(("model-gateway:" + admin).encode()).hexdigest()
    )
    torch.set_num_threads(4)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    manifest = json.loads((ROOT / ".runtime/models.json").read_text())
    if args.embedding == "bge-m3":
        selected_model = json.loads((ROOT / ".runtime/m3-bge-model.json").read_text())
        if selected_model["model"] != identity["model"] or selected_model["revision"] != identity["revision"]:
            raise ValueError("embedding_manifest_mismatch")
    else:
        selected_model = manifest[identity["model"]]
    if (
        selected_model["revision"] != identity["revision"]
        or manifest[TOKENIZERS["bge"]["model"]]["revision"] != TOKENIZERS["bge"]["revision"]
    ):
        raise ValueError("resident_model_manifest_mismatch")
    embed = SentenceTransformer(
        selected_model["local_path"],
        device=device,
        model_kwargs={"torch_dtype": dtype},
    )
    embed.max_seq_length = 256
    rerank = CrossEncoder(
        manifest["BAAI/bge-reranker-v2-m3"]["local_path"],
        device=device,
        max_length=512,
        model_kwargs={"torch_dtype": dtype},
    )
    # 160 + 160 codepoints can exceed 256 tokens as a pair; M1 raises pair cap to 512,
    # explicitly rejecting token overflow rather than silently truncating evidence.
    gate = FairGate(max_waiters=4)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Request bodies/headers never enter logs.

        def reply(self, status, body):
            encoded = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            if self.path != "/health":
                return self.reply(404, {"error": "not_found"})
            return self.reply(
                200,
                {
                    "status": "ready",
                    "device": device,
                    "concurrency": 1,
                    "embedding_dimension": identity["dimension"],
                    "embedding": identity,
                    "cuda_peak_allocated_mib": torch.cuda.max_memory_allocated() / 2**20
                    if device == "cuda"
                    else None,
                    "cuda_peak_reserved_mib": torch.cuda.max_memory_reserved() / 2**20
                    if device == "cuda"
                    else None,
                    "reranker_max_tokens": 512,
                    "queue": gate.snapshot(),
                },
            )

        def do_POST(self):
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                return self.reply(401, {"error": "unauthorized"})
            acquired = False
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 128 * 1024:
                    return self.reply(413, {"error": "request_size_limit"})
                self.connection.settimeout(5)
                body = json.loads(self.rfile.read(size))
                target = body.get("contract") == QUERY_CONTRACT
                if not target and self.path != "/tokenize" and size > 32767:
                    return self.reply(413, {"error": "request_size_limit"})
                texts = body.get("texts")
                if target:
                    if identity != embedding_identity():
                        return self.reply(422, {"error": "embedding_identity_mismatch"})
                    if self.path == "/context-tokenize":
                        if (
                            not isinstance(texts, list)
                            or not 0 < len(texts) <= 20
                            or any(not isinstance(t, str) or not 0 < len(t) <= 12000 for t in texts)
                        ):
                            return self.reply(422, {"error": "structural_text_limit"})
                        return self.reply(
                            200,
                            dict(
                                contract=QUERY_CONTRACT,
                                tokenizers=TOKENIZERS,
                                hashes=[hashlib.sha256(t.encode()).hexdigest() for t in texts],
                                counts=[
                                    len(
                                        rerank.tokenizer(t, add_special_tokens=False, truncation=False)[
                                            "input_ids"
                                        ]
                                    )
                                    for t in texts
                                ],
                            ),
                        )
                    question = body.get("question")
                    if self.path == "/embed":
                        if not body.get("query") or not isinstance(texts, list) or len(texts) != 1:
                            return self.reply(422, {"error": "structural_query_contract"})
                        question = texts[0]
                    measured = query_counts(question, embed.tokenizer, rerank.tokenizer)
                    if self.path == "/query-tokenize":
                        return self.reply(200, dict(measured, contract=QUERY_CONTRACT, tokenizers=TOKENIZERS))
                    if self.path == "/rerank":
                        measured = pair_counts(question, texts, embed.tokenizer, rerank.tokenizer)
                        waiting = time.perf_counter()
                        gate.acquire(timeout=8)
                        acquired = True
                        started = time.perf_counter()
                        scores = rerank.predict(
                            [(question, t) for t in texts],
                            batch_size=4,
                            show_progress_bar=False,
                            activation_fn=torch.nn.Identity(),
                        ).tolist()
                        return self.reply(
                            200,
                            dict(
                                measured,
                                contract=QUERY_CONTRACT,
                                tokenizers=TOKENIZERS,
                                scores=scores,
                                queue_ms=(started - waiting) * 1000,
                                inference_ms=(time.perf_counter() - started) * 1000,
                            ),
                        )
                if self.path == "/tokenize":
                    if body.get("contract") != CONTRACT or identity != embedding_identity():
                        return self.reply(422, {"error": "tokenizer_identity_mismatch"})
                    gate.acquire(timeout=8)
                    acquired = True
                    return self.reply(200, tokenize_response(texts, embed.tokenizer, rerank.tokenizer))
                structural = body.get("contract") == CONTRACT
                if body.get("contract") not in (None, CONTRACT, QUERY_CONTRACT):
                    return self.reply(422, {"error": "unknown_model_contract"})
                if (
                    not isinstance(texts, list)
                    or not 0 < len(texts) <= 20
                    or any(
                        not isinstance(t, str)
                        or not 0 < len(t) <= (512 if target else 960 if structural else 160)
                        for t in texts
                    )
                ):
                    return self.reply(422, {"error": "text_limit_20_by_160"})
                if self.path == "/embed":
                    if body.get("embedding", embedding_identity()) != identity:
                        return self.reply(422, {"error": "embedding_identity_mismatch"})
                    if structural:
                        if body.get("query") or identity != embedding_identity():
                            return self.reply(422, {"error": "structural_embedding_contract"})
                        measured = tokenize_response(texts, embed.tokenizer, rerank.tokenizer)
                        if any(not fits(t, c) for t, c in zip(texts, measured["rows"], strict=True)):
                            return self.reply(422, {"error": "structural_token_limit"})
                    values = [
                        (identity["query_prefix"] if body.get("query") else identity["document_prefix"]) + t
                        for t in texts
                    ]
                    if any(len(embed.tokenizer(v)["input_ids"]) > 256 for v in values):
                        return self.reply(422, {"error": "embedding_token_limit"})
                    gate.acquire(timeout=8)
                    acquired = True
                    vectors = (
                        embed.encode(values, batch_size=8, normalize_embeddings=True, show_progress_bar=False)
                        .astype("float32")
                        .tolist()
                    )
                    return self.reply(200, {"vectors": vectors, "embedding": identity})
                if self.path == "/rerank":
                    if structural:
                        return self.reply(422, {"error": "structural_rerank_not_enabled"})
                    question = body.get("question")
                    if not isinstance(question, str) or not 0 < len(question) <= 160:
                        return self.reply(422, {"error": "question_limit"})
                    pairs = [(question, t) for t in texts]
                    if any(len(rerank.tokenizer(a, b)["input_ids"]) > 512 for a, b in pairs):
                        return self.reply(422, {"error": "reranker_token_limit"})
                    gate.acquire(timeout=8)
                    acquired = True
                    scores = rerank.predict(
                        pairs, batch_size=4, show_progress_bar=False, activation_fn=torch.nn.Identity()
                    ).tolist()
                    return self.reply(200, {"scores": scores})
                return self.reply(404, {"error": "not_found"})
            except ModelCapacityError as exc:
                return self.reply(429, {"error": exc.code})
            except ValueError as exc:
                code = (
                    str(exc)
                    if str(exc)
                    in {
                        "query_token_limit",
                        "question_limit",
                        "structural_text_limit",
                        "reranker_token_limit",
                    }
                    else "invalid_model_request"
                )
                return self.reply(422, {"error": code})
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                return  # Disconnected client; inference is bounded to one admitted batch.
            except Exception as exc:
                print("model_request_failed " + type(exc).__name__, flush=True)
                return self.reply(503, {"error": "model_inference_failed"})
            finally:
                if acquired:
                    gate.release()

    class BoundedServer(ThreadingHTTPServer):
        handlers = threading.BoundedSemaphore(8)

        def process_request(self, request, client_address):
            if not self.handlers.acquire(blocking=False):
                try:
                    request.settimeout(1)
                    request.sendall(
                        b"HTTP/1.1 429 Too Many Requests\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                    )
                finally:
                    self.shutdown_request(request)
                return
            try:
                super().process_request(request, client_address)
            except BaseException:
                self.handlers.release()
                raise

        def process_request_thread(self, request, client_address):
            try:
                super().process_request_thread(request, client_address)
            finally:
                self.handlers.release()

    bind = os.environ.get("CW_MODEL_BIND", "127.0.0.1")
    print(json.dumps({"status": "ready", "device": device, "port": 18081}), flush=True)
    BoundedServer((bind, 18081), Handler).serve_forever()


if __name__ == "__main__":
    main()
