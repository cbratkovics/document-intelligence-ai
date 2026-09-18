"""Request and response models for the HTTP API."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

RetrievalModeName = Literal["lexical", "vector", "hybrid"]


class SearchRequest(BaseModel):
    """Retrieval without generation. Unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1, max_length=4000, description="Query text")
    top_k: Optional[int] = Field(default=None, ge=1, description="Results to return")
    mode: RetrievalModeName = Field(
        default="hybrid",
        description="lexical (BM25), vector (dense), or hybrid (RRF of both). "
        "hybrid degrades to lexical, and says so, when no embedding provider is configured.",
    )
    doc_ids: Optional[List[str]] = Field(
        default=None,
        max_length=50,
        description="Restrict retrieval to these documents. An empty list matches nothing.",
    )
    alpha: float = Field(default=0.5, ge=0.0, le=1.0, description="Dense weight in hybrid fusion")
    use_reranker: bool = Field(
        default=False, description="Rerank the candidate pool with the configured reranker"
    )


class QueryRequest(SearchRequest):
    """Retrieval plus grounded answer generation."""

    generate: bool = Field(
        default=True,
        description="When false, or when no generation provider is configured, "
        "return supporting excerpts instead of a generated answer.",
    )


class JudgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=1, max_length=4000)
    answer: str = Field(..., min_length=1, max_length=20000)
    context: str = Field(..., min_length=1, max_length=40000)


class DocumentResponse(BaseModel):
    doc_id: str
    version: int
    filename: str
    extension: str
    content_hash: str
    size_bytes: int
    status: str
    chunk_count: int
    page_count: Optional[int] = None
    created_at: str
    updated_at: str
    chunking_config: str
    embedding_identity: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class UploadResponse(BaseModel):
    document: DocumentResponse
    created: bool
    duplicate_of: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    timings_ms: Dict[str, float] = Field(default_factory=dict)
    evicted: List[str] = Field(
        default_factory=list,
        description="Documents removed (oldest first) to stay within MAX_DOCUMENTS",
    )


class DeleteResponse(BaseModel):
    doc_id: str
    status: Literal["deleted"]
    removed_chunks: int
    removed_vectors: int
    file_removed: bool


class ErrorResponse(BaseModel):
    error: str
    code: Optional[str] = None
    request_id: Optional[str] = None
