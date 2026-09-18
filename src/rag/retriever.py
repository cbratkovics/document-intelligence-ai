"""Scoped retrieval over the lexical and dense indexes.

Scope is enforced in *both* candidate generators before fusion, again when
hydrating from the manifest (only READY documents at their current version),
and reranking sees the whole candidate pool before final truncation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List, Optional, Sequence

from ..core.config import Settings
from ..core.lexical import LexicalHit
from ..core.types import (
    DocumentRecord,
    DocumentStatus,
    NotFoundError,
    QueryScope,
    RerankStatus,
    RetrievalMode,
    RetrievalResult,
    SearchHit,
)
from ..core.vector_store import VectorHit
from .hybrid_search import FusedCandidate, FusionConfig, reciprocal_rank_fusion
from .reranker import Reranker, apply_reranker
from .service import DocumentService

logger = logging.getLogger(__name__)


class RetrievalRequestError(ValueError):
    """Client-side request problem (bad top_k, unknown document, etc.)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class Retriever:
    def __init__(
        self, service: DocumentService, settings: Settings, reranker: Optional[Reranker] = None
    ):
        self.service = service
        self.settings = settings
        self.reranker = reranker

    # -- validation ------------------------------------------------------------
    def validate_query(self, query: str) -> str:
        query = (query or "").strip()
        if not query:
            raise RetrievalRequestError("query text must not be empty")
        if len(query) > self.settings.max_query_chars:
            raise RetrievalRequestError(
                f"query text exceeds {self.settings.max_query_chars} characters"
            )
        return query

    def validate_top_k(self, top_k: Optional[int]) -> int:
        if top_k is None:
            return self.settings.search_top_k
        if top_k < 1 or top_k > self.settings.max_top_k:
            raise RetrievalRequestError(f"top_k must be between 1 and {self.settings.max_top_k}")
        return top_k

    def resolve_scope(self, doc_ids: Optional[Sequence[str]]) -> QueryScope:
        """Unknown or non-ready documents are rejected, never silently widened."""
        if doc_ids is None:
            return QueryScope.whole_corpus()
        unique = list(dict.fromkeys(doc_ids))
        for doc_id in unique:
            try:
                record = self.service.get_document(doc_id)
            except NotFoundError:
                raise RetrievalRequestError(f"Unknown document: {doc_id}", status=404)
            if record.status != DocumentStatus.READY:
                raise RetrievalRequestError(
                    f"Document {doc_id} is not ready (status={record.status.value})",
                    status=409,
                )
        return QueryScope.of(unique)

    def resolve_mode(self, requested: RetrievalMode) -> tuple[RetrievalMode, List[str]]:
        notes: List[str] = []
        if (
            requested in (RetrievalMode.VECTOR, RetrievalMode.HYBRID)
            and not self.service.dense_available
        ):
            if requested == RetrievalMode.VECTOR:
                raise RetrievalRequestError(
                    "vector retrieval is unavailable: no embedding provider is configured",
                    status=409,
                )
            notes.append("dense retrieval unavailable; ran lexical-only")
            return RetrievalMode.LEXICAL, notes
        return requested, notes

    # -- retrieval ---------------------------------------------------------------
    async def retrieve(
        self,
        query: str,
        *,
        top_k: Optional[int] = None,
        mode: RetrievalMode = RetrievalMode.HYBRID,
        doc_ids: Optional[Sequence[str]] = None,
        alpha: float = 0.5,
        use_reranker: bool = False,
        candidate_k: Optional[int] = None,
    ) -> RetrievalResult:
        query = self.validate_query(query)
        top_k = self.validate_top_k(top_k)
        if alpha < 0.0 or alpha > 1.0:
            raise RetrievalRequestError("alpha must be within [0, 1]")
        scope = self.resolve_scope(doc_ids)
        effective, notes = self.resolve_mode(mode)
        generation = self.service.manifest.corpus_generation()
        timings: Dict[str, float] = {}

        pool = candidate_k or min(
            max(top_k * self.settings.candidate_multiplier, top_k), self.settings.max_top_k * 4
        )
        if scope.is_empty:
            notes.append("empty document scope; nothing searched")
            return RetrievalResult(
                [],
                mode,
                effective,
                RerankStatus.DISABLED,
                None,
                scope,
                generation,
                timings,
                notes,
                candidate_k=pool,
            )

        lexical_hits: List[LexicalHit] = []
        vector_hits: List[VectorHit] = []
        if effective in (RetrievalMode.LEXICAL, RetrievalMode.HYBRID):
            t0 = time.perf_counter()
            lexical_hits = self.service.lexical.search(query, pool, scope)
            timings["lexical_ms"] = (time.perf_counter() - t0) * 1000
        if effective in (RetrievalMode.VECTOR, RetrievalMode.HYBRID):
            embedder, store = self.service.embedder, self.service.vector_store
            assert embedder is not None and store is not None  # guaranteed by resolve_mode
            t0 = time.perf_counter()
            embedding = await asyncio.to_thread(embedder.embed_query, query)
            timings["embed_query_ms"] = (time.perf_counter() - t0) * 1000
            t0 = time.perf_counter()
            vector_hits = await asyncio.to_thread(store.query, embedding, pool, scope)
            timings["vector_ms"] = (time.perf_counter() - t0) * 1000

        if effective == RetrievalMode.HYBRID:
            if alpha == 1.0:
                notes.append("alpha=1.0: lexical branch carries no weight")
            elif alpha == 0.0:
                notes.append("alpha=0.0: dense branch carries no weight")
            fused = reciprocal_rank_fusion(
                vector_hits,
                lexical_hits,
                FusionConfig.from_alpha(alpha, rrf_k=self.settings.rrf_k),
            )
        elif effective == RetrievalMode.LEXICAL:
            fused = [
                FusedCandidate(
                    h.chunk_id, fusion_score=None, lexical_rank=h.rank, lexical_score=h.score
                )
                for h in lexical_hits
            ]
        else:
            fused = [
                FusedCandidate(
                    h.chunk_id, fusion_score=None, vector_rank=i + 1, vector_distance=h.distance
                )
                for i, h in enumerate(vector_hits)
            ]

        hits = self._hydrate(fused, scope)
        if effective == RetrievalMode.HYBRID:
            for position, hit in enumerate(hits, start=1):
                hit.fusion_rank = position
        if self.settings.min_similarity is not None and effective == RetrievalMode.VECTOR:
            hits = [
                h
                for h in hits
                if h.vector_similarity is not None
                and h.vector_similarity >= self.settings.min_similarity
            ]

        rerank_status = RerankStatus.DISABLED
        reranker_name = None
        if use_reranker:
            t0 = time.perf_counter()
            outcome = await apply_reranker(self.reranker, query, hits)
            timings["rerank_ms"] = (time.perf_counter() - t0) * 1000
            hits = outcome.hits
            rerank_status = outcome.status
            reranker_name = outcome.reranker
            if outcome.status == RerankStatus.UNAVAILABLE:
                notes.append(
                    f"reranking requested but reranker_mode={self.settings.reranker_mode} "
                    "provides no reranker"
                )
            elif outcome.status == RerankStatus.FAILED:
                notes.append(f"reranking failed, original order kept: {outcome.error}")

        hits = hits[:top_k]
        for rank, hit in enumerate(hits, start=1):
            hit.final_rank = rank
        return RetrievalResult(
            hits,
            mode,
            effective,
            rerank_status,
            reranker_name,
            scope,
            generation,
            timings,
            notes,
            candidate_k=pool,
        )

    def _hydrate(self, candidates: Sequence[FusedCandidate], scope: QueryScope) -> List[SearchHit]:
        manifest = self.service.manifest
        chunks = manifest.get_chunks_by_ids([c.chunk_id for c in candidates])
        doc_cache: Dict[str, Optional[DocumentRecord]] = {}
        hits: List[SearchHit] = []
        for cand in candidates:
            chunk = chunks.get(cand.chunk_id)
            if chunk is None:
                continue  # stale vector for a rolled-back or deleted version
            if not scope.allows(chunk.doc_id):
                continue
            if chunk.doc_id not in doc_cache:
                doc_cache[chunk.doc_id] = manifest.get_document(chunk.doc_id)
            record = doc_cache[chunk.doc_id]
            if (
                record is None
                or record.status != DocumentStatus.READY
                or record.version != chunk.version
            ):
                continue
            similarity = None
            if cand.vector_distance is not None:
                similarity = 1.0 - cand.vector_distance  # cosine space only
            hits.append(
                SearchHit(
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    version=chunk.version,
                    ordinal=chunk.ordinal,
                    text=chunk.text,
                    display_filename=record.display_filename,
                    location=chunk.location,
                    user_metadata=dict(record.user_metadata),
                    vector_distance=cand.vector_distance,
                    vector_similarity=similarity,
                    vector_rank=cand.vector_rank,
                    lexical_score=cand.lexical_score,
                    lexical_rank=cand.lexical_rank,
                    fusion_score=cand.fusion_score,
                )
            )
        return hits
