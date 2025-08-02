from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os
import time
from typing import Optional

from .endpoints import router
from .health import router as health_router
from ..core.config import settings
from ..monitoring.metrics import (
    request_count,
    request_latency,
    active_requests,
    initialize_metrics,
    system_info,
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events"""
    # Startup
    logger.info("Starting Document Intelligence API...")

    # Create necessary directories
    os.makedirs(settings.data_dir, exist_ok=True)
    os.makedirs(settings.log_dir, exist_ok=True)

    # Initialize metrics
    initialize_metrics(app_version=settings.app_version, environment=settings.app_env)

    yield

    # Shutdown
    logger.info("Shutting down Document Intelligence API...")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
## Document Intelligence API

Production-grade document intelligence system using RAG (Retrieval-Augmented Generation) architecture.

### Features
- **Multi-format document processing**: PDF, TXT, Markdown, reStructuredText
- **Advanced search capabilities**: 
  - Vector search with semantic understanding
  - Hybrid search combining vector and keyword (BM25)
  - Cross-encoder reranking for improved relevance
- **Streaming responses** for real-time interaction
- **Comprehensive monitoring** with Prometheus metrics
- **Scalable architecture** with Redis and ChromaDB

### Authentication
Currently using API key authentication. Pass your API key in the `X-API-Key` header.

### Rate Limits
- Document upload: 10 MB max file size
- Search queries: 100 requests per minute
- Document processing: 50 documents per hour

### Getting Started
1. Upload documents using `/api/v1/documents/upload`
2. Search documents using `/api/v1/search/advanced`
3. Generate answers using `/api/v1/query`

For more information, see the [GitHub repository](https://github.com/cbratkovics/document-intelligence-ai).
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {
            "name": "documents",
            "description": "Document upload, management, and deletion operations",
        },
        {
            "name": "search",
            "description": "Search operations including vector, hybrid, and advanced search",
        },
        {"name": "query", "description": "RAG-based question answering and generation"},
        {"name": "health", "description": "Health checks and system status"},
        {"name": "metrics", "description": "Prometheus metrics and monitoring"},
    ],
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router, prefix="/api/v1")
app.include_router(health_router)

# Add Prometheus metrics endpoint
try:
    from prometheus_client import make_asgi_app

    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)
except ImportError:
    logger.warning("prometheus_client not installed, metrics endpoint disabled")


# Add middleware for automatic metrics collection
@app.middleware("http")
async def track_requests(request: Request, call_next):
    """Middleware to track all HTTP requests"""
    start_time = time.time()
    active_requests.inc()

    try:
        response = await call_next(request)
        status = "success" if response.status_code < 400 else "error"
    except Exception as e:
        status = "error"
        raise
    finally:
        duration = time.time() - start_time

        # Only track API endpoints
        if request.url.path.startswith("/api/"):
            request_count.labels(
                method=request.method, endpoint=request.url.path, status=status
            ).inc()

            request_latency.labels(
                method=request.method, endpoint=request.url.path
            ).observe(duration)

        active_requests.dec()

    return response


@app.get("/", tags=["health"], summary="Root endpoint")
async def root():
    """Root endpoint with API information"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "operational",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", tags=["health"], summary="Health check")
async def health_check():
    """
    Health check endpoint.

    Returns the current health status of the API and its dependencies.
    """
    try:
        # Check if we can import all necessary modules
        from ..rag.retriever import RAGRetriever
        from ..rag.generator import RAGGenerator

        return {
            "status": "healthy",
            "version": settings.app_version,
            "environment": settings.app_env,
            "services": {
                "api": "operational",
                "embeddings": "operational",
                "vector_store": "operational",
            },
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503, content={"status": "unhealthy", "error": str(e)}
        )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc) if settings.is_development else "An error occurred",
        },
    )


# Custom OpenAPI schema
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    from fastapi.openapi.utils import get_openapi

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )

    # Add security scheme
    openapi_schema["components"]["securitySchemes"] = {
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API key for authentication",
        }
    }

    # Add servers
    openapi_schema["servers"] = [
        {"url": "http://localhost:8000", "description": "Local development server"},
        {
            "url": "https://api.document-intelligence.com",
            "description": "Production server",
        },
    ]

    # Add external docs
    openapi_schema["externalDocs"] = {
        "description": "GitHub Repository",
        "url": "https://github.com/cbratkovics/document-intelligence-ai",
    }

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


# Development-only endpoints
if settings.is_development:

    @app.get("/debug/config")
    async def debug_config():
        """Show current configuration (development only)"""
        return {
            "app_env": settings.app_env,
            "openai_model": settings.openai_model,
            "embedding_model": settings.embedding_model,
            "chunk_size": settings.chunk_size,
            "chunk_overlap": settings.chunk_overlap,
            "search_top_k": settings.search_top_k,
            "similarity_threshold": settings.similarity_threshold,
        }
