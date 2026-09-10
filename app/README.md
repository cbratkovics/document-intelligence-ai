# Experimental components

These modules predate the current `src/` pipeline. They are kept for
reference and are **not imported by the API** unless noted. They are excluded
from the lint and type gates and have no tests.

| Module | Status | Notes |
|---|---|---|
| `reranking/cross_encoder.py` | Optional, wired | Loaded lazily by `src/rag/reranker.py` when `RERANKER_MODE=cross_encoder`. Requires `requirements-ml.txt` and a model prepared with `scripts/setup/init_models.py --reranker`. Multi-class checkpoints use the second logit as relevance, which is only correct for binary relevance heads; the default MS MARCO MiniLM checkpoint has a single logit. |
| `cache/semantic_cache.py` | Disconnected | Redis-backed semantic cache using pickle serialization; not safe to enable against untrusted data without a versioned format. The active path uses the exact-match cache in `src/rag/cache.py`. |
| `chunking/strategies.py` | Disconnected | Alternative chunking strategies (sentence, sliding window, semantic). Requires `nltk`. The active chunker is `src/core/chunking.py`. |
| `embeddings/factory.py` | Disconnected | LangChain-based embedding factory. The active providers are in `src/core/embeddings.py`. |
| `retrieval/hybrid_search.py` | Disconnected | Standalone hybrid engine with weighted fusion; uses `1 - distance` regardless of the collection's distance metric. The active retriever is `src/rag/retriever.py`. |
| `tasks/` | Disconnected | Celery task definitions; no worker is part of the supported deployment. |
