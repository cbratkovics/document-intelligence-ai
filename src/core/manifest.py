"""Authoritative document/chunk manifest backed by SQLite.

The manifest is the source of truth for what is indexed: document identity and
version, lifecycle status, content hash, chunking/embedding configuration, and
the ordered chunk texts with source locations. Sparse (BM25) state is rebuilt
from it, summaries read from it, and deletion enumerates from it.

Single-process use is assumed. Access is serialized with a lock; SQLite runs in
WAL mode so a crash cannot leave a half-written manifest.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from .types import ChunkRecord, DocumentRecord, DocumentStatus, SourceLocation

_SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    display_filename TEXT NOT NULL,
    extension TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    status TEXT NOT NULL,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    page_count INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    storage_name TEXT,
    chunking_config TEXT NOT NULL,
    embedding_identity TEXT,
    user_metadata TEXT NOT NULL DEFAULT '{}',
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    ordinal INTEGER NOT NULL,
    text TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    page INTEGER,
    page_end INTEGER,
    section TEXT
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id, version, ordinal);
"""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_chunk_id(doc_id: str, version: int, ordinal: int) -> str:
    return f"{doc_id}:v{version}:{ordinal:05d}"


class Manifest:
    """SQLite-backed manifest. Use ``Manifest.open`` or ``Manifest.in_memory``."""

    def __init__(self, path: Optional[Path]):
        self._path = path
        target = str(path) if path is not None else ":memory:"
        self._conn = sqlite3.connect(target, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            if path is not None:
                self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(_SCHEMA)
            self._conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
                (str(_SCHEMA_VERSION),),
            )
            self._conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES ('corpus_generation', '0')"
            )

    @classmethod
    def open(cls, path: Path) -> "Manifest":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        return cls(Path(path))

    @classmethod
    def in_memory(cls) -> "Manifest":
        return cls(None)

    @property
    def path(self) -> Optional[Path]:
        return self._path

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- meta --------------------------------------------------------------
    def get_meta(self, key: str) -> Optional[str]:
        with self._lock:
            row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def corpus_generation(self) -> int:
        return int(self.get_meta("corpus_generation") or 0)

    def bump_generation(self) -> int:
        with self._lock:
            new = self.corpus_generation() + 1
            self.set_meta("corpus_generation", str(new))
            return new

    # -- documents ---------------------------------------------------------
    @staticmethod
    def _row_to_document(row: sqlite3.Row) -> DocumentRecord:
        return DocumentRecord(
            doc_id=row["doc_id"],
            version=int(row["version"]),
            display_filename=row["display_filename"],
            extension=row["extension"],
            content_hash=row["content_hash"],
            size_bytes=int(row["size_bytes"]),
            status=DocumentStatus(row["status"]),
            chunk_count=int(row["chunk_count"]),
            page_count=row["page_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            storage_name=row["storage_name"],
            chunking_config=row["chunking_config"],
            embedding_identity=row["embedding_identity"],
            user_metadata=json.loads(row["user_metadata"] or "{}"),
            error=row["error"],
        )

    def upsert_document(self, record: DocumentRecord) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO documents (
                    doc_id, version, display_filename, extension, content_hash,
                    size_bytes, status, chunk_count, page_count, created_at,
                    updated_at, storage_name, chunking_config, embedding_identity,
                    user_metadata, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET
                    version = excluded.version,
                    display_filename = excluded.display_filename,
                    extension = excluded.extension,
                    content_hash = excluded.content_hash,
                    size_bytes = excluded.size_bytes,
                    status = excluded.status,
                    chunk_count = excluded.chunk_count,
                    page_count = excluded.page_count,
                    updated_at = excluded.updated_at,
                    storage_name = excluded.storage_name,
                    chunking_config = excluded.chunking_config,
                    embedding_identity = excluded.embedding_identity,
                    user_metadata = excluded.user_metadata,
                    error = excluded.error
                """,
                (
                    record.doc_id,
                    record.version,
                    record.display_filename,
                    record.extension,
                    record.content_hash,
                    record.size_bytes,
                    record.status.value,
                    record.chunk_count,
                    record.page_count,
                    record.created_at,
                    record.updated_at,
                    record.storage_name,
                    record.chunking_config,
                    record.embedding_identity,
                    json.dumps(record.user_metadata, sort_keys=True),
                    record.error,
                ),
            )

    def set_status(
        self,
        doc_id: str,
        status: DocumentStatus,
        *,
        error: Optional[str] = None,
        chunk_count: Optional[int] = None,
        embedding_identity: Optional[str] = None,
    ) -> None:
        with self._lock:
            fields = ["status = ?", "updated_at = ?", "error = ?"]
            params: List[object] = [status.value, utcnow_iso(), error]
            if chunk_count is not None:
                fields.append("chunk_count = ?")
                params.append(chunk_count)
            if embedding_identity is not None:
                fields.append("embedding_identity = ?")
                params.append(embedding_identity)
            params.append(doc_id)
            # Column names are fixed literals above; every value is a bound parameter.
            sql = f"UPDATE documents SET {', '.join(fields)} WHERE doc_id = ?"  # nosec B608
            self._conn.execute(sql, params)

    def get_document(self, doc_id: str) -> Optional[DocumentRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM documents WHERE doc_id = ?", (doc_id,)
            ).fetchone()
        return self._row_to_document(row) if row else None

    def find_by_hash(self, content_hash: str) -> List[DocumentRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM documents WHERE content_hash = ? ORDER BY created_at",
                (content_hash,),
            ).fetchall()
        return [self._row_to_document(r) for r in rows]

    def list_documents(
        self, statuses: Optional[Sequence[DocumentStatus]] = None
    ) -> List[DocumentRecord]:
        with self._lock:
            if statuses:
                placeholders = ",".join("?" for _ in statuses)
                # Placeholders only; status values are bound parameters.
                sql = f"SELECT * FROM documents WHERE status IN ({placeholders}) "  # nosec B608
                sql += "ORDER BY created_at, doc_id"
                rows = self._conn.execute(sql, [s.value for s in statuses]).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM documents ORDER BY created_at, doc_id"
                ).fetchall()
        return [self._row_to_document(r) for r in rows]

    def ready_doc_ids(self) -> List[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT doc_id FROM documents WHERE status = ? ORDER BY doc_id",
                (DocumentStatus.READY.value,),
            ).fetchall()
        return [r["doc_id"] for r in rows]

    def delete_document_rows(self, doc_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            self._conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM chunks")
            self._conn.execute("DELETE FROM documents")

    # -- chunks ------------------------------------------------------------
    @staticmethod
    def _row_to_chunk(row: sqlite3.Row) -> ChunkRecord:
        return ChunkRecord(
            chunk_id=row["chunk_id"],
            doc_id=row["doc_id"],
            version=int(row["version"]),
            ordinal=int(row["ordinal"]),
            text=row["text"],
            text_hash=row["text_hash"],
            location=SourceLocation(
                char_start=int(row["char_start"]),
                char_end=int(row["char_end"]),
                page=row["page"],
                page_end=row["page_end"],
                section=row["section"],
            ),
        )

    def replace_chunks(self, doc_id: str, version: int, chunks: Iterable[ChunkRecord]) -> int:
        """Store the chunk set for ``(doc_id, version)`` atomically."""
        rows: List[Tuple[object, ...]] = []
        for chunk in chunks:
            rows.append(
                (
                    chunk.chunk_id,
                    chunk.doc_id,
                    chunk.version,
                    chunk.ordinal,
                    chunk.text,
                    chunk.text_hash,
                    chunk.location.char_start,
                    chunk.location.char_end,
                    chunk.location.page,
                    chunk.location.page_end,
                    chunk.location.section,
                )
            )
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                self._conn.execute(
                    "DELETE FROM chunks WHERE doc_id = ? AND version = ?", (doc_id, version)
                )
                self._conn.executemany(
                    "INSERT INTO chunks (chunk_id, doc_id, version, ordinal, text, text_hash, "
                    "char_start, char_end, page, page_end, section) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    rows,
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return len(rows)

    def delete_chunks(self, doc_id: str, version: Optional[int] = None) -> int:
        with self._lock:
            if version is None:
                cur = self._conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            else:
                cur = self._conn.execute(
                    "DELETE FROM chunks WHERE doc_id = ? AND version = ?", (doc_id, version)
                )
            return cur.rowcount

    def get_chunks(
        self, doc_id: str, version: int, *, offset: int = 0, limit: Optional[int] = None
    ) -> List[ChunkRecord]:
        with self._lock:
            sql = (
                "SELECT * FROM chunks WHERE doc_id = ? AND version = ? "
                "ORDER BY ordinal LIMIT ? OFFSET ?"
            )
            rows = self._conn.execute(
                sql, (doc_id, version, -1 if limit is None else limit, offset)
            ).fetchall()
        return [self._row_to_chunk(r) for r in rows]

    def chunk_ids(self, doc_id: str, version: Optional[int] = None) -> List[str]:
        with self._lock:
            if version is None:
                rows = self._conn.execute(
                    "SELECT chunk_id FROM chunks WHERE doc_id = ? ORDER BY version, ordinal",
                    (doc_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT chunk_id FROM chunks WHERE doc_id = ? AND version = ? "
                    "ORDER BY ordinal",
                    (doc_id, version),
                ).fetchall()
        return [r["chunk_id"] for r in rows]

    def get_chunks_by_ids(self, chunk_ids: Sequence[str]) -> Dict[str, ChunkRecord]:
        if not chunk_ids:
            return {}
        out: Dict[str, ChunkRecord] = {}
        with self._lock:
            for i in range(0, len(chunk_ids), 500):
                batch = list(chunk_ids[i : i + 500])
                placeholders = ",".join("?" for _ in batch)
                sql = f"SELECT * FROM chunks WHERE chunk_id IN ({placeholders})"  # nosec B608
                rows = self._conn.execute(sql, batch).fetchall()  # placeholders only
                for row in rows:
                    out[row["chunk_id"]] = self._row_to_chunk(row)
        return out

    def iter_active_chunks(self) -> Iterator[ChunkRecord]:
        """Chunks of READY documents at their current version, in stable order."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT c.* FROM chunks c
                JOIN documents d ON d.doc_id = c.doc_id AND d.version = c.version
                WHERE d.status = ?
                ORDER BY d.created_at, c.doc_id, c.ordinal
                """,
                (DocumentStatus.READY.value,),
            ).fetchall()
        for row in rows:
            yield self._row_to_chunk(row)

    def active_chunk_count(self) -> int:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COUNT(*) AS n FROM chunks c
                JOIN documents d ON d.doc_id = c.doc_id AND d.version = c.version
                WHERE d.status = ?
                """,
                (DocumentStatus.READY.value,),
            ).fetchone()
        return int(row["n"])
