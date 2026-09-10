"""Ingestion, replacement, deletion, restart, and failure-path tests."""

import asyncio

import pytest

from src.core.types import DocumentStatus, IngestionError, NotFoundError, RetrievalMode
from tests.conftest import (
    REFUND_TEXT,
    SHIPPING_TEXT,
    build_pdf,
    make_service,
    make_settings,
    make_stack,
)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_ingest_writes_each_store_exactly_once_and_is_idempotent(service):
    result = run(service.ingest("refund.md", REFUND_TEXT.encode(), {"team": "support"}))
    rec = result.record
    assert result.created and rec.status == DocumentStatus.READY and rec.chunk_count >= 2
    assert service.manifest.active_chunk_count() == rec.chunk_count
    assert service.lexical.size == rec.chunk_count
    assert service.vector_store.count() == rec.chunk_count
    assert service.storage.exists(rec.storage_name)
    assert rec.user_metadata == {"team": "support"}
    again = run(service.ingest("refund-copy.md", REFUND_TEXT.encode()))
    assert not again.created and again.duplicate_of == rec.doc_id
    assert service.vector_store.count() == rec.chunk_count  # nothing indexed twice
    assert service.manifest.corpus_generation() == 1


def test_reserved_and_invalid_metadata_rejected(service):
    for bad in ({"doc_id": "x"}, {"nested": {"a": 1}}, {"list": [1]}, {"long": "x" * 600}):
        with pytest.raises(IngestionError) as info:
            run(service.ingest("a.txt", b"some text", bad))
        assert info.value.code == "invalid_metadata"
    assert service.list_documents() == []


def test_empty_and_unsupported_inputs_do_not_become_documents(service):
    with pytest.raises(IngestionError):
        run(service.ingest("scan.pdf", build_pdf(["", ""])))
    with pytest.raises(IngestionError):
        run(service.ingest("blank.txt", b"   "))
    with pytest.raises(IngestionError):
        run(service.ingest("x.exe", b"MZ..."))
    assert service.list_documents() == []
    assert service.storage.root.exists() is False or not any(service.storage.root.iterdir())


class _FailingUpsertStore:
    """Wraps a real store but fails the first upsert (between chunk and vector writes)."""

    def __init__(self, inner, fail_times=1):
        self._inner = inner
        self._fail = fail_times

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def upsert(self, *args, **kwargs):
        if self._fail > 0:
            self._fail -= 1
            raise RuntimeError("simulated vector outage")
        return self._inner.upsert(*args, **kwargs)


def test_partial_indexing_failure_rolls_back_and_retry_succeeds(settings):
    service = make_service(settings)
    service.vector_store = _FailingUpsertStore(service.vector_store)
    with pytest.raises(IngestionError) as info:
        run(service.ingest("refund.md", REFUND_TEXT.encode()))
    assert info.value.code == "indexing_failed"
    docs = service.manifest.list_documents()
    assert len(docs) == 1 and docs[0].status == DocumentStatus.FAILED and docs[0].chunk_count == 0
    assert service.manifest.active_chunk_count() == 0 and service.lexical.size == 0
    assert service.vector_store.count() == 0
    assert not service.storage.exists(docs[0].storage_name)
    assert service.list_documents()[0].status == DocumentStatus.FAILED  # visible, honest
    retry = run(service.ingest("refund.md", REFUND_TEXT.encode()))
    assert (
        retry.created
        and retry.record.doc_id == docs[0].doc_id
        and retry.record.status == DocumentStatus.READY
    )
    assert service.vector_store.count() == retry.record.chunk_count == service.lexical.size
    assert len(service.manifest.chunk_ids(retry.record.doc_id)) == retry.record.chunk_count
    service.close()


def test_state_survives_restart(settings):
    service = make_service(settings)
    rec = run(service.ingest("refund.md", REFUND_TEXT.encode())).record
    service.close()
    reopened_service, retriever, _ = make_stack(settings)
    listed = reopened_service.list_documents()
    assert [d.doc_id for d in listed] == [rec.doc_id]
    assert reopened_service.lexical.size == rec.chunk_count
    assert reopened_service.vector_store.count() == rec.chunk_count
    result = run(retriever.retrieve("refund within 30 days", mode=RetrievalMode.LEXICAL))
    assert result.hits and result.hits[0].doc_id == rec.doc_id
    hybrid = run(retriever.retrieve("refund within 30 days", mode=RetrievalMode.HYBRID))
    assert hybrid.mode_effective == RetrievalMode.HYBRID and hybrid.hits
    reopened_service.close()


def test_embedding_identity_change_is_refused_not_silently_reused(settings, tmp_path):
    service = make_service(settings)
    run(service.ingest("refund.md", REFUND_TEXT.encode()))
    service.close()
    from src.core.types import IndexCompatibilityError

    other = make_settings(tmp_path, embedding_provider="local", allow_model_download=False)
    # ``local`` would try to load a model; use a fake identity via the store directly instead.
    from src.core.vector_store import VectorStore

    with pytest.raises(IndexCompatibilityError):
        VectorStore(embedding_identity="openai:text-embedding-3-small", persist_dir=other.index_dir)


def test_delete_removes_more_than_100_chunks_files_and_cache(tmp_path):
    settings = make_settings(tmp_path, chunk_size=60, chunk_overlap=0)
    service, retriever, generator = make_stack(settings)
    big = (
        "Northwind clause number {} states that refunds require a receipt. ".format(i)
        for i in range(160)
    )
    rec = run(service.ingest("big.txt", "".join(big).encode())).record
    assert rec.chunk_count > 100
    assert service.vector_store.count() == rec.chunk_count
    service.answer_cache.set("k", {"answer": "stale"})
    result = run(service.delete_document(rec.doc_id))
    assert (
        result.removed_chunks == rec.chunk_count == result.removed_vectors and result.file_removed
    )
    assert service.vector_store.count() == 0 and service.lexical.size == 0
    assert service.manifest.active_chunk_count() == 0 and len(service.answer_cache) == 0
    assert not (settings.uploads_dir).exists() or not any(settings.uploads_dir.iterdir())
    with pytest.raises(NotFoundError):
        run(service.delete_document(rec.doc_id))  # repeat delete is a 404, not a fake success
    assert run(retriever.retrieve("refunds receipt", mode=RetrievalMode.HYBRID)).hits == []
    service.close()


class _FailingDeleteStore:
    def __init__(self, inner):
        self._inner = inner
        self.fail = True

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def delete_document(self, doc_id, version=None):
        if self.fail:
            raise RuntimeError("simulated delete outage")
        return self._inner.delete_document(doc_id, version)


def test_failed_deletion_is_reported_and_document_stays_unsearchable(settings):
    service, retriever, _ = make_stack(settings)
    rec = run(service.ingest("refund.md", REFUND_TEXT.encode())).record
    store = _FailingDeleteStore(service.vector_store)
    service.vector_store = store
    with pytest.raises(IngestionError) as info:
        run(service.delete_document(rec.doc_id))
    assert info.value.code == "deletion_incomplete"
    assert service.manifest.get_document(rec.doc_id).status == DocumentStatus.DELETED
    assert service.vector_store.count() == rec.chunk_count  # vectors still there ...
    assert (
        run(retriever.retrieve("refund 30 days", mode=RetrievalMode.HYBRID)).hits == []
    )  # ... but never served
    assert rec.doc_id not in [d.doc_id for d in service.list_documents()]
    store.fail = False
    done = run(service.delete_document(rec.doc_id))
    assert done.removed_vectors == rec.chunk_count and service.vector_store.count() == 0
    service.close()


def test_replacement_keeps_old_version_until_commit_and_purges_after(settings):
    service, retriever, _ = make_stack(settings)
    v1 = run(
        service.ingest("policy.txt", b"The stipend is 250 dollars per year for accessories.")
    ).record
    failing = _FailingUpsertStore(service.vector_store)
    service.vector_store = failing
    with pytest.raises(IngestionError):
        run(
            service.ingest(
                "policy.txt", b"The stipend is 300 dollars per year now.", replace_doc_id=v1.doc_id
            )
        )
    current = service.get_document(v1.doc_id)
    assert current.version == 1 and current.status == DocumentStatus.READY  # old version intact
    assert (
        run(retriever.retrieve("stipend dollars", mode=RetrievalMode.LEXICAL))
        .hits[0]
        .text.startswith("The stipend is 250")
    )
    assert service.manifest.chunk_ids(v1.doc_id) == service.manifest.chunk_ids(v1.doc_id, 1)
    v2 = run(
        service.ingest(
            "policy.txt", b"The stipend is 300 dollars per year now.", replace_doc_id=v1.doc_id
        )
    ).record
    assert v2.doc_id == v1.doc_id and v2.version == 2
    assert service.manifest.chunk_ids(v1.doc_id) == service.manifest.chunk_ids(v1.doc_id, 2)
    assert service.vector_store.ids_for_document(v1.doc_id) == service.manifest.chunk_ids(
        v1.doc_id, 2
    )
    hits = run(
        service.lexical.search("stipend dollars", 10)
        and retriever.retrieve("stipend dollars", mode=RetrievalMode.HYBRID)
    ).hits
    assert all(h.version == 2 for h in hits) and "300" in hits[0].text
    assert not service.storage.exists(v1.storage_name) and service.storage.exists(v2.storage_name)
    same = run(
        service.ingest(
            "policy.txt", b"The stipend is 300 dollars per year now.", replace_doc_id=v1.doc_id
        )
    )
    assert not same.created and same.record.version == 2  # idempotent re-upload of the same bytes
    with pytest.raises(NotFoundError):
        run(service.ingest("policy.txt", b"x y z", replace_doc_id="missing"))
    service.close()


def test_lexical_only_mode_has_no_vector_store(tmp_path):
    settings = make_settings(tmp_path, embedding_provider="none")
    service, retriever, _ = make_stack(settings)
    rec = run(service.ingest("shipping.txt", SHIPPING_TEXT.encode())).record
    assert service.vector_store is None and rec.embedding_identity is None
    result = run(retriever.retrieve("expedited delivery", mode=RetrievalMode.HYBRID))
    assert (
        result.mode_effective == RetrievalMode.LEXICAL
        and result.mode_requested == RetrievalMode.HYBRID
    )
    assert any("dense retrieval unavailable" in n for n in result.notes)
    assert result.hits and result.hits[0].lexical_score and result.hits[0].vector_similarity is None
    from src.rag.retriever import RetrievalRequestError

    with pytest.raises(RetrievalRequestError) as info:
        run(retriever.retrieve("expedited delivery", mode=RetrievalMode.VECTOR))
    assert info.value.status == 409
    service.close()


def test_ephemeral_mode_is_explicit_and_resets(tmp_path):
    settings = make_settings(tmp_path, storage_mode="ephemeral")
    service = make_service(settings)
    run(service.ingest("shipping.txt", SHIPPING_TEXT.encode()))
    assert service.manifest.path is None and not settings.manifest_path.exists()
    service.close()
    assert make_service(settings).list_documents() == []
