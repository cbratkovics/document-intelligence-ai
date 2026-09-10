"""FastAPI application factory.

Long-lived services (manifest, indexes, providers) are created in the lifespan
handler and attached to ``app.state`` so every route shares one consistent
view of the corpus. Importing this module performs no I/O.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from ..core.config import Settings, get_settings
from ..core.types import IndexCompatibilityError, IngestionError, NotFoundError
from ..monitoring import metrics
from ..rag.generator import Generator, ProviderError, build_chat_client
from ..rag.reranker import build_reranker
from ..rag.retriever import RetrievalRequestError, Retriever
from ..rag.service import DocumentService
from .endpoints import router
from .health import router as health_router

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"

DESCRIPTION = """
Document search and evidence-grounded question answering over a single local corpus.

**Supported formats**: .txt, .md, .rst (plain text), .pdf (text layer only).

**Retrieval modes**: `lexical` (BM25) always works; `vector` and `hybrid` need an
embedding provider. Every response reports the mode that actually ran.

**Answers** are generated only when a generation provider is configured and are
checked so that every citation resolves to a passage that was in the model's context.
Without a provider the API returns the supporting excerpts instead.

**Access control**: when `API_KEY` is set every `/api/v1` route requires the
`X-API-Key` header. Without it the server runs in local mode with no
authentication, which is only appropriate on a trusted machine. There is no
multi-tenant isolation: one process serves one corpus.
"""


def build_services(settings: Settings):
    service = DocumentService.from_settings(settings)
    chat = build_chat_client(settings)
    reranker = build_reranker(settings, chat)
    retriever = Retriever(service, settings, reranker)
    generator = Generator(retriever, settings, chat)
    return service, generator


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.service = None
        app.state.generator = None
        app.state.startup_error = None
        try:
            service, generator = build_services(settings)
            app.state.service = service
            app.state.generator = generator
            metrics.initialize_metrics(
                settings.app_version,
                settings.app_env,
                settings.resolved_embedding_provider,
                settings.resolved_generation_provider,
            )
            logger.info(
                "Started (storage=%s, embeddings=%s, generation=%s, reranker=%s, auth=%s)",
                settings.storage_mode,
                settings.resolved_embedding_provider,
                settings.resolved_generation_provider,
                settings.reranker_mode,
                "api_key" if settings.api_key else "none",
            )
        except IndexCompatibilityError as exc:
            app.state.startup_error = str(exc)
            logger.error("Startup failed: %s", exc)
        except Exception as exc:
            app.state.startup_error = f"{type(exc).__name__}: {exc}"
            logger.exception("Startup failed")
        yield
        if app.state.service is not None:
            app.state.service.close()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=[
            {"name": "documents", "description": "Upload, inspect, replace, and delete documents"},
            {"name": "search", "description": "Lexical, vector, and hybrid retrieval"},
            {"name": "query", "description": "Grounded question answering"},
            {"name": "evaluation", "description": "Optional LLM-based answer rating"},
            {"name": "health", "description": "Liveness, readiness, statistics"},
        ],
    )
    app.state.settings = settings

    origins = settings.cors_origin_list
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials="*" not in origins,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Content-Type", "X-API-Key"],
        )

    app.include_router(router, prefix="/api/v1")
    app.include_router(health_router)

    if settings.metrics_enabled and metrics.AVAILABLE:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        @app.get("/metrics", include_in_schema=False)
        async def metrics_endpoint() -> Response:
            return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        start = time.perf_counter()
        if metrics.AVAILABLE:
            metrics.active_requests.inc()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            if metrics.AVAILABLE:
                metrics.active_requests.dec()
            route = request.scope.get("route")
            template = getattr(route, "path", None) or "unmatched"
            metrics.record_request(
                request.method, template, status_code, time.perf_counter() - start
            )

    # -- error handling: preserve status codes, sanitize details -------------
    def _error(request: Request, status: int, message: str, code: Optional[str] = None):
        return JSONResponse(
            status_code=status,
            content={
                "error": message,
                "code": code,
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(IngestionError)
    async def _ingestion_error(request: Request, exc: IngestionError):
        return _error(request, exc.status, exc.message, exc.code)

    @app.exception_handler(NotFoundError)
    async def _not_found(request: Request, exc: NotFoundError):
        return _error(request, 404, f"Document not found: {exc}", "not_found")

    @app.exception_handler(RetrievalRequestError)
    async def _retrieval_error(request: Request, exc: RetrievalRequestError):
        return _error(request, exc.status, str(exc), "invalid_request")

    @app.exception_handler(ProviderError)
    async def _provider_error(request: Request, exc: ProviderError):
        return _error(request, 502, f"Generation provider error: {exc}", "provider_error")

    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else None
        payload = {
            "error": detail or "Request failed",
            "code": None,
            "request_id": getattr(request.state, "request_id", None),
        }
        if not isinstance(exc.detail, str):
            payload["detail"] = exc.detail
        return JSONResponse(status_code=exc.status_code, content=payload, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": "Validation failed",
                "code": "validation_error",
                "detail": exc.errors(),
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception("Unhandled error (request %s)", getattr(request.state, "request_id", "?"))
        message = (
            f"{type(exc).__name__}: {exc}" if settings.is_development else "Internal server error"
        )
        return _error(request, 500, message, "internal_error")

    # -- root and review UI ------------------------------------------------------
    @app.get("/", tags=["health"], summary="Service information")
    async def root():
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "ui": "/ui",
            "health": "/health",
            "ready": "/ready",
        }

    @app.get("/ui", include_in_schema=False)
    async def review_ui():
        page = _STATIC_DIR / "index.html"
        if not page.is_file():
            raise HTTPException(status_code=404, detail="Review UI not installed")
        return FileResponse(page, headers={"Cache-Control": "no-cache"})

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        from fastapi.openapi.utils import get_openapi

        schema = get_openapi(
            title=app.title, version=app.version, description=app.description, routes=app.routes
        )
        schema.setdefault("components", {})["securitySchemes"] = {
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": "Required on /api/v1 routes only when API_KEY is configured.",
            }
        }
        schema["servers"] = [{"url": "/", "description": "This server"}]
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
    return app


app = create_app()
