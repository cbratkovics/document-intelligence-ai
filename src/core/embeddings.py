"""Embedding providers.

Providers are constructed lazily from settings. Importing this module never
imports a provider SDK, opens a connection, or loads a model.

- ``openai``: OpenAI embeddings API (paid; requires ``OPENAI_API_KEY``).
- ``local``: sentence-transformers model loaded from the local cache. Downloads
  are refused unless ``ALLOW_MODEL_DOWNLOAD=true``.
- ``fastembed``: the same MiniLM family through ONNX Runtime (no torch). Model
  files come from the fastembed cache; downloads are refused unless
  ``ALLOW_MODEL_DOWNLOAD=true``.
- ``hash``: deterministic hashed bag-of-words vectors. Test-only: proves the
  vector plumbing but carries no semantic signal.
- ``none``: dense retrieval disabled; the system runs lexical-only.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
import re
from typing import List, Optional, Protocol, Sequence

from .config import Settings

logger = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    identity: str
    dimension: int
    semantic: bool

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        ...

    def embed_query(self, text: str) -> List[float]:
        ...


class HashEmbeddings:
    """Deterministic, dependency-free embeddings for plumbing tests."""

    semantic = False
    _token_re = re.compile(r"\w+")

    def __init__(self, dimension: int = 64):
        self.dimension = dimension
        self.identity = f"hash:bow:{dimension}"

    def _vector(self, text: str) -> List[float]:
        vec = [0.0] * self.dimension
        for token in self._token_re.findall(text.lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[index] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            vec[0] = 1.0
            return vec
        return [v / norm for v in vec]

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._vector(text)


class OpenAIEmbeddings:
    """OpenAI embeddings via the official SDK (imported lazily)."""

    semantic = True
    _KNOWN_DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
        batch_size: int = 100,
        client=None,
    ):
        self.model = model
        self.identity = f"openai:{model}"
        self.batch_size = batch_size
        self.dimension = self._KNOWN_DIMENSIONS.get(model, 0)
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError(
                    "The 'openai' package is required for embedding_provider=openai "
                    "(pip install -r requirements-ml.txt)"
                ) from exc
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        self._client = client

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        out: List[List[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = [t if t.strip() else " " for t in texts[i : i + self.batch_size]]
            response = self._client.embeddings.create(model=self.model, input=batch)
            vectors = [item.embedding for item in sorted(response.data, key=lambda d: d.index)]
            if len(vectors) != len(batch):
                raise RuntimeError("Embedding provider returned an unexpected count")
            out.extend(vectors)
        if out and not self.dimension:
            self.dimension = len(out[0])
        return out

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]


class LocalEmbeddings:
    """sentence-transformers embeddings loaded from the local HF cache."""

    semantic = True

    def __init__(self, model_name: str, allow_download: bool, device: str = "cpu"):
        self.identity = f"local:{model_name}"
        if not allow_download:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is required for embedding_provider=local "
                "(pip install -r requirements-ml.txt)"
            ) from exc
        try:
            self._model = SentenceTransformer(model_name, device=device)
        except Exception as exc:
            raise RuntimeError(
                f"Could not load local embedding model '{model_name}'. Prepare it "
                "with `python scripts/setup/init_models.py --embedding` or set "
                "ALLOW_MODEL_DOWNLOAD=true."
            ) from exc
        self.dimension = int(self._model.get_sentence_embedding_dimension() or 0)

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        vectors = self._model.encode(list(texts), normalize_embeddings=True)
        return [list(map(float, v)) for v in vectors]

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]


class FastEmbedEmbeddings:
    """ONNX Runtime embeddings via ``fastembed`` (imported lazily).

    The model must already be present in ``cache_dir`` (prepare it with
    ``scripts/setup/init_models.py --fastembed``) unless downloads are allowed.
    """

    semantic = True

    def __init__(
        self,
        model_name: str,
        cache_dir: Optional[str],
        allow_download: bool,
        model_factory=None,
    ):
        self.identity = f"fastembed:{model_name}"
        self.model_name = model_name
        if not allow_download:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
        if model_factory is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:
                raise RuntimeError(
                    "fastembed is required for embedding_provider=fastembed "
                    "(pip install -r requirements-demo.txt)"
                ) from exc
            model_factory = TextEmbedding
        kwargs: dict = {"local_files_only": not allow_download}
        if cache_dir:
            kwargs["cache_dir"] = cache_dir
        try:
            self._model = model_factory(model_name, **kwargs)
        except Exception as exc:
            raise RuntimeError(
                f"Could not load fastembed model '{model_name}'. Prepare it with "
                "`python scripts/setup/init_models.py --fastembed` or set "
                "ALLOW_MODEL_DOWNLOAD=true."
            ) from exc
        self.dimension = len(self.embed_query("dimension probe"))

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        batch = [t if t.strip() else " " for t in texts]
        if not batch:
            return []
        vectors = [list(map(float, v)) for v in self._model.embed(batch)]
        if len(vectors) != len(batch):
            raise RuntimeError("fastembed returned an unexpected number of vectors")
        return vectors

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]


def build_embedding_provider(settings: Settings) -> Optional[EmbeddingProvider]:
    """Instantiate the configured provider, or ``None`` for lexical-only mode."""
    name = settings.resolved_embedding_provider
    if name == "none":
        return None
    if name == "hash":
        return HashEmbeddings()
    if name == "openai":
        return OpenAIEmbeddings(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key or "",
            base_url=settings.openai_base_url,
            timeout=settings.openai_timeout_seconds,
        )
    if name == "local":
        return LocalEmbeddings(
            settings.local_embedding_model, allow_download=settings.allow_model_download
        )
    if name == "fastembed":
        return FastEmbedEmbeddings(
            settings.fastembed_model,
            cache_dir=settings.fastembed_cache_dir,
            allow_download=settings.allow_model_download,
        )
    raise ValueError(f"Unknown embedding provider: {name}")


async def embed_documents_async(
    provider: EmbeddingProvider, texts: Sequence[str]
) -> List[List[float]]:
    return await asyncio.to_thread(provider.embed_documents, texts)


async def embed_query_async(provider: EmbeddingProvider, text: str) -> List[float]:
    return await asyncio.to_thread(provider.embed_query, text)
