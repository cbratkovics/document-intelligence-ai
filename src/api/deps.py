"""FastAPI dependencies: service access and API-key enforcement."""

from __future__ import annotations

import hmac
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader

from ..core.config import Settings
from ..rag.generator import Generator
from ..rag.service import DocumentService

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_service(request: Request) -> DocumentService:
    service = getattr(request.app.state, "service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Document service is not available")
    return service


def get_generator(request: Request) -> Generator:
    generator = getattr(request.app.state, "generator", None)
    if generator is None:
        raise HTTPException(status_code=503, detail="Generator is not available")
    return generator


def _check_key(settings: Settings, provided: Optional[str]) -> None:
    expected = settings.api_key
    if expected is None:
        return  # local mode: no key configured
    if not provided or not hmac.compare_digest(provided.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


async def require_api_key(
    settings: Settings = Depends(get_settings_dep),
    provided: Optional[str] = Depends(api_key_header),
) -> None:
    """Enforced on every /api/v1 route when API_KEY is configured."""
    _check_key(settings, provided)


async def require_configured_key(
    settings: Settings = Depends(get_settings_dep),
    provided: Optional[str] = Depends(api_key_header),
) -> None:
    """Destructive bulk operations require a configured *and* matching key."""
    if settings.api_key is None:
        raise HTTPException(
            status_code=403,
            detail="This operation requires API_KEY to be configured on the server",
        )
    _check_key(settings, provided)
