"""Public-demo controls: health reporting, fusion ranks, seeding, eviction, rate limits."""

from __future__ import annotations

from tests.conftest import REFUND_TEXT, SHIPPING_TEXT, client_for, make_settings, upload

KEY = "rate-limit-test-key-0123456789"


def test_health_reports_effective_modes_and_document_count(tmp_path):
    with client_for(make_settings(tmp_path)) as client:  # hash embeddings
        health = client.get("/health").json()
        assert health["retrieval_mode"] == "hybrid" and health["embedding_provider"] == "hash"
        assert health["embedding_model"] == "bow:64" and health["embedding_semantic"] is False
        assert health["document_count"] == 0 and health["seeded_doc_ids"] == []
        upload(client, "s.txt", SHIPPING_TEXT)
        assert client.get("/health").json()["document_count"] == 1
    with client_for(make_settings(tmp_path / "lex", embedding_provider="none")) as client:
        health = client.get("/health").json()
        assert health["retrieval_mode"] == "lexical" and health["embedding_model"] is None
        assert health["reranker_mode"] == "none" and health["generation_provider"] == "none"
        assert health["capabilities"]["supported_extensions"] == [".md", ".pdf", ".rst", ".txt"]


def test_fusion_rank_and_candidate_pool_are_reported(tmp_path):
    with client_for(make_settings(tmp_path, reranker_mode="heuristic")) as client:
        upload(client, "refund.md", REFUND_TEXT)
        upload(client, "shipping.txt", SHIPPING_TEXT)
        hybrid = client.post(
            "/api/v1/search", json={"text": "refund delivery days", "mode": "hybrid", "top_k": 4}
        ).json()
        ranks = [(r["rank"], r["scores"]["fusion_rank"]) for r in hybrid["results"]]
        assert ranks and all(rank == fused for rank, fused in ranks)
        assert hybrid["candidate_k"] == 16  # top_k * candidate_multiplier
        # The corpus is smaller than the pool, so a missing branch rank means
        # "no match", and the counts say so: every chunk has a dense rank while
        # only chunks containing a query term have a lexical one.
        returned = hybrid["candidates_returned"]
        chunk_total = sum(d["chunk_count"] for d in client.get("/api/v1/documents").json())
        assert returned["vector"] == chunk_total < hybrid["candidate_k"]
        assert returned["lexical"] == sum(
            1 for r in hybrid["results"] if r["scores"]["lexical_rank"] is not None
        )
        assert returned["lexical"] <= returned["vector"]
        # A term that appears in one chunk: the lexical branch returns exactly
        # that chunk, every other hit has no lexical rank, and the counts make
        # the reason unambiguous (1 returned is fewer than the pool of 16).
        narrow = client.post(
            "/api/v1/search", json={"text": "expedited", "mode": "hybrid", "top_k": 4}
        ).json()
        assert narrow["candidates_returned"] == {"lexical": 1, "vector": chunk_total}
        assert [r["scores"]["lexical_rank"] for r in narrow["results"]].count(None) == len(
            narrow["results"]
        ) - 1
        lexical = client.post(
            "/api/v1/search", json={"text": "refund delivery days", "mode": "lexical"}
        ).json()
        assert all(r["scores"]["fusion_rank"] is None for r in lexical["results"])
        assert all(r["scores"]["fusion_score"] is None for r in lexical["results"])
        assert lexical["candidates_returned"]["vector"] is None  # branch did not run
        reranked = client.post(
            "/api/v1/search",
            json={"text": "refund delivery days", "mode": "hybrid", "use_reranker": True},
        ).json()
        assert reranked["rerank_status"] == "applied"
        # Fusion rank survives reranking so the two orderings can be compared.
        assert sorted(r["scores"]["fusion_rank"] for r in reranked["results"]) == list(
            range(1, len(reranked["results"]) + 1)
        )
        assert all(r["scores"]["rerank_score"] is not None for r in reranked["results"])


def test_seed_directory_ingests_supported_files_and_survives_restart(tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "b-shipping.txt").write_text(SHIPPING_TEXT)
    (seed / "a-refund.md").write_text(REFUND_TEXT)
    (seed / "ignored.exe").write_bytes(b"MZ")
    (seed / "empty.txt").write_text("   ")
    settings = make_settings(tmp_path, demo_seed_dir=str(seed))
    with client_for(settings) as client:
        health = client.get("/health").json()
        assert health["document_count"] == 2 and len(health["seeded_doc_ids"]) == 2
        assert len(health["seed_errors"]) == 1 and "empty.txt" in health["seed_errors"][0]
        names = [d["filename"] for d in client.get("/api/v1/documents").json()]
        assert names == ["a-refund.md", "b-shipping.txt"]
        first_ids = health["seeded_doc_ids"]
    with client_for(settings) as client:  # persistent storage: same ids, still protected
        health = client.get("/health").json()
        assert health["seeded_doc_ids"] == first_ids and health["document_count"] == 2


def test_max_documents_evicts_oldest_unprotected_document(tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "seeded.md").write_text(REFUND_TEXT)
    settings = make_settings(tmp_path, demo_seed_dir=str(seed), max_documents=3)
    with client_for(settings) as client:
        seeded_id = client.get("/health").json()["seeded_doc_ids"][0]
        first = upload(client, "first.txt", "Alpha parcel tracking number ALPHA-1.").json()
        assert first["evicted"] == []
        second = upload(client, "second.txt", "Bravo parcel tracking number BRAVO-2.").json()
        assert second["evicted"] == []  # exactly at the cap
        third = upload(client, "third.txt", "Charlie parcel tracking number CHARLIE-3.").json()
        assert third["evicted"] == [first["document"]["doc_id"]]
        remaining = {d["doc_id"] for d in client.get("/api/v1/documents").json()}
        assert remaining == {seeded_id, second["document"]["doc_id"], third["document"]["doc_id"]}
        hits = client.post("/api/v1/search", json={"text": "ALPHA-1", "mode": "lexical"}).json()
        assert hits["total"] == 0  # the evicted document is gone from every index
        # Re-uploading identical bytes is a duplicate, not a new document: nothing evicted.
        again = upload(client, "renamed.txt", "Bravo parcel tracking number BRAVO-2.").json()
        assert again["created"] is False and again["evicted"] == []
    # Seeded documents are never evicted; when only they remain, the cap is a hard error.
    settings = make_settings(tmp_path / "full", demo_seed_dir=str(seed), max_documents=1)
    with client_for(settings) as client:
        response = upload(client, "x.txt", SHIPPING_TEXT)
        assert response.status_code == 409 and response.json()["code"] == "corpus_full"
        assert len(client.get("/api/v1/documents").json()) == 1


def test_per_client_rate_limit_uses_forwarded_ip_only_with_a_valid_key(tmp_path):
    settings = make_settings(
        tmp_path, api_key=KEY, rate_limit_per_minute=2, rate_limit_global_per_minute=100
    )
    with client_for(settings) as client:
        trusted = {"X-API-Key": KEY, "X-Client-IP": "203.0.113.1"}
        assert client.get("/api/v1/documents", headers=trusted).status_code == 200
        assert client.get("/api/v1/documents", headers=trusted).status_code == 200
        blocked = client.get("/api/v1/documents", headers=trusted)
        assert blocked.status_code == 429 and blocked.json()["code"] == "rate_limited"
        assert int(blocked.headers["Retry-After"]) >= 1
        # A different visitor behind the same proxy has its own budget.
        other = {"X-API-Key": KEY, "X-Client-IP": "203.0.113.2"}
        assert client.get("/api/v1/documents", headers=other).status_code == 200
        # Health is never limited.
        for _ in range(5):
            assert client.get("/health").status_code == 200
    with client_for(settings) as client:
        # Without a valid key the header is ignored: every caller shares the socket bucket.
        spoof_a = {"X-Client-IP": "198.51.100.1"}
        spoof_b = {"X-Client-IP": "198.51.100.2"}
        assert client.get("/api/v1/documents", headers=spoof_a).status_code == 401
        assert client.get("/api/v1/documents", headers=spoof_b).status_code == 401
        assert client.get("/api/v1/documents", headers=spoof_b).status_code == 429
        wrong_key = {"X-API-Key": "wrong-key-wrong-key-1", "X-Client-IP": "198.51.100.3"}
        assert client.get("/api/v1/documents", headers=wrong_key).status_code == 429


def test_global_rate_limit_is_a_backstop_across_clients(tmp_path):
    settings = make_settings(
        tmp_path, api_key=KEY, rate_limit_per_minute=100, rate_limit_global_per_minute=3
    )
    with client_for(settings) as client:
        for n in range(3):
            headers = {"X-API-Key": KEY, "X-Client-IP": f"203.0.113.{n}"}
            assert client.get("/api/v1/documents", headers=headers).status_code == 200
        headers = {"X-API-Key": KEY, "X-Client-IP": "203.0.113.99"}
        assert client.get("/api/v1/documents", headers=headers).status_code == 429
        assert client.get("/health").status_code == 200
    with client_for(make_settings(tmp_path / "off")) as client:  # limits default to off
        assert not client.app.state.limiter.enabled
        for _ in range(10):
            assert client.get("/api/v1/documents").status_code == 200
