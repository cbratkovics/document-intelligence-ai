"""Reranking modes.

- ``heuristic``: term-overlap scoring; cheap, no model, weak.
- ``llm``: prompt-based relevance scoring through the generation provider.
  Responses are parsed strictly; a response that is not a number is a failure,
  never a default score. Concurrency and candidate count are bounded.
- ``cross_encoder``: the transformer cross-encoder in
  ``app/reranking/cross_encoder.py`` (optional ML dependencies, local model
  prepared in advance; no download at request time).

Whatever the mode, a failed rerank keeps the original candidate order and is
reported with ``RerankStatus.FAILED`` instead of fabricating scores.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, List, Optional, Protocol, Sequence

from ..core.config import Settings
from ..core.lexical import tokenize
from ..core.types import RerankStatus, SearchHit

logger = logging.getLogger(__name__)


class RerankError(Exception):
    pass


class Reranker(Protocol):
    name: str

    async def score(self, query: str, hits: Sequence[SearchHit]) -> List[float]:
        ...


class HeuristicReranker:
    """Query-term coverage plus exact-phrase bonus. Not a relevance model."""

    name = "heuristic:term-overlap"

    async def score(self, query: str, hits: Sequence[SearchHit]) -> List[float]:
        terms = set(tokenize(query))
        phrase = query.strip().lower()
        scores: List[float] = []
        for hit in hits:
            if not terms:
                scores.append(0.0)
                continue
            doc_terms = set(tokenize(hit.text))
            coverage = len(terms & doc_terms) / len(terms)
            bonus = 0.25 if phrase and phrase in hit.text.lower() else 0.0
            scores.append(min(1.0, coverage + bonus))
        return scores


_SCORE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:/\s*10)?\s*\.?\s*$")


class LLMReranker:
    """Scores each candidate 0-10 with the chat model. Paid per candidate."""

    def __init__(self, chat_client, model_name: str, max_candidates: int, concurrency: int):
        self._client = chat_client
        self.name = f"llm:{model_name}"
        self.max_candidates = max(1, max_candidates)
        self._semaphore = asyncio.Semaphore(max(1, concurrency))

    async def _score_one(self, query: str, text: str) -> float:
        system = (
            "You rate how well a passage answers a query. Reply with a single "
            "number from 0 (irrelevant) to 10 (fully answers). Reply with the "
            "number only."
        )
        user = f"Query:\n{query}\n\nPassage:\n<passage>\n{text[:2000]}\n</passage>"
        async with self._semaphore:
            raw = await self._client.complete(system, user, max_tokens=8, temperature=0.0)
        match = _SCORE_RE.match(raw or "")
        if not match:
            raise RerankError(f"Unparseable relevance score: {raw!r}")
        value = float(match.group(1))
        if value < 0.0 or value > 10.0:
            raise RerankError(f"Relevance score out of range: {value}")
        return value / 10.0

    async def score(self, query: str, hits: Sequence[SearchHit]) -> List[float]:
        if len(hits) > self.max_candidates:
            raise RerankError(
                f"{len(hits)} candidates exceed llm_rerank_max_candidates=" f"{self.max_candidates}"
            )
        return list(await asyncio.gather(*(self._score_one(query, h.text) for h in hits)))


class CrossEncoderAdapter:
    """Lazy adapter around ``app.reranking.cross_encoder.CrossEncoderReranker``."""

    def __init__(self, model_name: str, device: str, allow_download: bool):
        self.name = f"cross_encoder:{model_name}"
        self._model_name = model_name
        self._device = device
        self._allow_download = allow_download
        self._impl: Any = None
        self._lock = asyncio.Lock()

    async def _load(self) -> Any:
        if self._impl is not None:
            return self._impl
        async with self._lock:
            if self._impl is None:
                if not self._allow_download:
                    os.environ.setdefault("HF_HUB_OFFLINE", "1")
                    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
                try:
                    from app.reranking.cross_encoder import CrossEncoderConfig, CrossEncoderReranker
                except ImportError as exc:
                    raise RerankError(
                        "cross_encoder mode needs the optional ML dependencies "
                        "(pip install -r requirements-ml.txt)"
                    ) from exc
                config = CrossEncoderConfig(model_name=self._model_name, device=self._device)

                def construct() -> Any:
                    return CrossEncoderReranker(config)

                try:
                    self._impl = await asyncio.to_thread(construct)
                except Exception as exc:
                    raise RerankError(
                        f"Could not load cross-encoder '{self._model_name}': {exc}. "
                        "Prepare it with `python scripts/setup/init_models.py --reranker`."
                    ) from exc
        return self._impl

    async def score(self, query: str, hits: Sequence[SearchHit]) -> List[float]:
        impl = await self._load()
        docs = [{"id": h.chunk_id, "content": h.text, "score": 0.0} for h in hits]
        results = await asyncio.to_thread(impl.rerank, query, docs, None)
        by_id = {r.doc_id: float(r.rerank_score) for r in results}
        return [by_id[h.chunk_id] for h in hits]


def build_reranker(settings: Settings, chat_client=None) -> Optional[Reranker]:
    mode = settings.reranker_mode
    if mode == "none":
        return None
    if mode == "heuristic":
        return HeuristicReranker()
    if mode == "llm":
        if chat_client is None:
            logger.warning("reranker_mode=llm but no generation provider; reranking unavailable")
            return None
        return LLMReranker(
            chat_client,
            settings.openai_model,
            settings.llm_rerank_max_candidates,
            settings.llm_rerank_concurrency,
        )
    if mode == "cross_encoder":
        return CrossEncoderAdapter(
            settings.cross_encoder_model,
            settings.cross_encoder_device,
            settings.allow_model_download,
        )
    raise ValueError(f"Unknown reranker mode: {mode}")


@dataclass
class RerankOutcome:
    hits: List[SearchHit]
    status: RerankStatus
    reranker: Optional[str]
    error: Optional[str] = None


async def apply_reranker(
    reranker: Optional[Reranker], query: str, hits: Sequence[SearchHit]
) -> RerankOutcome:
    """Rerank the full candidate pool; never drop candidates on failure."""
    hits = list(hits)
    if reranker is None:
        return RerankOutcome(hits, RerankStatus.UNAVAILABLE, None)
    if not hits:
        return RerankOutcome(hits, RerankStatus.APPLIED, reranker.name)
    try:
        scores = await reranker.score(query, hits)
        if len(scores) != len(hits):
            raise RerankError("reranker returned a different number of scores")
    except Exception as exc:
        logger.warning("Reranking failed (%s); keeping original order", exc)
        return RerankOutcome(hits, RerankStatus.FAILED, reranker.name, str(exc))
    for hit, score in zip(hits, scores):
        hit.rerank_score = float(score)
    ordered = sorted(hits, key=lambda h: (-(h.rerank_score or 0.0), h.chunk_id))
    return RerankOutcome(ordered, RerankStatus.APPLIED, reranker.name)
