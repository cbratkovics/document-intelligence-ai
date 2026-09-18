"""In-process sliding-window rate limiter for ``/api`` routes.

Two ceilings: one per client and one global backstop. Both count requests in
a sliding 60 second window. State is process-local, which matches the
single-process deployment boundary.

Client identity: the socket address, unless the request carries a valid API
key *and* the configured client-IP header, in which case the header value is
used. A trusted proxy (the demo frontend) holds the key and forwards the real
visitor address in that header; anonymous callers cannot spoof it.
"""

from __future__ import annotations

import hmac
import math
import threading
import time
from collections import deque
from typing import Deque, Dict, Optional

from fastapi import Request

from ..core.config import Settings

WINDOW_SECONDS = 60.0
_MAX_TRACKED_CLIENTS = 10_000


class SlidingWindowLimiter:
    def __init__(self, per_client: int, global_limit: int, window: float = WINDOW_SECONDS):
        self.per_client = max(0, per_client)
        self.global_limit = max(0, global_limit)
        self.window = window
        self._clients: Dict[str, Deque[float]] = {}
        self._global: Deque[float] = deque()
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.per_client > 0 or self.global_limit > 0

    def _prune(self, bucket: Deque[float], now: float) -> None:
        cutoff = now - self.window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

    def check(self, client_key: str, now: Optional[float] = None) -> Optional[int]:
        """Record one request. Return ``None`` if allowed, else seconds to wait."""
        if not self.enabled:
            return None
        now = time.monotonic() if now is None else now
        with self._lock:
            if self.global_limit:
                self._prune(self._global, now)
                if len(self._global) >= self.global_limit:
                    return max(1, math.ceil(self._global[0] + self.window - now))
            if self.per_client:
                bucket = self._clients.get(client_key)
                if bucket is None:
                    if len(self._clients) >= _MAX_TRACKED_CLIENTS:
                        self._evict_idle(now)
                    bucket = self._clients[client_key] = deque()
                self._prune(bucket, now)
                if len(bucket) >= self.per_client:
                    return max(1, math.ceil(bucket[0] + self.window - now))
                bucket.append(now)
            if self.global_limit:
                self._global.append(now)
        return None

    def _evict_idle(self, now: float) -> None:
        for key in list(self._clients):
            self._prune(self._clients[key], now)
            if not self._clients[key]:
                del self._clients[key]


def client_identity(request: Request, settings: Settings) -> str:
    """Socket address, or the forwarded address when the caller proves it holds the key."""
    socket_host = request.client.host if request.client else "unknown"
    if settings.api_key is None:
        return socket_host
    provided = request.headers.get("X-API-Key") or ""
    if not hmac.compare_digest(provided.encode(), settings.api_key.encode()):
        return socket_host
    forwarded = (request.headers.get(settings.client_ip_header) or "").split(",")[0].strip()
    return forwarded[:128] if forwarded else socket_host
