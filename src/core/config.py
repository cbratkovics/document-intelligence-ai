"""Application settings.

All configuration is read from environment variables (and an optional ``.env``
file). Nothing here touches the filesystem, opens network connections, or loads
models: settings are plain data so that importing the application is free of
side effects.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

EmbeddingProviderName = Literal["auto", "none", "openai", "local", "hash"]
GenerationProviderName = Literal["auto", "none", "openai"]
RerankerMode = Literal["none", "heuristic", "cross_encoder", "llm"]
StorageMode = Literal["persistent", "ephemeral"]


class Settings(BaseSettings):
    """Runtime configuration.

    Values are validated once at startup. ``resolved_*`` properties expose the
    effective provider after ``auto`` resolution so that health endpoints and
    logs can report what actually runs.
    """

    model_config = SettingsConfigDict(
        env_file=os.environ.get("APP_ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Document Intelligence RAG System"
    app_version: str = "0.2.0"
    app_env: Literal["development", "testing", "production"] = "development"
    log_level: str = "INFO"

    # Access control. When ``api_key`` is unset the API runs in local mode:
    # every endpoint is open, which is only appropriate on a trusted machine.
    api_key: Optional[str] = None
    cors_origins: str = ""

    # Storage
    storage_mode: StorageMode = "persistent"
    data_dir: str = "./data"
    chroma_collection_name: str = "documents"

    # Embeddings (dense retrieval). ``auto`` selects ``openai`` when an OpenAI
    # key is configured and ``none`` (lexical-only retrieval) otherwise.
    embedding_provider: EmbeddingProviderName = "auto"
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    openai_embedding_model: str = "text-embedding-3-small"
    openai_timeout_seconds: float = 60.0
    local_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    allow_model_download: bool = False

    # Generation
    generation_provider: GenerationProviderName = "auto"
    openai_model: str = "gpt-4o-mini"
    generation_max_tokens: int = 600
    generation_temperature: float = 0.0
    generation_concurrency: int = 4
    prompt_version: str = "grounded-v1"

    # Reranking. ``cross_encoder`` requires the optional ML dependencies and a
    # prepared local model; ``llm`` requires a generation provider.
    reranker_mode: RerankerMode = "none"
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    cross_encoder_device: str = "cpu"
    llm_rerank_max_candidates: int = 20
    llm_rerank_concurrency: int = 4

    # Ingestion limits
    max_upload_size: int = 10 * 1024 * 1024
    max_filename_length: int = 255
    max_extracted_chars: int = 2_000_000
    max_pdf_pages: int = 500
    max_chunks_per_document: int = 2000
    max_metadata_keys: int = 32
    max_metadata_value_length: int = 512

    # Chunking (character based)
    chunk_size: int = 1000
    chunk_overlap: int = 200

    # Retrieval
    search_top_k: int = 5
    max_top_k: int = 50
    candidate_multiplier: int = 4
    rrf_k: int = 60
    min_similarity: Optional[float] = None
    max_query_chars: int = 2000

    # Context assembly
    max_context_chars: int = 6000
    max_excerpt_chars: int = 1200

    # Answer cache (exact match; 0 disables)
    answer_cache_ttl_seconds: int = 300
    answer_cache_max_entries: int = 256

    metrics_enabled: bool = True

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        value = value.upper()
        if value not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"Unsupported log level: {value}")
        return value

    @model_validator(mode="after")
    def _check_bounds(self) -> "Settings":
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be >= 0 and < chunk_size")
        if self.search_top_k <= 0 or self.max_top_k <= 0:
            raise ValueError("top_k limits must be positive")
        if self.search_top_k > self.max_top_k:
            raise ValueError("search_top_k must not exceed max_top_k")
        if self.max_upload_size <= 0:
            raise ValueError("max_upload_size must be positive")
        if self.api_key is not None and len(self.api_key) < 16:
            raise ValueError("api_key must be at least 16 characters")
        if self.embedding_provider == "openai" and not self.openai_api_key:
            raise ValueError("embedding_provider=openai requires OPENAI_API_KEY")
        if self.generation_provider == "openai" and not self.openai_api_key:
            raise ValueError("generation_provider=openai requires OPENAI_API_KEY")
        return self

    # Derived paths -------------------------------------------------------
    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def uploads_dir(self) -> Path:
        return self.data_path / "uploads"

    @property
    def index_dir(self) -> Path:
        return self.data_path / "index"

    @property
    def manifest_path(self) -> Path:
        return self.data_path / "manifest.sqlite3"

    # Resolved modes ------------------------------------------------------
    @property
    def resolved_embedding_provider(self) -> str:
        if self.embedding_provider == "auto":
            return "openai" if self.openai_api_key else "none"
        return self.embedding_provider

    @property
    def resolved_generation_provider(self) -> str:
        if self.generation_provider == "auto":
            return "openai" if self.openai_api_key else "none"
        return self.generation_provider

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def chunking_config_id(self) -> str:
        """Identity of the chunking configuration used when indexing."""
        return f"chars:v2:size={self.chunk_size}:overlap={self.chunk_overlap}"


@lru_cache()
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()


def reset_settings_cache() -> None:
    """Clear the cached settings (used by tests that change the environment)."""
    get_settings.cache_clear()
