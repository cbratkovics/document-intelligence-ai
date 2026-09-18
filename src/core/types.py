"""Typed contracts shared across ingestion, retrieval, and generation.

Each stage keeps its own score field so that a raw vector distance is never
confused with a lexical score, a fusion score, or a reranker score.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional


class DocumentStatus(str, Enum):
    PENDING = "pending"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class RetrievalMode(str, Enum):
    LEXICAL = "lexical"
    VECTOR = "vector"
    HYBRID = "hybrid"


class RerankStatus(str, Enum):
    APPLIED = "applied"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class AnswerStatus(str, Enum):
    ANSWERED = "answered"
    EXCERPTS_ONLY = "excerpts_only"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNVERIFIED_CITATIONS = "unverified_citations"
    PROVIDER_ERROR = "provider_error"


@dataclass(frozen=True)
class SourceLocation:
    """Where a chunk sits inside the normalized extracted text.

    ``char_start``/``char_end`` are offsets into the normalized extracted text,
    not into the original file bytes. ``page``/``page_end`` are only set for
    formats that have pages (PDF); ``section`` is the nearest preceding
    Markdown heading when available.
    """

    char_start: int
    char_end: int
    page: Optional[int] = None
    page_end: Optional[int] = None
    section: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    doc_id: str
    version: int
    ordinal: int
    text: str
    location: SourceLocation
    text_hash: str


@dataclass
class DocumentRecord:
    doc_id: str
    version: int
    display_filename: str
    extension: str
    content_hash: str
    size_bytes: int
    status: DocumentStatus
    chunk_count: int
    created_at: str
    updated_at: str
    storage_name: Optional[str]
    chunking_config: str
    embedding_identity: Optional[str]
    user_metadata: Dict[str, Any] = field(default_factory=dict)
    page_count: Optional[int] = None
    error: Optional[str] = None

    def to_public_dict(self) -> Dict[str, Any]:
        """Representation returned by the API (no storage paths)."""
        return {
            "doc_id": self.doc_id,
            "version": self.version,
            "filename": self.display_filename,
            "extension": self.extension,
            "content_hash": self.content_hash,
            "size_bytes": self.size_bytes,
            "status": self.status.value,
            "chunk_count": self.chunk_count,
            "page_count": self.page_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "chunking_config": self.chunking_config,
            "embedding_identity": self.embedding_identity,
            "metadata": dict(self.user_metadata),
            "error": self.error,
        }


@dataclass(frozen=True)
class QueryScope:
    """Which documents a request may see.

    ``doc_ids is None`` means the whole corpus. An empty set means *nothing*
    and must never be widened to the whole corpus.
    """

    doc_ids: Optional[FrozenSet[str]] = None

    @classmethod
    def whole_corpus(cls) -> "QueryScope":
        return cls(None)

    @classmethod
    def of(cls, doc_ids) -> "QueryScope":
        return cls(frozenset(doc_ids))

    @property
    def is_empty(self) -> bool:
        return self.doc_ids is not None and len(self.doc_ids) == 0

    def allows(self, doc_id: str) -> bool:
        return self.doc_ids is None or doc_id in self.doc_ids

    def to_dict(self) -> Dict[str, Any]:
        return {"doc_ids": sorted(self.doc_ids) if self.doc_ids is not None else None}


@dataclass
class SearchHit:
    chunk_id: str
    doc_id: str
    version: int
    ordinal: int
    text: str
    display_filename: str
    location: SourceLocation
    user_metadata: Dict[str, Any] = field(default_factory=dict)
    vector_distance: Optional[float] = None
    vector_similarity: Optional[float] = None
    vector_rank: Optional[int] = None
    lexical_score: Optional[float] = None
    lexical_rank: Optional[int] = None
    fusion_score: Optional[float] = None
    fusion_rank: Optional[int] = None  # position after fusion, before any reranking
    rerank_score: Optional[float] = None
    final_rank: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "version": self.version,
            "ordinal": self.ordinal,
            "filename": self.display_filename,
            "text": self.text,
            "location": self.location.to_dict(),
            "metadata": dict(self.user_metadata),
            "scores": {
                "vector_distance": self.vector_distance,
                "vector_similarity": self.vector_similarity,
                "vector_rank": self.vector_rank,
                "lexical_score": self.lexical_score,
                "lexical_rank": self.lexical_rank,
                "fusion_score": self.fusion_score,
                "fusion_rank": self.fusion_rank,
                "rerank_score": self.rerank_score,
            },
            "rank": self.final_rank,
        }


@dataclass
class RetrievalResult:
    hits: List[SearchHit]
    mode_requested: RetrievalMode
    mode_effective: RetrievalMode
    rerank_status: RerankStatus
    reranker: Optional[str]
    scope: QueryScope
    corpus_generation: int
    timings_ms: Dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    candidate_k: int = 0  # candidates requested from each retrieval branch

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode_requested": self.mode_requested.value,
            "mode_effective": self.mode_effective.value,
            "rerank_status": self.rerank_status.value,
            "reranker": self.reranker,
            "scope": self.scope.to_dict(),
            "corpus_generation": self.corpus_generation,
            "candidate_k": self.candidate_k,
            "timings_ms": self.timings_ms,
            "notes": list(self.notes),
        }


@dataclass
class Citation:
    label: str
    chunk_id: str
    doc_id: str
    version: int
    filename: str
    location: SourceLocation
    text: str
    ordinal: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "version": self.version,
            "filename": self.filename,
            "ordinal": self.ordinal,
            "location": self.location.to_dict(),
            "text": self.text,
        }


class IngestionError(Exception):
    """Raised when a document cannot be ingested; carries an HTTP-ish code."""

    def __init__(self, message: str, code: str = "invalid_document", status: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


class NotFoundError(Exception):
    pass


class IndexCompatibilityError(Exception):
    """The on-disk vector index was built with a different embedding identity."""
