"""The public demo configuration can never reach a paid provider.

``deploy/space/demo.env`` is the configuration the Hugging Face Space runs
with. These tests load it the way the container does and prove that, even
with an OpenAI key present in the environment and every socket blocked, the
service starts, seeds the sample corpus, and answers hybrid queries.
"""

from __future__ import annotations

import socket
import sys
import types
from pathlib import Path

import pytest

from src.core.config import Settings
from src.core.embeddings import FastEmbedEmbeddings, HashEmbeddings, build_embedding_provider
from src.rag.generator import build_chat_client
from src.rag.reranker import HeuristicReranker, build_reranker
from tests.conftest import client_for

ROOT = Path(__file__).resolve().parents[1]
DEMO_ENV = ROOT / "deploy" / "space" / "demo.env"
SAMPLES = ROOT / "data" / "samples"
KEY = "demo-test-key-0123456789"


def demo_settings(tmp_path: Path, **overrides) -> Settings:
    base = dict(
        _env_file=str(DEMO_ENV),
        data_dir=str(tmp_path / "data"),
        fastembed_cache_dir=str(tmp_path / "models"),
        demo_seed_dir=str(SAMPLES),
        api_key=KEY,
    )
    base.update(overrides)
    return Settings(**base)


class FakeTextEmbedding:
    """Stands in for ``fastembed.TextEmbedding``: deterministic, offline."""

    calls: list = []

    def __init__(self, model_name: str, **kwargs):
        FakeTextEmbedding.calls.append((model_name, kwargs))
        self._inner = HashEmbeddings(384)

    def embed(self, texts, **kwargs):
        for text in texts:
            yield self._inner._vector(text)


@pytest.fixture
def fake_fastembed(monkeypatch):
    module = types.ModuleType("fastembed")
    module.TextEmbedding = FakeTextEmbedding  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fastembed", module)
    FakeTextEmbedding.calls.clear()
    return FakeTextEmbedding


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted in demo configuration")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


@pytest.fixture
def no_openai_import(monkeypatch):
    class Blocker:
        def find_spec(self, name, path=None, target=None):
            if name == "openai" or name.startswith("openai."):
                raise ImportError("openai must not be imported in the demo configuration")
            return None

    monkeypatch.setattr(sys, "meta_path", [Blocker()] + sys.meta_path)
    monkeypatch.delitem(sys.modules, "openai", raising=False)


def test_demo_env_resolves_no_paid_provider_even_with_a_key_present(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-not-a-real-key")
    settings = demo_settings(tmp_path)
    assert settings.openai_api_key == "sk-not-a-real-key"  # present, and still unused
    assert settings.resolved_embedding_provider == "fastembed"
    assert settings.resolved_generation_provider == "none"
    assert settings.reranker_mode == "heuristic"
    assert settings.allow_model_download is False
    assert settings.storage_mode == "ephemeral"
    assert settings.max_upload_size == 4 * 1024 * 1024
    assert settings.max_documents > 0
    assert settings.rate_limit_per_minute > 0 and settings.rate_limit_global_per_minute > 0
    assert settings.metrics_enabled is False
    assert build_chat_client(settings) is None
    assert isinstance(build_reranker(settings, None), HeuristicReranker)


def test_demo_stack_runs_with_sockets_blocked_and_openai_unimportable(
    tmp_path, monkeypatch, fake_fastembed, no_network, no_openai_import
):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-not-a-real-key")
    settings = demo_settings(tmp_path)
    with client_for(settings) as client:
        health = client.get("/health").json()
        assert health["status"] == "ok", health
        assert health["retrieval_mode"] == "hybrid"
        assert health["embedding_provider"] == "fastembed"
        assert health["embedding_model"] == "sentence-transformers/all-MiniLM-L6-v2"
        assert health["generation_provider"] == "none" and not health["generation_available"]
        assert health["reranker_mode"] == "heuristic"
        assert health["document_count"] == 4 and len(health["seeded_doc_ids"]) == 4
        assert health["seed_errors"] == []
        assert client.get("/metrics").status_code == 404

        headers = {"X-API-Key": KEY}
        assert client.get("/api/v1/documents").status_code == 401  # key enforced
        search = client.post(
            "/api/v1/search",
            json={"text": "What does error code DQ-E417 mean?", "mode": "hybrid", "top_k": 5},
            headers=headers,
        ).json()
        assert search["mode_effective"] == "hybrid" and search["results"]
        assert search["results"][0]["scores"]["fusion_rank"] == 1
        query = client.post(
            "/api/v1/query", json={"text": "What counts as a repeat buyer?"}, headers=headers
        ).json()
        assert query["status"] == "excerpts_only" and query["generation"]["model"] is None
    # The provider was constructed offline against the configured cache.
    (model_name, kwargs), *_ = fake_fastembed.calls
    assert model_name == settings.fastembed_model
    assert kwargs == {"local_files_only": True, "cache_dir": str(tmp_path / "models")}
    assert "openai" not in sys.modules


def test_fastembed_provider_plumbing_with_a_double(tmp_path, fake_fastembed):
    settings = Settings(
        embedding_provider="fastembed",
        fastembed_cache_dir=str(tmp_path),
        allow_model_download=False,
        data_dir=str(tmp_path / "data"),
    )
    provider = build_embedding_provider(settings)
    assert isinstance(provider, FastEmbedEmbeddings)
    assert provider.identity == "fastembed:sentence-transformers/all-MiniLM-L6-v2"
    assert provider.semantic is True and provider.dimension == 384
    vectors = provider.embed_documents(["refund window", "   "])
    assert len(vectors) == 2 and len(vectors[0]) == 384
    assert provider.embed_query("refund window") == vectors[0]
    assert fake_fastembed.calls[0][1]["local_files_only"] is True

    FastEmbedEmbeddings("m", cache_dir=None, allow_download=True, model_factory=fake_fastembed)
    assert fake_fastembed.calls[-1] == ("m", {"local_files_only": False})


def test_fastembed_missing_model_is_a_clear_error(tmp_path):
    def broken(*args, **kwargs):
        raise FileNotFoundError("no model in cache")

    with pytest.raises(RuntimeError, match="init_models.py --fastembed"):
        FastEmbedEmbeddings(
            "m", cache_dir=str(tmp_path), allow_download=False, model_factory=broken
        )
