"""Prometheus metrics with bounded label cardinality.

Labels use route templates (``/api/v1/documents/{doc_id}``), never document
IDs or query text. Metrics are optional: the app works without the
``prometheus_client`` package.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Counter, Gauge, Histogram, Info

    AVAILABLE = True
except ImportError:  # pragma: no cover
    AVAILABLE = False

request_count: Any = None
request_latency: Any = None
active_requests: Any = None
stage_latency: Any = None
stage_outcomes: Any = None
documents_ready: Any = None
chunks_active: Any = None
system_info: Any = None

if AVAILABLE:
    request_count = Counter(
        "docintel_requests_total", "HTTP requests", ["method", "route", "status"]
    )
    request_latency = Histogram(
        "docintel_request_duration_seconds", "HTTP request latency", ["method", "route"]
    )
    active_requests = Gauge("docintel_active_requests", "In-flight HTTP requests")
    stage_latency = Histogram(
        "docintel_stage_duration_seconds",
        "Pipeline stage latency",
        ["stage"],
        buckets=(0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
    )
    stage_outcomes = Counter(
        "docintel_stage_outcomes_total", "Pipeline stage outcomes", ["stage", "outcome"]
    )
    documents_ready = Gauge("docintel_documents_ready", "Documents with status READY")
    chunks_active = Gauge("docintel_chunks_active", "Chunks of READY documents")
    system_info = Info("docintel_build", "Build information")


def record_request(method: str, route: str, status_code: int, duration: float) -> None:
    if not AVAILABLE:
        return
    status = (
        "2xx"
        if status_code < 300
        else "3xx"
        if status_code < 400
        else "4xx"
        if status_code < 500
        else "5xx"
    )
    request_count.labels(method=method, route=route, status=status).inc()
    request_latency.labels(method=method, route=route).observe(duration)


@contextmanager
def track_stage(stage: str) -> Iterator[None]:
    start = time.perf_counter()
    outcome = "ok"
    try:
        yield
    except Exception:
        outcome = "error"
        raise
    finally:
        if AVAILABLE:
            stage_latency.labels(stage=stage).observe(time.perf_counter() - start)
            stage_outcomes.labels(stage=stage, outcome=outcome).inc()


def update_index_gauges(documents: int, chunks: int) -> None:
    if AVAILABLE:
        documents_ready.set(documents)
        chunks_active.set(chunks)


def initialize_metrics(
    app_version: str, environment: str, embedding: Optional[str], generation: str
) -> None:
    if AVAILABLE:
        system_info.info(
            {
                "version": app_version,
                "environment": environment,
                "embedding_provider": embedding or "none",
                "generation_provider": generation,
            }
        )
