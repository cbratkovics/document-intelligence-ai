"""Document lifecycle service: ingest, list, inspect, delete.

Supported process model: one API process owning one corpus. Writes are
serialized; the manifest is authoritative; the lexical index is rebuilt from
the manifest after every committed change; vectors live in Chroma when an
embedding provider is configured.

Ingestion is staged: file -> manifest (INDEXING) -> chunks -> vectors ->
commit (READY). Any failure rolls the staged state back and, for new
documents, leaves a FAILED record that is never searchable. Replacement keeps
the previous version searchable until the new one is committed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..core.chunking import Chunk, chunk_text
from ..core.config import Settings
from ..core.embeddings import EmbeddingProvider, build_embedding_provider
from ..core.lexical import LexicalEntry, LexicalIndex
from ..core.manifest import Manifest, make_chunk_id, utcnow_iso
from ..core.types import ChunkRecord, DocumentRecord, DocumentStatus, IngestionError, NotFoundError
from ..core.vector_store import VectorStore
from ..utils.document_loader import (
    UploadStorage,
    content_hash,
    detect_extension,
    extract_document,
    normalize_display_filename,
)
from .cache import AnswerCache

logger = logging.getLogger(__name__)

RESERVED_METADATA_KEYS = {
    "doc_id",
    "version",
    "chunk_id",
    "ordinal",
    "filename",
    "status",
    "content_hash",
    "source",
    "storage_name",
    "location",
    "owner",
}


def validate_user_metadata(
    metadata: Optional[Dict[str, Any]], *, max_keys: int, max_value_length: int
) -> Dict[str, Any]:
    """Accept only flat, scalar user metadata that does not shadow reserved fields."""
    if metadata is None:
        return {}
    if not isinstance(metadata, dict):
        raise IngestionError("metadata must be a JSON object", code="invalid_metadata")
    if len(metadata) > max_keys:
        raise IngestionError(f"metadata may have at most {max_keys} keys", code="invalid_metadata")
    clean: Dict[str, Any] = {}
    for key, value in metadata.items():
        if not isinstance(key, str) or not key or len(key) > 64:
            raise IngestionError("metadata keys must be non-empty strings", code="invalid_metadata")
        if key in RESERVED_METADATA_KEYS:
            raise IngestionError(f"metadata key '{key}' is reserved", code="invalid_metadata")
        if isinstance(value, bool) or value is None:
            clean[key] = value
        elif isinstance(value, (int, float)):
            clean[key] = value
        elif isinstance(value, str):
            if len(value) > max_value_length:
                raise IngestionError(
                    f"metadata value for '{key}' exceeds {max_value_length} characters",
                    code="invalid_metadata",
                )
            clean[key] = value
        else:
            raise IngestionError(
                f"metadata value for '{key}' must be a string, number, boolean or null",
                code="invalid_metadata",
            )
    return clean


@dataclass
class IngestResult:
    record: DocumentRecord
    created: bool
    duplicate_of: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    timings_ms: Dict[str, float] = field(default_factory=dict)


@dataclass
class DeleteResult:
    doc_id: str
    removed_chunks: int
    removed_vectors: int
    file_removed: bool


class DocumentService:
    def __init__(
        self,
        settings: Settings,
        *,
        manifest: Manifest,
        storage: UploadStorage,
        lexical: LexicalIndex,
        answer_cache: AnswerCache,
        embedder: Optional[EmbeddingProvider],
        vector_store: Optional[VectorStore],
    ):
        self.settings = settings
        self.manifest = manifest
        self.storage = storage
        self.lexical = lexical
        self.answer_cache = answer_cache
        self.embedder = embedder
        self.vector_store = vector_store
        self._write_lock = asyncio.Lock()
        self.rebuild_lexical()

    # -- construction ------------------------------------------------------
    @classmethod
    def from_settings(cls, settings: Settings) -> "DocumentService":
        embedder = build_embedding_provider(settings)
        if settings.storage_mode == "ephemeral":
            manifest = Manifest.in_memory()
            persist_dir = None
        else:
            manifest = Manifest.open(settings.manifest_path)
            persist_dir = settings.index_dir
        storage = UploadStorage(settings.uploads_dir)
        vector_store = None
        if embedder is not None:
            vector_store = VectorStore(
                embedding_identity=embedder.identity,
                collection_name=settings.chroma_collection_name,
                persist_dir=persist_dir,
            )
        return cls(
            settings,
            manifest=manifest,
            storage=storage,
            lexical=LexicalIndex(),
            answer_cache=AnswerCache(
                settings.answer_cache_ttl_seconds, settings.answer_cache_max_entries
            ),
            embedder=embedder,
            vector_store=vector_store,
        )

    def close(self) -> None:
        self.manifest.close()

    # -- capabilities --------------------------------------------------------
    @property
    def dense_available(self) -> bool:
        return self.embedder is not None and self.vector_store is not None

    def capabilities(self) -> Dict[str, Any]:
        return {
            "storage_mode": self.settings.storage_mode,
            "persistent": self.manifest.path is not None,
            "embedding_provider": self.settings.resolved_embedding_provider,
            "embedding_identity": self.embedder.identity if self.embedder else None,
            "embedding_semantic": bool(self.embedder and self.embedder.semantic),
            "dense_retrieval": self.dense_available,
            "lexical_retrieval": True,
            "reranker_mode": self.settings.reranker_mode,
            "generation_provider": self.settings.resolved_generation_provider,
            "chunking_config": self.settings.chunking_config_id,
            "supported_extensions": [".txt", ".md", ".rst", ".pdf"],
        }

    def stats(self) -> Dict[str, Any]:
        docs = self.manifest.list_documents()
        return {
            "documents": len(docs),
            "documents_ready": sum(1 for d in docs if d.status == DocumentStatus.READY),
            "active_chunks": self.manifest.active_chunk_count(),
            "lexical_entries": self.lexical.size,
            "vectors": self.vector_store.count() if self.vector_store else None,
            "corpus_generation": self.manifest.corpus_generation(),
            "answer_cache_entries": len(self.answer_cache),
        }

    # -- lexical -------------------------------------------------------------
    def rebuild_lexical(self) -> None:
        entries = [
            LexicalEntry(chunk_id=c.chunk_id, doc_id=c.doc_id, text=c.text)
            for c in self.manifest.iter_active_chunks()
        ]
        self.lexical.rebuild(entries, self.manifest.corpus_generation())

    def _commit_corpus_change(self) -> None:
        self.manifest.bump_generation()
        self.rebuild_lexical()
        self.answer_cache.clear()

    # -- reads -----------------------------------------------------------------
    def get_document(self, doc_id: str) -> DocumentRecord:
        record = self.manifest.get_document(doc_id)
        if record is None or record.status == DocumentStatus.DELETED:
            raise NotFoundError(doc_id)
        return record

    def list_documents(self) -> List[DocumentRecord]:
        return [d for d in self.manifest.list_documents() if d.status != DocumentStatus.DELETED]

    def get_chunks(self, doc_id: str, *, offset: int = 0, limit: int = 50) -> List[ChunkRecord]:
        record = self.get_document(doc_id)
        return self.manifest.get_chunks(doc_id, record.version, offset=offset, limit=limit)

    # -- ingestion ---------------------------------------------------------------
    async def ingest(
        self,
        filename: Optional[str],
        content: bytes,
        user_metadata: Optional[Dict[str, Any]] = None,
        *,
        replace_doc_id: Optional[str] = None,
    ) -> IngestResult:
        settings = self.settings
        display_name = normalize_display_filename(filename, settings.max_filename_length)
        extension = detect_extension(display_name)
        if len(content) > settings.max_upload_size:
            raise IngestionError(
                f"File exceeds the {settings.max_upload_size} byte limit",
                code="too_large",
                status=413,
            )
        metadata = validate_user_metadata(
            user_metadata,
            max_keys=settings.max_metadata_keys,
            max_value_length=settings.max_metadata_value_length,
        )
        digest = content_hash(content)

        async with self._write_lock:
            existing: Optional[DocumentRecord] = None
            if replace_doc_id is not None:
                existing = self.manifest.get_document(replace_doc_id)
                if existing is None or existing.status == DocumentStatus.DELETED:
                    raise NotFoundError(replace_doc_id)
                if existing.status == DocumentStatus.READY and existing.content_hash == digest:
                    return IngestResult(existing, created=False, duplicate_of=existing.doc_id)
            else:
                for candidate in self.manifest.find_by_hash(digest):
                    if candidate.status == DocumentStatus.READY:
                        return IngestResult(candidate, created=False, duplicate_of=candidate.doc_id)
                    if candidate.status in (DocumentStatus.FAILED, DocumentStatus.INDEXING):
                        existing = candidate  # retry under the same identity
                        break

            timings: Dict[str, float] = {}
            t0 = time.perf_counter()
            extracted = await asyncio.to_thread(
                extract_document,
                display_name,
                content,
                max_extracted_chars=settings.max_extracted_chars,
                max_pdf_pages=settings.max_pdf_pages,
            )
            timings["extract"] = (time.perf_counter() - t0) * 1000

            t0 = time.perf_counter()
            chunks: List[Chunk] = await asyncio.to_thread(
                chunk_text,
                extracted.text,
                chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap,
                max_chunks=settings.max_chunks_per_document,
                pages=extracted.pages,
                extension=extension,
            )
            timings["chunk"] = (time.perf_counter() - t0) * 1000
            if not chunks:
                raise IngestionError("Document produced no chunks", code="no_text")

            if existing is None:
                doc_id = uuid.uuid4().hex
                version = 1
                previous_version = None
                previous_storage = None
            else:
                doc_id = existing.doc_id
                version = existing.version + 1
                previous_version = (
                    existing.version if existing.status == DocumentStatus.READY else None
                )
                previous_storage = existing.storage_name
                if previous_version is None:
                    # Failed or interrupted earlier attempt: clear its remains.
                    self._purge_versions(doc_id, keep_version=None)

            storage_name = await asyncio.to_thread(
                self.storage.save, doc_id, version, extension, content
            )
            now = utcnow_iso()
            record = DocumentRecord(
                doc_id=doc_id,
                version=version,
                display_filename=display_name,
                extension=extension,
                content_hash=digest,
                size_bytes=len(content),
                status=DocumentStatus.INDEXING,
                chunk_count=0,
                created_at=existing.created_at if existing else now,
                updated_at=now,
                storage_name=storage_name,
                chunking_config=settings.chunking_config_id,
                embedding_identity=self.embedder.identity if self.embedder else None,
                user_metadata=metadata,
                page_count=extracted.page_count,
            )
            if existing is None or previous_version is None:
                self.manifest.upsert_document(record)
            # For replacement, the row keeps the old READY version until commit.

            chunk_records = [
                ChunkRecord(
                    chunk_id=make_chunk_id(doc_id, version, c.ordinal),
                    doc_id=doc_id,
                    version=version,
                    ordinal=c.ordinal,
                    text=c.text,
                    location=c.location,
                    text_hash=c.text_hash,
                )
                for c in chunks
            ]
            try:
                self.manifest.replace_chunks(doc_id, version, chunk_records)
                if self.embedder is not None and self.vector_store is not None:
                    t0 = time.perf_counter()
                    vectors = await asyncio.to_thread(
                        self.embedder.embed_documents, [c.text for c in chunk_records]
                    )
                    timings["embed"] = (time.perf_counter() - t0) * 1000
                    if len(vectors) != len(chunk_records):
                        raise RuntimeError("embedding count mismatch")
                    t0 = time.perf_counter()
                    await asyncio.to_thread(
                        self.vector_store.upsert,
                        [c.chunk_id for c in chunk_records],
                        vectors,
                        [
                            {"doc_id": doc_id, "version": version, "ordinal": c.ordinal}
                            for c in chunk_records
                        ],
                    )
                    timings["index_vectors"] = (time.perf_counter() - t0) * 1000
                    present = self.vector_store.has_ids([c.chunk_id for c in chunk_records])
                    missing = [cid for cid, ok in present.items() if not ok]
                    if missing:
                        raise RuntimeError(f"{len(missing)} vectors missing after write")
            except Exception as exc:
                logger.error("Ingestion of %s failed: %s", display_name, exc)
                self._rollback_version(doc_id, version, storage_name)
                if previous_version is None:
                    self.manifest.set_status(
                        doc_id, DocumentStatus.FAILED, error=str(exc)[:500], chunk_count=0
                    )
                raise IngestionError(
                    f"Indexing failed: {exc}", code="indexing_failed", status=500
                ) from exc

            # Commit
            record.status = DocumentStatus.READY
            record.chunk_count = len(chunk_records)
            record.updated_at = utcnow_iso()
            self.manifest.upsert_document(record)
            if previous_version is not None:
                self._purge_versions(doc_id, keep_version=version)
                if previous_storage and previous_storage != storage_name:
                    self.storage.delete(previous_storage)
            t0 = time.perf_counter()
            self._commit_corpus_change()
            timings["index_lexical"] = (time.perf_counter() - t0) * 1000
            logger.info(
                "Indexed %s as %s v%d (%d chunks)",
                display_name,
                doc_id,
                version,
                len(chunk_records),
            )
            return IngestResult(
                record, created=True, warnings=extracted.warnings, timings_ms=timings
            )

    def _rollback_version(self, doc_id: str, version: int, storage_name: Optional[str]) -> None:
        try:
            self.manifest.delete_chunks(doc_id, version)
        except Exception as exc:  # pragma: no cover
            logger.error("Rollback: could not delete chunks: %s", exc)
        if self.vector_store is not None:
            try:
                self.vector_store.delete_document(doc_id, version)
            except Exception as exc:  # pragma: no cover
                logger.error("Rollback: could not delete vectors: %s", exc)
        try:
            self.storage.delete(storage_name)
        except Exception as exc:  # pragma: no cover
            logger.error("Rollback: could not delete file: %s", exc)

    def _purge_versions(self, doc_id: str, keep_version: Optional[int]) -> None:
        """Remove chunks/vectors of every version except ``keep_version``."""
        if self.vector_store is not None:
            stale = [
                cid
                for cid in self.vector_store.ids_for_document(doc_id)
                if keep_version is None or f":v{keep_version}:" not in cid
            ]
            if stale:
                self.vector_store.delete_ids(stale)
        if keep_version is None:
            self.manifest.delete_chunks(doc_id)
            return
        versions = {
            int(cid.split(":v")[1].split(":")[0])
            for cid in self.manifest.chunk_ids(doc_id)
            if f":v{keep_version}:" not in cid
        }
        for version in versions:
            self.manifest.delete_chunks(doc_id, version)

    # -- deletion -------------------------------------------------------------
    async def delete_document(self, doc_id: str) -> DeleteResult:
        async with self._write_lock:
            record = self.manifest.get_document(doc_id)
            if record is None:
                raise NotFoundError(doc_id)
            # Mark first so retrieval excludes the document even if a later step fails.
            self.manifest.set_status(doc_id, DocumentStatus.DELETED)
            self.answer_cache.clear()
            removed_vectors = 0
            try:
                if self.vector_store is not None:
                    removed_vectors = await asyncio.to_thread(
                        self.vector_store.delete_document, doc_id
                    )
                    remaining = self.vector_store.ids_for_document(doc_id)
                    if remaining:
                        raise RuntimeError(f"{len(remaining)} vectors still present")
            except Exception as exc:
                self.manifest.set_status(
                    doc_id, DocumentStatus.DELETED, error=f"vector deletion incomplete: {exc}"
                )
                self._commit_corpus_change()
                raise IngestionError(
                    "Deletion incomplete: vector index removal failed; retry the request",
                    code="deletion_incomplete",
                    status=500,
                ) from exc
            removed_chunks = self.manifest.delete_chunks(doc_id)
            file_removed = self.storage.delete(record.storage_name)
            self.manifest.delete_document_rows(doc_id)
            self._commit_corpus_change()
            logger.info("Deleted document %s (%d chunks)", doc_id, removed_chunks)
            return DeleteResult(doc_id, removed_chunks, removed_vectors, file_removed)

    async def clear_all(self) -> int:
        async with self._write_lock:
            records = self.manifest.list_documents()
            for record in records:
                self.manifest.set_status(record.doc_id, DocumentStatus.DELETED)
            self.answer_cache.clear()
            if self.vector_store is not None:
                await asyncio.to_thread(self.vector_store.reset)
            for record in records:
                self.storage.delete(record.storage_name)
            self.manifest.clear()
            self._commit_corpus_change()
            return len(records)

    # -- consistency ---------------------------------------------------------------
    def consistency_report(self) -> Dict[str, Any]:
        """Compare manifest, vector index and lexical index counts."""
        active = self.manifest.active_chunk_count()
        report: Dict[str, Any] = {
            "manifest_active_chunks": active,
            "lexical_entries": self.lexical.size,
            "lexical_in_sync": self.lexical.size == active
            and self.lexical.generation == self.manifest.corpus_generation(),
        }
        if self.vector_store is not None:
            report["vector_count"] = self.vector_store.count()
            report["vectors_in_sync"] = report["vector_count"] == active
        return report

    def describe_config(self) -> str:
        return json.dumps(self.capabilities(), sort_keys=True)
