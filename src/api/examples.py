"""
OpenAPI examples for better API documentation
"""

# Query examples
query_examples = {
    "simple_query": {
        "summary": "Simple question",
        "description": "Basic question answering",
        "value": {"text": "What is machine learning?", "top_k": 5},
    },
    "filtered_query": {
        "summary": "Query with filters",
        "description": "Search with metadata filters",
        "value": {
            "text": "Legal requirements for data processing",
            "filters": {"document_type": "legal"},
            "top_k": 10,
        },
    },
    "streaming_query": {
        "summary": "Streaming response",
        "description": "Get streaming response for real-time interaction",
        "value": {"text": "Explain the key concepts in the document", "stream": True},
    },
}

# Advanced search examples
advanced_search_examples = {
    "hybrid_search": {
        "summary": "Hybrid search",
        "description": "Combine vector and keyword search",
        "value": {
            "text": "data privacy regulations GDPR",
            "top_k": 10,
            "use_hybrid": True,
            "use_reranker": True,
            "alpha": 0.7,
        },
    },
    "keyword_focused": {
        "summary": "Keyword-focused search",
        "description": "Emphasize keyword matching",
        "value": {
            "text": "section 3.2 compliance requirements",
            "top_k": 5,
            "use_hybrid": True,
            "use_reranker": False,
            "alpha": 0.3,
        },
    },
    "semantic_only": {
        "summary": "Pure semantic search",
        "description": "Vector search without keyword matching",
        "value": {
            "text": "How does the system handle user authentication?",
            "top_k": 10,
            "use_hybrid": False,
            "use_reranker": True,
        },
    },
}

# Document upload examples
upload_examples = {
    "pdf_with_metadata": {
        "summary": "PDF with metadata",
        "description": "Upload PDF document with custom metadata",
        "value": {
            "metadata": '{"document_type": "technical", "version": "1.0", "tags": ["ml", "ai"]}'
        },
    },
    "text_document": {
        "summary": "Plain text document",
        "description": "Upload a simple text file",
        "value": {"metadata": '{"source": "internal", "department": "engineering"}'},
    },
}

# Response examples
response_examples = {
    200: {
        "description": "Successful response",
        "content": {
            "application/json": {
                "example": {
                    "answer": "Machine learning is a subset of artificial intelligence...",
                    "sources": [
                        {
                            "content": "Machine learning (ML) is a field of inquiry...",
                            "relevance_score": 0.92,
                            "chunk_id": "doc123_0",
                            "metadata": {"filename": "ml_basics.pdf", "page": 1},
                        }
                    ],
                    "confidence": 0.85,
                    "processing_time": 1.234,
                }
            }
        },
    },
    400: {
        "description": "Bad request",
        "content": {
            "application/json": {"example": {"detail": "Invalid query parameters"}}
        },
    },
    404: {
        "description": "Not found",
        "content": {"application/json": {"example": {"detail": "Document not found"}}},
    },
    500: {
        "description": "Internal server error",
        "content": {
            "application/json": {"example": {"detail": "An unexpected error occurred"}}
        },
    },
}
