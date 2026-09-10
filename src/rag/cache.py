"""Bounded exact-match answer cache.

Keys include everything that could change the answer: question, scope, corpus
generation, retrieval configuration, embedding/reranker identity, prompt
version and generation model. A cache entry therefore can never be served for
a different scope or after any document changes. Entries expire by TTL and
the cache is LRU-bounded. This is process-local.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Optional


def make_cache_key(parts: Dict[str, Any]) -> str:
    payload = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AnswerCache:
    def __init__(self, ttl_seconds: int, max_entries: int):
        self.ttl = max(0, int(ttl_seconds))
        self.max_entries = max(0, int(max_entries))
        self._data: "OrderedDict[str, tuple[float, Dict[str, Any]]]" = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    @property
    def enabled(self) -> bool:
        return self.ttl > 0 and self.max_entries > 0

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        now = time.monotonic()
        with self._lock:
            item = self._data.get(key)
            if item is None:
                self.misses += 1
                return None
            expires_at, value = item
            if expires_at <= now:
                del self._data[key]
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: str, value: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._data[key] = (time.monotonic() + self.ttl, value)
            self._data.move_to_end(key)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
