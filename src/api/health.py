"""
Health check endpoint for the Document Intelligence AI application.
Used by Docker health checks and load balancers.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging
import time
import os
from pathlib import Path

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint that verifies system components are working.

    Returns:
        Dict containing health status and component information
    """
    start_time = time.time()

    health_status = {
        "status": "healthy",
        "timestamp": int(time.time()),
        "version": "1.0.0",
        "uptime": get_uptime(),
        "components": {},
        "response_time_ms": 0,
    }

    try:
        # Check basic system health
        health_status["components"]["system"] = check_system_health()

        # Check model initialization status
        health_status["components"]["models"] = check_model_status()

        # Check external dependencies
        health_status["components"]["dependencies"] = await check_dependencies()

        # Determine overall status
        component_statuses = [
            comp.get("status", "unknown")
            for comp in health_status["components"].values()
        ]

        if "unhealthy" in component_statuses:
            health_status["status"] = "unhealthy"
        elif "degraded" in component_statuses:
            health_status["status"] = "degraded"

        # Calculate response time
        health_status["response_time_ms"] = round((time.time() - start_time) * 1000, 2)

        return health_status

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


def get_uptime() -> float:
    """Get system uptime in seconds"""
    try:
        with open("/proc/uptime", "r") as f:
            uptime_seconds = float(f.readline().split()[0])
        return uptime_seconds
    except (FileNotFoundError, ValueError):
        # Fallback for non-Linux systems
        return 0.0


def check_system_health() -> Dict[str, Any]:
    """Check basic system health metrics"""
    try:
        # Check disk space
        disk_usage = get_disk_usage()

        # Check memory (if available)
        memory_info = get_memory_info()

        status = "healthy"
        issues = []

        # Check disk space (warn if > 90% full)
        if disk_usage and disk_usage > 0.9:
            status = "degraded"
            issues.append(f"Disk usage high: {disk_usage:.1%}")

        return {
            "status": status,
            "disk_usage": disk_usage,
            "memory_info": memory_info,
            "issues": issues,
        }

    except Exception as e:
        logger.warning(f"System health check failed: {e}")
        return {"status": "unknown", "error": str(e)}


def get_disk_usage() -> float:
    """Get disk usage percentage"""
    try:
        import shutil

        total, used, free = shutil.disk_usage("/app")
        return used / total if total > 0 else 0.0
    except Exception:
        return 0.0


def get_memory_info() -> Dict[str, Any]:
    """Get memory information if available"""
    try:
        # Try to read memory info from /proc/meminfo
        with open("/proc/meminfo", "r") as f:
            lines = f.readlines()

        mem_info = {}
        for line in lines:
            if line.startswith(("MemTotal:", "MemAvailable:", "MemFree:")):
                key, value = line.split(":", 1)
                # Convert from kB to MB
                mem_info[key.strip()] = int(value.strip().split()[0]) // 1024

        return mem_info

    except (FileNotFoundError, ValueError):
        return {"status": "unavailable"}


def check_model_status() -> Dict[str, Any]:
    """Check model initialization status"""
    try:
        models_dir = Path(os.getenv("MODEL_CACHE_DIR", "/app/models"))
        status_file = models_dir / "init_status.json"

        if not status_file.exists():
            return {
                "status": "not_initialized",
                "message": "Models not yet initialized",
            }

        import json

        with open(status_file, "r") as f:
            model_status = json.load(f)

        if model_status.get("initialized", False):
            errors = model_status.get("errors", [])
            if errors:
                return {
                    "status": "degraded",
                    "message": f"{len(errors)} model(s) failed to initialize",
                    "errors": errors[:3],  # Show first 3 errors
                }
            else:
                return {
                    "status": "healthy",
                    "message": "All models initialized successfully",
                    "models": len(model_status.get("models", {})),
                }
        else:
            return {
                "status": "initializing",
                "message": "Model initialization in progress",
            }

    except Exception as e:
        logger.warning(f"Model status check failed: {e}")
        return {"status": "unknown", "error": str(e)}


async def check_dependencies() -> Dict[str, Any]:
    """Check external dependencies (Redis, ChromaDB, etc.)"""
    dependencies = {}

    # Check Redis
    try:
        import redis

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        r = redis.from_url(redis_url, decode_responses=True)
        r.ping()
        dependencies["redis"] = {"status": "healthy"}
    except Exception as e:
        dependencies["redis"] = {"status": "unhealthy", "error": str(e)}

    # Check ChromaDB
    try:
        import httpx

        chroma_host = os.getenv("CHROMA_HOST", "localhost")
        chroma_port = os.getenv("CHROMA_PORT", "8000")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://{chroma_host}:{chroma_port}/api/v1/heartbeat", timeout=5.0
            )
            if response.status_code == 200:
                dependencies["chromadb"] = {"status": "healthy"}
            else:
                dependencies["chromadb"] = {
                    "status": "unhealthy",
                    "error": f"HTTP {response.status_code}",
                }
    except Exception as e:
        dependencies["chromadb"] = {"status": "unhealthy", "error": str(e)}

    return dependencies


@router.get("/ready")
async def readiness_check() -> Dict[str, Any]:
    """
    Readiness check endpoint for Kubernetes deployments.
    More strict than health check - ensures all critical components are ready.
    """
    health = await health_check()

    # Check if critical components are healthy
    critical_components = ["models", "dependencies"]
    ready = True

    for component in critical_components:
        if component in health["components"]:
            status = health["components"][component].get("status", "unknown")
            if status in ["unhealthy", "unknown"]:
                ready = False
                break

    if not ready:
        raise HTTPException(status_code=503, detail="Service not ready")

    return {
        "status": "ready",
        "timestamp": int(time.time()),
        "message": "Service is ready to accept requests",
    }
