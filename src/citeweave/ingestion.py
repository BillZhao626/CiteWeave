"""PDF pipeline. All externally visible publication is delegated to the fenced DB commit."""

import json
import logging
import tempfile
import threading
from dataclasses import asdict
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pdfplumber

from citeweave import ingestion_state as state
from citeweave.blobs import LocalBlobStore
from citeweave.evidence import Scope
from citeweave.index import QdrantIndex
from citeweave.model_client import ModelGateway
from citeweave.parsing import parse_simple_pdf
from citeweave.pipeline import chunk_blocks
from citeweave.retrieval import BM25Encoder
from citeweave.settings import settings

log = logging.getLogger(__name__)


def fault_gate(job_id, stage):
    """Disabled by default, no HTTP control. Acceptance uses a mounted local marker directory."""
    config = settings()
    if not config.enable_faults or not config.fault_root:
        return
    marker = config.fault_root / f"{job_id}.{stage}.pause"
    if marker.is_file():
        marker.with_suffix(".reached").write_text(stage)
        while marker.is_file():
            threading.Event().wait(0.1)  # Deliberate test barrier; never used by normal recovery.


def run_ingestion(job_id: str):
    lease = state.claim(UUID(job_id), str(uuid4()))
    if not lease:
        return
    fence = lease["fence"]
    job_id = lease["job_id"]
    stop, lost = threading.Event(), threading.Event()

    def pulse():
        while not stop.wait(max(1, settings().lease_seconds / 4)):
            try:
                state.heartbeat(job_id, fence)
            except Exception as exc:
                log.warning("heartbeat_failed job=%s error=%s", job_id, type(exc).__name__)
                lost.set()
                return

    thread = threading.Thread(target=pulse, daemon=True)
    thread.start()
    try:
        blobs = LocalBlobStore(settings().blob_root)
        fault_gate(job_id, "PARSING")
        with tempfile.TemporaryDirectory(prefix="cw-parse-") as temporary:
            path = Path(temporary) / "source.pdf"
            path.write_bytes(blobs.get(lease["blob_key"]))
            with pdfplumber.open(path) as pdf:
                page_count = len(pdf.pages)
                if not 0 < page_count <= 100:
                    raise ValueError("pdf_page_limit_100")
                for page in pdf.pages:
                    if page.mediabox[:2] != (0, 0) and list(page.mediabox[:2]) != [0, 0]:
                        raise ValueError("unsupported_nonzero_media_origin")
                    if page.cropbox and tuple(page.cropbox) != tuple(page.mediabox):
                        raise ValueError("unsupported_cropped_page")
            blocks = parse_simple_pdf(
                path,
                Scope(
                    workspace_id=lease["workspace_id"], kb_id=lease["kb_id"], revision_id=lease["version_id"]
                ),
            )
        state.stage(job_id, fence, "CHUNKING")
        chunks = chunk_blocks(blocks)
        canonical = blobs.put(
            json.dumps([b.model_dump(mode="json") for b in blocks], ensure_ascii=False).encode()
        )
        encoder = BM25Encoder.fit([c["text"] for c in chunks])
        state.stage(job_id, fence, "EMBEDDING")
        fault_gate(job_id, "EMBEDDING")
        model, vectors = ModelGateway(), []
        for start in range(0, len(chunks), 16):
            if lost.is_set():
                raise state.StaleAttempt()
            vectors.extend(model.embed([c["text"] for c in chunks[start : start + 16]]))
        state.stage(job_id, fence, "INDEXING")
        index = QdrantIndex()
        collection = f"cw1_v{lease['version_id'].hex}_f{fence}"
        if lease["kind"] == "rebuild":
            collection = f"cw2_v{lease['version_id'].hex}_j{job_id.hex}_f{fence}"
        from citeweave.lifecycle import register_index

        register_index(lease, collection)
        index.create(collection)
        for start in range(0, len(chunks), 16):
            if lost.is_set():
                raise state.StaleAttempt()
            index.write(collection, chunks[start : start + 16], vectors[start : start + 16], encoder, start)
            if start == 0:
                fault_gate(job_id, "INDEXING")  # Crash after a real partial write, before publication.
        index.verify(collection, [c["id"] for c in chunks])
        stats = asdict(encoder)
        stats["documents"] = []  # Query only needs immutable vocabulary / IDF / average length.
        state.publish(job_id, fence, chunks, collection, stats, canonical, page_count)
    except state.StaleAttempt:
        log.warning("stale_attempt_discarded job=%s fence=%s", job_id, fence)
    except Exception as exc:
        permanent = isinstance(exc, ValueError)
        code = str(exc) if permanent and str(exc).replace("_", "").isalnum() else type(exc).__name__
        if isinstance(exc, httpx.HTTPError):
            code = "model_gateway_unavailable"
        log.error("ingestion_failed job=%s code=%s", job_id, code)
        try:
            state.fail(
                job_id, fence, code, "文档处理失败，请检查文件格式或本地服务。错误代码：" + code, permanent
            )
        except state.StaleAttempt:
            log.warning("failure_after_lease_expired job=%s", job_id)
    finally:
        stop.set()
        thread.join(timeout=5)
