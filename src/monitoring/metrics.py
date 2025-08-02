from prometheus_client import Counter, Histogram, Gauge, Info
import time
from functools import wraps
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)

# Define metrics
request_count = Counter(
    "document_intelligence_requests_total",
    "Total requests",
    ["method", "endpoint", "status"],
)

request_latency = Histogram(
    "document_intelligence_request_duration_seconds",
    "Request latency",
    ["method", "endpoint"],
)

active_requests = Gauge("document_intelligence_active_requests", "Active requests")

documents_processed = Counter(
    "documents_processed_total", "Total documents processed", ["document_type"]
)

embedding_generation_time = Histogram(
    "embedding_generation_seconds",
    "Time to generate embeddings",
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

vector_search_latency = Histogram(
    "vector_search_duration_seconds",
    "Vector search latency",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

rag_generation_time = Histogram(
    "rag_generation_seconds",
    "Time to generate RAG answers",
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

hybrid_search_performance = Histogram(
    "hybrid_search_duration_seconds",
    "Hybrid search latency",
    ["search_type"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0),
)

reranking_latency = Histogram(
    "reranking_duration_seconds", "Reranking latency", buckets=(0.1, 0.5, 1.0, 2.5, 5.0)
)

documents_in_index = Gauge("documents_in_index_total", "Total documents in the index")

chunks_in_index = Gauge("chunks_in_index_total", "Total chunks in the index")

search_results_returned = Histogram(
    "search_results_returned",
    "Number of search results returned",
    ["search_type"],
    buckets=(0, 1, 5, 10, 20, 50, 100),
)

# System info
system_info = Info("document_intelligence_info", "System information")


def track_request_metrics(method: str, endpoint: str):
    """Decorator to track request metrics"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            active_requests.inc()
            status = "success"

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                logger.error(f"Request failed: {method} {endpoint} - {str(e)}")
                raise
            finally:
                duration = time.time() - start_time
                request_count.labels(
                    method=method, endpoint=endpoint, status=status
                ).inc()
                request_latency.labels(method=method, endpoint=endpoint).observe(
                    duration
                )
                active_requests.dec()

                logger.info(f"{method} {endpoint} - {status} - {duration:.3f}s")

        return wrapper

    return decorator


def track_embedding_generation():
    """Context manager to track embedding generation time"""

    class EmbeddingTimer:
        def __enter__(self):
            self.start_time = time.time()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            duration = time.time() - self.start_time
            embedding_generation_time.observe(duration)
            logger.debug(f"Embedding generation took {duration:.3f}s")

    return EmbeddingTimer()


def track_vector_search():
    """Context manager to track vector search time"""

    class SearchTimer:
        def __enter__(self):
            self.start_time = time.time()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            duration = time.time() - self.start_time
            vector_search_latency.observe(duration)
            logger.debug(f"Vector search took {duration:.3f}s")

    return SearchTimer()


def track_rag_generation():
    """Context manager to track RAG generation time"""

    class RAGTimer:
        def __enter__(self):
            self.start_time = time.time()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            duration = time.time() - self.start_time
            rag_generation_time.observe(duration)
            logger.debug(f"RAG generation took {duration:.3f}s")

    return RAGTimer()


def track_hybrid_search(search_type: str = "hybrid"):
    """Context manager to track hybrid search time"""

    class HybridSearchTimer:
        def __enter__(self):
            self.start_time = time.time()
            self.search_type = search_type
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            duration = time.time() - self.start_time
            hybrid_search_performance.labels(search_type=self.search_type).observe(
                duration
            )
            logger.debug(f"{self.search_type} search took {duration:.3f}s")

    return HybridSearchTimer()


def track_reranking():
    """Context manager to track reranking time"""

    class RerankingTimer:
        def __enter__(self):
            self.start_time = time.time()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            duration = time.time() - self.start_time
            reranking_latency.observe(duration)
            logger.debug(f"Reranking took {duration:.3f}s")

    return RerankingTimer()


def update_document_metrics(doc_type: str):
    """Update document processing metrics"""
    documents_processed.labels(document_type=doc_type).inc()


def update_index_metrics(num_documents: int, num_chunks: int):
    """Update index size metrics"""
    documents_in_index.set(num_documents)
    chunks_in_index.set(num_chunks)


def track_search_results(num_results: int, search_type: str = "vector"):
    """Track number of search results returned"""
    search_results_returned.labels(search_type=search_type).observe(num_results)


def initialize_metrics(app_version: str = "1.0.0", environment: str = "production"):
    """Initialize system metrics"""
    system_info.info(
        {
            "version": app_version,
            "environment": environment,
            "rag_enabled": "true",
            "hybrid_search": "true",
            "reranking": "true",
        }
    )
    logger.info(f"Metrics initialized for version {app_version} in {environment}")
