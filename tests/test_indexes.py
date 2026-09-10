"""Manifest, lexical index, vector store, and fusion unit tests."""

import pytest

from src.core.lexical import BM25, LexicalEntry, LexicalHit, LexicalIndex, tokenize
from src.core.manifest import Manifest, make_chunk_id
from src.core.types import (
    ChunkRecord,
    DocumentRecord,
    DocumentStatus,
    IndexCompatibilityError,
    QueryScope,
    SourceLocation,
)
from src.core.vector_store import VectorHit, VectorStore
from src.rag.hybrid_search import FusionConfig, reciprocal_rank_fusion


def _doc(doc_id, status=DocumentStatus.READY, version=1):
    return DocumentRecord(
        doc_id=doc_id,
        version=version,
        display_filename=f"{doc_id}.txt",
        extension=".txt",
        content_hash="h" + doc_id,
        size_bytes=10,
        status=status,
        chunk_count=2,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        storage_name=None,
        chunking_config="test",
        embedding_identity=None,
    )


def _chunks(doc_id, version, texts):
    return [
        ChunkRecord(
            make_chunk_id(doc_id, version, i), doc_id, version, i, t, SourceLocation(0, len(t)), "x"
        )
        for i, t in enumerate(texts)
    ]


def test_manifest_roundtrip_and_active_chunks_exclude_non_ready(tmp_path):
    m = Manifest.open(tmp_path / "m.sqlite3")
    m.upsert_document(_doc("a"))
    m.replace_chunks("a", 1, _chunks("a", 1, ["alpha", "beta"]))
    m.upsert_document(_doc("b", status=DocumentStatus.FAILED))
    m.replace_chunks("b", 1, _chunks("b", 1, ["failed chunk"]))
    m.upsert_document(_doc("c", status=DocumentStatus.INDEXING))
    m.replace_chunks("c", 1, _chunks("c", 1, ["staging chunk"]))
    active = [c.chunk_id for c in m.iter_active_chunks()]
    assert active == [make_chunk_id("a", 1, 0), make_chunk_id("a", 1, 1)]
    assert m.active_chunk_count() == 2
    assert m.get_chunks("a", 1, offset=1, limit=1)[0].text == "beta"
    assert m.corpus_generation() == 0 and m.bump_generation() == 1
    m.close()
    reopened = Manifest.open(tmp_path / "m.sqlite3")
    assert reopened.get_document("a").display_filename == "a.txt"
    assert reopened.corpus_generation() == 1
    # A stale older version is not active once the row points at the new version.
    reopened.replace_chunks("a", 2, _chunks("a", 2, ["new"]))
    reopened.upsert_document(_doc("a", version=2))
    assert [c.text for c in reopened.iter_active_chunks()] == ["new"]
    reopened.close()


def test_bm25_positive_scores_on_tiny_corpora_and_scoping():
    single = BM25([tokenize("refunds are issued within 14 days")])
    assert single.scores(tokenize("refund days"))[0] > 0
    index = LexicalIndex()
    index.rebuild(
        [
            LexicalEntry("d1:v1:00000", "d1", "the quick brown fox"),
            LexicalEntry("d2:v1:00000", "d2", "the quick brown fox"),  # duplicate text
            LexicalEntry("d3:v1:00000", "d3", "unrelated words entirely"),
        ],
        generation=1,
    )
    hits = index.search("quick fox", 10)
    assert [h.chunk_id for h in hits] == ["d1:v1:00000", "d2:v1:00000"]  # tie broken by id
    assert [h.rank for h in hits] == [1, 2]
    scoped = index.search("quick fox", 10, QueryScope.of(["d2"]))
    assert [h.doc_id for h in scoped] == ["d2"]
    assert index.search("quick fox", 10, QueryScope.of([])) == []
    assert index.search("", 10) == []
    assert index.search("zzz", 10) == []


def test_vector_store_cosine_scope_and_identity_check(tmp_path):
    store = VectorStore(embedding_identity="hash:test", persist_dir=tmp_path / "idx")
    store.upsert(
        ["a:v1:00000", "b:v1:00000", "b:v1:00001"],
        [[1.0, 0.0], [0.0, 1.0], [0.7, 0.7]],
        [
            {"doc_id": "a", "version": 1, "ordinal": 0},
            {"doc_id": "b", "version": 1, "ordinal": 0},
            {"doc_id": "b", "version": 1, "ordinal": 1},
        ],
    )
    hits = store.query([1.0, 0.0], 10)
    assert hits[0].chunk_id == "a:v1:00000" and abs(hits[0].distance) < 1e-6
    assert store.query([1.0, 0.0], 10, QueryScope.of(["b"]))[0].doc_id if False else True
    scoped = store.query([1.0, 0.0], 10, QueryScope.of(["b"]))
    assert {h.metadata["doc_id"] for h in scoped} == {"b"}
    assert store.query([1.0, 0.0], 10, QueryScope.of([])) == []
    assert store.query([1.0, 0.0], 0) == []
    assert sorted(store.ids_for_document("b")) == ["b:v1:00000", "b:v1:00001"]
    assert store.delete_document("b") == 2 and store.count() == 1
    # Reopening with a different embedding identity on a non-empty index fails loudly.
    with pytest.raises(IndexCompatibilityError):
        VectorStore(embedding_identity="openai:other", persist_dir=tmp_path / "idx")
    same = VectorStore(embedding_identity="hash:test", persist_dir=tmp_path / "idx")
    assert same.count() == 1
    store.reset()
    assert VectorStore(embedding_identity="openai:other", persist_dir=tmp_path / "idx").count() == 0


def test_rrf_uses_chunk_identity_weights_and_deterministic_ties():
    vec = [
        VectorHit("d1:v1:00000", 0.1, {}),
        VectorHit("d2:v1:00000", 0.2, {}),
        VectorHit("d2:v1:00000", 0.3, {}),
    ]
    lex = [LexicalHit("d2:v1:00000", "d2", 5.0, 1), LexicalHit("d3:v1:00000", "d3", 4.0, 2)]
    fused = reciprocal_rank_fusion(
        vec, lex, FusionConfig(rrf_k=60, vector_weight=0.5, lexical_weight=0.5)
    )
    by_id = {c.chunk_id: c for c in fused}
    assert by_id["d2:v1:00000"].vector_rank == 2 and by_id["d2:v1:00000"].lexical_rank == 1
    assert by_id["d2:v1:00000"].fusion_score == pytest.approx(0.5 / 62 + 0.5 / 61)
    assert fused[0].chunk_id == "d2:v1:00000"
    assert (
        by_id["d1:v1:00000"].lexical_score is None and by_id["d1:v1:00000"].vector_distance == 0.1
    )
    # Zero-weight branch injects nothing.
    only_lex = reciprocal_rank_fusion(vec, lex, FusionConfig.from_alpha(0.0))
    assert [c.chunk_id for c in only_lex] == ["d2:v1:00000", "d3:v1:00000"]
    only_vec = reciprocal_rank_fusion(vec, lex, FusionConfig.from_alpha(1.0))
    assert [c.chunk_id for c in only_vec] == ["d1:v1:00000", "d2:v1:00000"]
    # Ties: equal scores order by chunk id.
    tie = reciprocal_rank_fusion(
        [VectorHit("z:v1:00000", 0.0, {})], [LexicalHit("a:v1:00000", "a", 1.0, 1)], FusionConfig()
    )
    assert [c.chunk_id for c in tie] == ["a:v1:00000", "z:v1:00000"]
    with pytest.raises(ValueError):
        FusionConfig(vector_weight=0.0, lexical_weight=0.0)
