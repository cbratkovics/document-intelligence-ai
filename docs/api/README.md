# API Reference Guide

## Overview

The Document Intelligence RAG System provides a RESTful API for document processing, semantic search, and question answering. Built with FastAPI, it offers automatic API documentation, streaming responses, and comprehensive monitoring.

## Base URL

```
Development: http://localhost:8000
API Endpoints: http://localhost:8000/api/v1
```

## Interactive Documentation

FastAPI automatically generates interactive API documentation:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI Schema**: `http://localhost:8000/openapi.json`

## Authentication

The API supports API key authentication (configuration in progress). Include your API key in request headers:

```http
X-API-Key: your-api-key-here
```

## Rate Limiting

- **Document Upload**: 10 MB max file size
- **Search Queries**: 100 requests per minute
- **Document Processing**: 50 documents per hour

---

## Core Endpoints

### System Status

#### `GET /`
Root endpoint with API information.

**Response:**
```json
{
  "name": "Document Intelligence AI",
  "version": "0.1.0",
  "status": "operational",
  "docs": "/docs",
  "health": "/health"
}
```

#### `GET /health`
Comprehensive health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-21T10:00:00Z",
  "components": {
    "system": {
      "status": "healthy",
      "cpu_percent": 15.2,
      "memory_percent": 45.3,
      "disk_percent": 62.1
    },
    "chromadb": {
      "status": "healthy",
      "collections": 1,
      "documents": 150
    },
    "redis": {
      "status": "healthy",
      "connected": true,
      "ping_time_ms": 0.5
    },
    "openai": {
      "status": "healthy",
      "model": "text-embedding-ada-002"
    }
  },
  "response_time_ms": 12.5
}
```

#### `GET /metrics`
Prometheus-compatible metrics endpoint for monitoring.

---

### Document Management

#### `POST /api/v1/documents/upload`
Upload and process documents for indexing.

**Request:**
- Method: `POST`
- Content-Type: `multipart/form-data`

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| file | file | Yes | Document file (PDF, TXT, MD, RST) |
| metadata | string | No | JSON metadata string |

**Supported File Types:**
- PDF (`.pdf`)
- Text (`.txt`)
- Markdown (`.md`)
- reStructuredText (`.rst`)

**Example Request:**
```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "X-API-Key: your-api-key" \
  -F "file=@document.pdf" \
  -F 'metadata={"department":"engineering","version":"1.0"}'
```

**Response:**
```json
{
  "document_id": "doc_abc123",
  "filename": "document.pdf",
  "status": "processed",
  "message": "Document uploaded and processed successfully",
  "chunks_created": 42
}
```

#### `GET /api/v1/documents`
List all documents in the system.

**Response:**
```json
[
  {
    "doc_id": "doc_abc123",
    "filename": "document.pdf",
    "chunks": 42,
    "added_at": "2025-01-21T10:00:00Z"
  }
]
```

#### `GET /api/v1/documents/{doc_id}`
Get information about a specific document.

**Path Parameters:**
- `doc_id` (string): Document ID

**Response:**
```json
{
  "doc_id": "doc_abc123",
  "filename": "document.pdf",
  "chunks": 42,
  "added_at": "2025-01-21T10:00:00Z"
}
```

#### `DELETE /api/v1/documents/{doc_id}`
Delete a document from the system.

**Path Parameters:**
- `doc_id` (string): Document ID

**Response:**
```json
{
  "message": "Document deleted successfully",
  "doc_id": "doc_abc123"
}
```

#### `POST /api/v1/documents/{doc_id}/summary`
Generate a summary for a specific document.

**Path Parameters:**
- `doc_id` (string): Document ID

**Query Parameters:**
- `max_length` (integer): Maximum summary length (default: 500)

---

### Search & Retrieval

#### `POST /api/v1/search`
Basic semantic search across documents.

**Request Body:**
```json
{
  "text": "What are the performance optimizations?",
  "top_k": 5,
  "filters": {
    "department": "engineering"
  }
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| text | string | Yes | Search query text |
| top_k | integer | No | Number of results (default: 5) |
| filters | object | No | Metadata filters |

**Response:**
```json
{
  "query": "What are the performance optimizations?",
  "results": [
    {
      "chunk_id": "chunk_123",
      "content": "Performance optimizations include...",
      "score": 0.92,
      "metadata": {
        "filename": "optimization_guide.pdf",
        "page": 12
      }
    }
  ],
  "total": 5
}
```

#### `POST /api/v1/search/advanced`
Advanced hybrid search with customizable strategies.

**Request Body:**
```json
{
  "text": "Docker optimization techniques",
  "top_k": 10,
  "use_hybrid": true,
  "use_reranker": true,
  "alpha": 0.7,
  "filters": null
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| text | string | Yes | Search query text |
| top_k | integer | No | Number of results (default: 10) |
| use_hybrid | boolean | No | Enable hybrid search (default: true) |
| use_reranker | boolean | No | Enable cross-encoder reranking (default: true) |
| alpha | float | No | Vector search weight 0-1 (default: 0.7) |
| filters | object | No | Metadata filters |

**Features:**
- **Hybrid Search**: Combines vector embeddings with BM25 keyword search
- **Cross-Encoder Reranking**: Uses LLM to rerank results for better relevance
- **Configurable Weights**: Adjust balance between semantic and keyword matching

**Response:**
```json
{
  "query": "Docker optimization techniques",
  "results": [
    {
      "chunk_id": "chunk_456",
      "content": "Multi-stage Docker builds can reduce image size by...",
      "score": 0.94,
      "metadata": {
        "filename": "docker_guide.pdf",
        "page": 8
      }
    }
  ],
  "total": 10,
  "search_config": {
    "hybrid": true,
    "reranker": true,
    "alpha": 0.7
  }
}
```

---

### Question Answering

#### `POST /api/v1/query`
Generate answers using RAG (Retrieval-Augmented Generation).

**Request Body:**
```json
{
  "text": "How do I optimize Docker image size?",
  "top_k": 5,
  "filters": null,
  "stream": false
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| text | string | Yes | Question or query text |
| top_k | integer | No | Number of context chunks (default: 5) |
| filters | object | No | Metadata filters |
| stream | boolean | No | Stream the response (default: false) |

**Process:**
1. Performs semantic search to find relevant documents
2. Uses advanced search with hybrid mode and reranking
3. Generates comprehensive answer using GPT-4
4. Returns source documents for transparency

**Response:**
```json
{
  "answer": "To optimize Docker image size, you should:\n\n1. Use multi-stage builds...",
  "sources": [
    {
      "chunk_id": "chunk_456",
      "content": "Multi-stage builds allow you to...",
      "score": 0.94,
      "metadata": {
        "filename": "docker_guide.pdf",
        "page": 8
      }
    }
  ],
  "confidence": 0.89,
  "processing_time": 1.234
}
```

#### `POST /api/v1/query/stream`
Generate answers with real-time streaming response.

**Request Body:**
Same as `/api/v1/query`

**Response:**
Returns a streaming text response with:
- Content-Type: `text/plain`
- Cache-Control: `no-cache`
- Real-time token streaming from the LLM

---

## Configuration

### Environment Variables

The application uses the following environment variables:

```bash
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key

# Redis Configuration  
REDIS_URL=redis://localhost:6379

# ChromaDB Configuration
CHROMA_HOST=localhost
CHROMA_PORT=8000

# Application Settings
APP_ENV=development
LOG_LEVEL=INFO
MAX_UPLOAD_SIZE=10485760  # 10MB in bytes
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
SEARCH_TOP_K=10

# Model Settings
EMBEDDING_MODEL=text-embedding-ada-002
LLM_MODEL=gpt-4
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=500
```

---

## Error Handling

The API returns structured error responses:

```json
{
  "detail": "Error message describing what went wrong"
}
```

### HTTP Status Codes

| Status Code | Description |
|-------------|-------------|
| 200 | Success |
| 400 | Bad Request - Invalid input |
| 404 | Not Found - Resource doesn't exist |
| 413 | Payload Too Large - File exceeds size limit |
| 422 | Unprocessable Entity - Validation error |
| 500 | Internal Server Error |

---

## Monitoring & Observability

### Metrics Collection

The application tracks the following metrics via Prometheus:

- `request_count` - Total requests by method, endpoint, and status
- `request_latency` - Request duration in seconds
- `active_requests` - Currently active requests
- `document_processing_time` - Time to process documents
- `search_latency` - Search operation duration
- `cache_hit_rate` - Cache effectiveness

### System Information

Available in health check responses:
- CPU usage percentage
- Memory usage (MB and percentage)
- Disk usage (GB and percentage)
- Process information (PID, threads, uptime)
- Component connectivity status

---

## Docker Deployment

### Using Docker Compose

```bash
# Start all services
docker-compose -f docker/docker-compose.yml up -d

# Services included:
# - app: Main FastAPI application (port 8000)
# - redis: Cache layer (port 6379)
# - chromadb: Vector database (port 8001)
# - prometheus: Metrics collection (port 9090)
# - grafana: Monitoring dashboards (port 3000)
```

### Docker Image Variants

- **Base** (`~600MB`): Production API with OpenAI embeddings
- **ML** (`~900MB`): Includes local ML models
- **Dev** (`~1GB`): Development with hot reload

---

## Architecture Components

### Core Technologies

- **FastAPI**: High-performance async web framework
- **ChromaDB**: Vector database for embeddings
- **Redis**: Caching and performance optimization
- **OpenAI API**: Embeddings and text generation
- **BM25 (rank-bm25)**: Keyword-based search
- **Pydantic**: Request/response validation

### RAG Pipeline

1. **Document Processing**:
   - Multi-format support (PDF, TXT, MD, RST)
   - Intelligent chunking strategies
   - Metadata extraction

2. **Hybrid Search**:
   - Vector similarity (ChromaDB)
   - Keyword matching (BM25)
   - Cross-encoder reranking

3. **Answer Generation**:
   - Context retrieval
   - GPT-4 generation
   - Source attribution

---

## Performance Optimization

### Caching Strategy
- Redis caching for frequently accessed data
- Document metadata caching
- Search result caching with TTL

### Async Processing
- Non-blocking I/O operations
- Concurrent document processing
- Streaming response support

### Resource Management
- Connection pooling for databases
- Lazy loading of ML models
- Automatic garbage collection

---

## Best Practices

1. **Document Upload**:
   - Keep files under 10MB
   - Use appropriate file formats
   - Include relevant metadata

2. **Search Optimization**:
   - Use specific, descriptive queries
   - Leverage metadata filters
   - Enable hybrid search for better results

3. **Performance**:
   - Batch document uploads when possible
   - Use streaming for long responses
   - Monitor metrics for optimization

---

## Support & Resources

- **GitHub Repository**: [document-intelligence-ai](https://github.com/cbratkovics/document-intelligence-ai)
- **Interactive API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Integration Examples**: [examples.md](examples.md)

For additional help or bug reports, please open an issue on GitHub.