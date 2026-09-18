"""API-first M1 surface. Long-running ingestion belongs exclusively to Celery."""

import hashlib
import hmac
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from citeweave import catalog, schemas
from citeweave.blobs import LocalBlobStore
from citeweave.db import migrate, transaction
from citeweave.domain import DocumentRow, IngestionJobRow, KnowledgeBaseRow, QueryRunRow, VersionRow
from citeweave.settings import settings


def create_app(
    admin_token: str | None = None, workspace_id: UUID | None = None, lab_root: Path | None = None
):
    admin_token = admin_token or settings().admin_token.get_secret_value()
    workspace_id = workspace_id or settings().workspace_id
    if len(admin_token) < 24:
        raise ValueError("admin_token_must_have_at_least_24_characters")

    @asynccontextmanager
    async def lifespan(app):
        migrate()
        yield

    app = FastAPI(title="CiteWeave", version="0.3.0-alpha.1", lifespan=lifespan)
    bearer = HTTPBearer(auto_error=False)

    def signature(expiry):
        return hmac.new(
            admin_token.encode(), (str(workspace_id) + ":" + expiry).encode(), hashlib.sha256
        ).hexdigest()

    def origin_ok(request):
        origin = request.headers.get("origin")
        if origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "origin_mismatch")

    def principal(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if credentials and hmac.compare_digest(credentials.credentials, admin_token):
            return workspace_id
        cookie = request.cookies.get("cw_session", "")
        expiry, _, sig = cookie.partition(".")
        if (
            not expiry.isdigit()
            or int(expiry) < time.time()
            or not hmac.compare_digest(sig, signature(expiry))
        ):
            raise HTTPException(401, "unauthorized")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin_ok(request)
        return workspace_id

    @app.middleware("http")
    async def identity(request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers.update(
            {
                "X-Request-ID": request.state.request_id,
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
            }
        )
        return response

    def error(request, code, status):
        return JSONResponse(
            {
                "error": {"code": code, "message": code, "retryable": status in (429, 503)},
                "request_id": request.state.request_id,
            },
            status_code=status,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error(request, str(exc.detail), exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error(request, "validation_error", 422)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        logging.error("database_error request=%s class=%s", request.state.request_id, type(exc).__name__)
        return error(request, "database_unavailable", 503)

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        with transaction() as db:
            db.execute(text("SELECT 1 FROM alembic_version"))
        return {"status": "ready", "capability": "durable_api", "model_health": "check_model_gateway"}

    @app.post("/v1/auth/session", status_code=204)
    def login(body: schemas.Login, request: Request, response: Response):
        origin_ok(request)
        if not hmac.compare_digest(body.token.get_secret_value(), admin_token):
            raise HTTPException(401, "unauthorized")
        expiry = str(int(time.time()) + 8 * 3600)
        response.set_cookie(
            "cw_session",
            expiry + "." + signature(expiry),
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            max_age=8 * 3600,
        )

    @app.delete("/v1/auth/session", status_code=204)
    def logout(response: Response, workspace=Depends(principal)):
        response.delete_cookie("cw_session")

    @app.post("/v1/knowledge-bases", response_model=schemas.KnowledgeBase, status_code=201)
    def create_kb(
        body: schemas.KnowledgeBaseCreate,
        response: Response,
        idempotency_key: str = Header(min_length=1, max_length=128),
        workspace=Depends(principal),
    ):
        row, created = catalog.create_kb(workspace, body, idempotency_key)
        response.status_code = 201 if created else 200
        return row

    @app.get("/v1/knowledge-bases", response_model=list[schemas.KnowledgeBase])
    def list_kbs(
        workspace=Depends(principal), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)
    ):
        with transaction() as db:
            return [
                schemas.KnowledgeBase.model_validate(r)
                for r in db.scalars(
                    select(KnowledgeBaseRow)
                    .where(KnowledgeBaseRow.workspace_id == workspace)
                    .order_by(KnowledgeBaseRow.created_at.desc(), KnowledgeBaseRow.id)
                    .limit(limit)
                    .offset(offset)
                )
            ]

    @app.get("/v1/knowledge-bases/{kb_id}", response_model=schemas.KnowledgeBase)
    def get_kb(kb_id: UUID, workspace=Depends(principal)):
        with transaction() as db:
            return schemas.KnowledgeBase.model_validate(catalog.authorized_kb(db, kb_id, workspace))

    @app.post(
        "/v1/knowledge-bases/{kb_id}/documents",
        response_model=schemas.UploadResult,
        status_code=202,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
            }
        },
    )
    async def upload(
        kb_id: UUID,
        request: Request,
        filename: str = Query(min_length=1, max_length=200),
        license: str = Query(pattern="^(original|CC0-1.0|CC-BY-4.0|permission-held)$"),
        document_id: UUID | None = None,
        idempotency_key: str = Header(min_length=1, max_length=128),
        workspace=Depends(principal),
    ):
        if request.headers.get("content-type", "").split(";")[0] != "application/pdf":
            raise HTTPException(415, "application_pdf_required")
        data = bytearray()
        async for part in request.stream():
            data.extend(part)
            if len(data) > 10 * 1024 * 1024:
                raise HTTPException(413, "pdf_max_10_mib")
        from starlette.concurrency import run_in_threadpool

        return await run_in_threadpool(
            catalog.upload, workspace, kb_id, bytes(data), filename, license, idempotency_key, document_id
        )

    @app.get("/v1/knowledge-bases/{kb_id}/documents", response_model=list[schemas.Document])
    def documents(kb_id: UUID, workspace=Depends(principal)):
        with transaction() as db:
            catalog.authorized_kb(db, kb_id, workspace)
            return [
                catalog.document_view(db, r)
                for r in db.scalars(
                    select(DocumentRow)
                    .where(DocumentRow.kb_id == kb_id)
                    .order_by(DocumentRow.created_at.desc())
                )
            ]

    @app.get("/v1/documents/{document_id}", response_model=schemas.Document)
    def document(document_id: UUID, workspace=Depends(principal)):
        with transaction() as db:
            row = db.get(DocumentRow, document_id)
            if not row:
                raise HTTPException(404, "document_not_found")
            catalog.authorized_kb(db, row.kb_id, workspace)
            return catalog.document_view(db, row)

    @app.get("/v1/jobs/{job_id}", response_model=schemas.Job)
    def job(job_id: UUID, workspace=Depends(principal)):
        with transaction() as db:
            row = db.get(IngestionJobRow, job_id)
            if not row:
                raise HTTPException(404, "job_not_found")
            version = db.get(VersionRow, row.document_version_id)
            catalog.authorized_kb(db, version.kb_id, workspace)
            return schemas.Job.model_validate(row)

    @app.get("/v1/document-versions/{version_id}/content")
    def content(version_id: UUID, workspace=Depends(principal)):
        with transaction() as db:
            row = db.get(VersionRow, version_id)
            if not row:
                raise HTTPException(404, "version_not_found")
            catalog.authorized_kb(db, row.kb_id, workspace)
            data = LocalBlobStore(settings().blob_root).get(row.blob_key)
            return Response(
                data,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": "inline; filename*=UTF-8''" + quote(row.filename),
                    "X-Source-SHA256": row.source_sha256,
                },
            )

    @app.post("/v1/queries", response_model=schemas.StreamEvent, response_class=StreamingResponse)
    def query(
        body: schemas.QueryCreate,
        idempotency_key: str = Header(min_length=1, max_length=128),
        workspace=Depends(principal),
    ):
        from citeweave.answering import begin_query, stream_answer

        run = begin_query(workspace, body, idempotency_key)
        return StreamingResponse(
            stream_answer(run), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
        )

    @app.get("/v1/runs/{run_id}", response_model=schemas.Run)
    def run(run_id: UUID, workspace=Depends(principal)):
        with transaction() as db:
            row = db.scalar(
                select(QueryRunRow).where(QueryRunRow.id == run_id, QueryRunRow.workspace_id == workspace)
            )
            if not row:
                raise HTTPException(404, "run_not_found")
            return schemas.Run.model_validate(row)

    @app.get("/v1/evidence/{evidence_id}", response_model=schemas.Citation)
    def evidence(evidence_id: UUID, run_id: UUID, workspace=Depends(principal)):
        from citeweave.answering import get_citation

        return get_citation(workspace, run_id, evidence_id)

    from citeweave.m2_api import mount

    mount(app, principal)

    if lab_root:
        from citeweave.lab import install_lab

        install_lab(app, lab_root)
    if (settings().web_root / "assets").is_dir():
        if (settings().web_root / "pdfjs").is_dir():
            app.mount("/pdfjs", StaticFiles(directory=settings().web_root / "pdfjs"), name="pdfjs")

        @app.get("/original-handbook.pdf", include_in_schema=False)
        def original_example():
            return FileResponse(settings().web_root / "original-handbook.pdf", media_type="application/pdf")

        app.mount("/assets", StaticFiles(directory=settings().web_root / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str):
            if path.startswith(("v1/", "health/")):
                raise HTTPException(404, "route_not_found")
            return FileResponse(settings().web_root / "index.html")

    return app
