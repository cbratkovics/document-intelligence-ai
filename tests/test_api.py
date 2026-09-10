"""HTTP contract tests: startup without keys, auth, limits, statuses, streaming."""

import json

import pytest

from tests.conftest import REFUND_TEXT, SHIPPING_TEXT, client_for, make_settings, upload


def test_import_and_startup_without_keys_redis_or_models(client):
    health = client.get("/health").json()
    assert health["status"] == "ok" and health["auth"] == "local_mode_no_auth"
    caps = health["capabilities"]
    assert caps["lexical_retrieval"] is True and caps["generation_provider"] == "none"
    assert caps["embedding_provider"] == "hash" and caps["embedding_semantic"] is False
    assert client.get("/ready").status_code == 200
    schema = client.get("/openapi.json").json()
    assert schema["servers"] == [{"url": "/", "description": "This server"}]
    assert client.get("/").json()["ui"] == "/ui"


def test_upload_search_query_chunks_delete_flow(client):
    up = upload(client, "refund.md", REFUND_TEXT, {"team": "support"})
    assert up.status_code == 200, up.text
    body = up.json()
    doc = body["document"]
    assert body["created"] and doc["status"] == "ready" and doc["metadata"] == {"team": "support"}
    assert doc["filename"] == "refund.md" and "storage" not in json.dumps(doc)
    dup = upload(client, "other-name.md", REFUND_TEXT)
    assert (
        dup.status_code == 200
        and dup.json()["created"] is False
        and dup.json()["duplicate_of"] == doc["doc_id"]
    )

    listed = client.get("/api/v1/documents").json()
    assert [d["doc_id"] for d in listed] == [doc["doc_id"]]
    chunks = client.get(f"/api/v1/documents/{doc['doc_id']}/chunks?limit=1").json()
    assert chunks["chunk_count"] == doc["chunk_count"] and len(chunks["chunks"]) == 1
    assert chunks["chunks"][0]["location"]["section"] == "Refund policy"

    search = client.post(
        "/api/v1/search", json={"text": "refund 30 days", "mode": "hybrid", "top_k": 3}
    ).json()
    assert search["mode_effective"] == "hybrid" and search["results"][0]["doc_id"] == doc["doc_id"]
    assert (
        search["results"][0]["scores"]["fusion_score"] is not None
        and search["rerank_status"] == "disabled"
    )

    answer = client.post(
        "/api/v1/query", json={"text": "How long do refunds take?", "doc_ids": [doc["doc_id"]]}
    ).json()
    assert answer["status"] == "excerpts_only" and answer["answer"] is None and answer["excerpts"]
    assert "confidence" not in answer and answer["generation"]["model"] is None

    summary = client.post(f"/api/v1/documents/{doc['doc_id']}/summary?max_chars=100").json()
    assert (
        summary["status"] == "excerpts_only"
        and summary["coverage"]["chunks_total"] == doc["chunk_count"]
    )

    deleted = client.delete(f"/api/v1/documents/{doc['doc_id']}")
    assert deleted.status_code == 200 and deleted.json()["status"] == "deleted"
    assert client.delete(f"/api/v1/documents/{doc['doc_id']}").status_code == 404
    assert client.get(f"/api/v1/documents/{doc['doc_id']}").status_code == 404
    assert client.post("/api/v1/search", json={"text": "refund 30 days"}).json()["total"] == 0


def test_unknown_request_fields_are_rejected(client):
    for payload in (
        {"text": "q", "filters": {"a": 1}},
        {"text": "q", "stream": True},
        {"text": "q", "mode": "magic"},
    ):
        assert client.post("/api/v1/query", json=payload).status_code == 422, payload
    assert client.post("/api/v1/query", json={"text": ""}).status_code == 422
    assert client.post("/api/v1/search", json={"text": "q", "top_k": 0}).status_code == 422
    assert client.post("/api/v1/search", json={"text": "q", "top_k": 999}).status_code == 400
    assert client.post("/api/v1/search", json={"text": "q", "doc_ids": ["nope"]}).status_code == 404


def test_upload_validation_status_codes(tmp_path):
    settings = make_settings(tmp_path, max_upload_size=2000)
    with client_for(settings) as client:
        assert upload(client, "big.txt", "x" * 2001).status_code == 413
        assert upload(client, "run.exe", "MZ").status_code == 400
        assert upload(client, "blank.txt", "   ").status_code == 400
        assert upload(client, "a.txt", "hello world", {"doc_id": "x"}).status_code == 400
        bad_json = client.post(
            "/api/v1/documents/upload",
            files={"file": ("a.txt", b"hello")},
            data={"metadata": "{not json"},
        )
        assert bad_json.status_code == 400
        assert client.get("/api/v1/documents").json() == []


def test_api_key_enforced_when_configured(tmp_path):
    key = "local-test-key-0123456789"
    settings = make_settings(tmp_path, api_key=key)
    with client_for(settings) as client:
        assert client.get("/health").status_code == 200  # liveness stays open
        assert client.get("/api/v1/documents").status_code == 401
        assert (
            client.get(
                "/api/v1/documents", headers={"X-API-Key": "wrong-key-wrong-key-1"}
            ).status_code
            == 401
        )
        assert client.get("/api/v1/documents", headers={"X-API-Key": key}).status_code == 200
        assert upload(client, "s.txt", SHIPPING_TEXT).status_code == 401
        assert upload(client, "s.txt", SHIPPING_TEXT, api_key=key).status_code == 200
        assert client.delete("/api/v1/documents").status_code == 401
        cleared = client.delete("/api/v1/documents", headers={"X-API-Key": key})
        assert cleared.status_code == 200 and cleared.json()["documents_removed"] == 1


def test_clear_all_unavailable_without_configured_key(client):
    upload(client, "s.txt", SHIPPING_TEXT)
    assert client.delete("/api/v1/documents").status_code == 403
    assert len(client.get("/api/v1/documents").json()) == 1


def test_short_api_key_rejected_at_configuration(tmp_path):
    with pytest.raises(ValueError):
        make_settings(tmp_path, api_key="short")


def test_stream_endpoint_returns_ndjson_with_single_terminal_event(client):
    doc = upload(client, "s.txt", SHIPPING_TEXT).json()["document"]["doc_id"]
    response = client.post(
        "/api/v1/query/stream", json={"text": "expedited delivery", "doc_ids": [doc]}
    )
    assert response.status_code == 200 and response.headers["content-type"].startswith(
        "application/x-ndjson"
    )
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [e["event"] for e in events] == ["meta", "sources", "done"]
    assert events[0]["v"] == 1 and events[-1]["status"] == "excerpts_only"
    assert (
        client.post("/api/v1/query/stream", json={"text": "x", "doc_ids": ["missing"]}).status_code
        == 404
    )


def test_errors_keep_status_codes_and_hide_internals(tmp_path):
    settings = make_settings(tmp_path, app_env="production")
    with client_for(settings) as client:
        response = client.get("/api/v1/documents/missing")
        assert response.status_code == 404 and response.json()["code"] == "not_found"
        assert "X-Request-ID" in response.headers
        assert (
            client.post(
                "/api/v1/evaluate/judge", json={"question": "q", "answer": "a", "context": "c"}
            ).json()["status"]
            == "unavailable"
        )


def test_startup_index_mismatch_is_reported_not_hidden(tmp_path):
    settings = make_settings(tmp_path)
    with client_for(settings) as client:
        upload(client, "s.txt", SHIPPING_TEXT)
    from src.core.vector_store import VectorStore

    # Simulate an index built by another embedding configuration.
    store = VectorStore(embedding_identity="hash:bow:64", persist_dir=settings.index_dir)
    store._client.get_collection(settings.chroma_collection_name).modify(
        metadata={"embedding_identity": "openai:other"}
    )
    with client_for(settings) as client:
        health = client.get("/health").json()
        assert health["status"] == "degraded" and "embedding identity" in health["startup_error"]
        assert client.get("/ready").status_code == 503
        assert client.get("/api/v1/documents").status_code == 503


def test_metrics_endpoint_uses_route_templates(client):
    doc = upload(client, "s.txt", SHIPPING_TEXT).json()["document"]["doc_id"]
    client.get(f"/api/v1/documents/{doc}")
    response = client.get("/metrics", follow_redirects=False)
    assert response.status_code == 200  # no trailing-slash redirect
    text = response.text
    assert 'route="/api/v1/documents/{doc_id}"' in text
    assert doc not in text
