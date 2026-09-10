"""Liveness, readiness, and capability reporting.

``/health`` answers as soon as the process runs and reports which optional
capabilities are configured. ``/ready`` checks that storage is reachable and
the indexes agree with the manifest; it returns 503 otherwise. Neither makes
network calls to a provider.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter()
_STARTED = time.monotonic()


@router.get(
    "/health", tags=["health"], summary="Liveness and capabilities", operation_id="health_check"
)
async def health(request: Request) -> Dict[str, Any]:
    settings = request.app.state.settings
    service = getattr(request.app.state, "service", None)
    generator = getattr(request.app.state, "generator", None)
    startup_error = getattr(request.app.state, "startup_error", None)
    payload: Dict[str, Any] = {
        "status": "ok" if service is not None else "degraded",
        "version": settings.app_version,
        "environment": settings.app_env,
        "uptime_seconds": round(time.monotonic() - _STARTED, 1),
        "auth": "api_key" if settings.api_key else "local_mode_no_auth",
        "capabilities": service.capabilities() if service else None,
        "generation_available": bool(generator and generator.generation_available),
        "startup_error": startup_error,
    }
    return payload


@router.get("/ready", tags=["health"], summary="Storage readiness", operation_id="readiness_check")
async def ready(request: Request) -> Dict[str, Any]:
    service = getattr(request.app.state, "service", None)
    if service is None:
        raise HTTPException(
            status_code=503,
            detail={
                "ready": False,
                "reason": getattr(request.app.state, "startup_error", "not started"),
            },
        )
    try:
        report = service.consistency_report()
        stats = service.stats()
    except Exception as exc:
        logger.error("Readiness check failed: %s", exc)
        raise HTTPException(
            status_code=503, detail={"ready": False, "reason": "storage unavailable"}
        )
    ready_flag = bool(report.get("lexical_in_sync")) and report.get("vectors_in_sync", True)
    if not ready_flag:
        raise HTTPException(status_code=503, detail={"ready": False, "consistency": report})
    return {"ready": True, "consistency": report, "stats": stats}
