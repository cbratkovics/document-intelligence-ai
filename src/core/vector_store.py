"""Chroma-backed dense index.

The collection is created with cosine space explicitly, so the ``distance``
Chroma returns is ``1 - cosine_similarity`` and ``vector_similarity`` is a
faithful conversion. Embeddings are always supplied by the application: the
collection has no embedding function, so Chroma never downloads a model.

The embedding identity is stored in collection metadata; opening an index that
was built with a different identity raises ``IndexCompatibilityError`` unless
the index is empty, in which case it is rebuilt.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from .types import IndexCompatibilityError, QueryScope

logger = logging.getLogger(__name__)

_META_IDENTITY = "embedding_identity"


@dataclass(frozen=True)
class VectorHit:
    chunk_id: str
    distance: float
    metadata: Dict[str, Any]


class VectorStore:
    def __init__(
        self,
        *,
        embedding_identity: str,
        collection_name: str = "documents",
        persist_dir: Optional[Path] = None,
        client=None,
    ):
        self.embedding_identity = embedding_identity
        self.collection_name = collection_name
        self.persist_dir = persist_dir
        self._client = client or self._make_client(persist_dir)
        self._collection = self._open_collection()

    @staticmethod
    def _make_client(persist_dir: Optional[Path]):
        os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        chroma_settings = ChromaSettings(anonymized_telemetry=False, allow_reset=True)
        if persist_dir is None:
            return chromadb.EphemeralClient(settings=chroma_settings)
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        return chromadb.PersistentClient(path=str(persist_dir), settings=chroma_settings)

    def _open_collection(self):
        metadata = {"hnsw:space": "cosine", _META_IDENTITY: self.embedding_identity}
        try:
            collection = self._client.get_collection(self.collection_name)
        except Exception:
            return self._client.create_collection(self.collection_name, metadata=metadata)

        existing = (collection.metadata or {}).get(_META_IDENTITY)
        space = (collection.metadata or {}).get("hnsw:space")
        if existing != self.embedding_identity or space != "cosine":
            if collection.count() == 0:
                logger.warning(
                    "Rebuilding empty vector collection (identity %r -> %r)",
                    existing,
                    self.embedding_identity,
                )
                self._client.delete_collection(self.collection_name)
                return self._client.create_collection(self.collection_name, metadata=metadata)
            raise IndexCompatibilityError(
                f"Vector index was built with embedding identity {existing!r} "
                f"(space={space!r}) but the configured identity is "
                f"{self.embedding_identity!r}. Delete {self.persist_dir} to rebuild."
            )
        return collection

    # -- writes ------------------------------------------------------------
    def upsert(
        self,
        chunk_ids: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        metadatas: Sequence[Dict[str, Any]],
        documents: Optional[Sequence[str]] = None,
    ) -> None:
        if not chunk_ids:
            return
        if not (len(chunk_ids) == len(embeddings) == len(metadatas)):
            raise ValueError("chunk_ids, embeddings and metadatas must align")
        kwargs: Dict[str, Any] = {
            "ids": list(chunk_ids),
            "embeddings": [list(map(float, e)) for e in embeddings],
            "metadatas": [dict(m) for m in metadatas],
        }
        if documents is not None:
            kwargs["documents"] = list(documents)
        self._collection.upsert(**kwargs)

    def delete_ids(self, chunk_ids: Sequence[str]) -> None:
        ids = list(chunk_ids)
        for i in range(0, len(ids), 500):
            self._collection.delete(ids=ids[i : i + 500])

    def delete_document(self, doc_id: str, version: Optional[int] = None) -> int:
        """Delete every vector for ``doc_id`` (optionally one version)."""
        ids = self.ids_for_document(doc_id, version)
        if ids:
            self.delete_ids(ids)
        return len(ids)

    def reset(self) -> None:
        self._client.delete_collection(self.collection_name)
        self._collection = self._open_collection()

    def drop(self) -> None:
        """Delete the collection without recreating it (ephemeral shutdown)."""
        try:
            self._client.delete_collection(self.collection_name)
        except Exception as exc:  # pragma: no cover - best effort at shutdown
            logger.warning("Could not drop vector collection: %s", exc)

    # -- reads -------------------------------------------------------------
    def count(self) -> int:
        return int(self._collection.count())

    def ids_for_document(self, doc_id: str, version: Optional[int] = None) -> List[str]:
        where: Dict[str, Any] = {"doc_id": doc_id}
        if version is not None:
            where = {"$and": [{"doc_id": doc_id}, {"version": int(version)}]}
        ids: List[str] = []
        offset = 0
        page = 500
        while True:
            result = self._collection.get(where=where, limit=page, offset=offset, include=[])
            batch = result.get("ids") or []
            ids.extend(batch)
            if len(batch) < page:
                break
            offset += page
        return ids

    def query(
        self,
        embedding: Sequence[float],
        n_results: int,
        scope: QueryScope = QueryScope.whole_corpus(),
    ) -> List[VectorHit]:
        if n_results <= 0 or scope.is_empty:
            return []
        total = self.count()
        if total == 0:
            return []
        where: Optional[Dict[str, Any]] = None
        if scope.doc_ids is not None:
            ids = sorted(scope.doc_ids)
            where = {"doc_id": ids[0]} if len(ids) == 1 else {"doc_id": {"$in": ids}}
        result = self._collection.query(
            query_embeddings=[list(map(float, embedding))],
            n_results=min(n_results, total),
            where=where,
            include=["metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        hits = [
            VectorHit(chunk_id=cid, distance=float(dist), metadata=dict(meta or {}))
            for cid, dist, meta in zip(ids, distances, metadatas)
        ]
        hits.sort(key=lambda h: (h.distance, h.chunk_id))
        return hits

    def has_ids(self, chunk_ids: Iterable[str]) -> Dict[str, bool]:
        wanted = list(chunk_ids)
        present: Set[str] = set()
        for i in range(0, len(wanted), 500):
            got = self._collection.get(ids=wanted[i : i + 500], include=[])
            present.update(got.get("ids") or [])
        return {cid: cid in present for cid in wanted}
