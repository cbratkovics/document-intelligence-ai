# Architecture Overview

## System Design

The Document Intelligence AI system follows a microservices architecture pattern with clear separation of concerns:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│   Client Apps   │────▶│   FastAPI       │────▶│  ChromaDB       │
│   (Web/CLI)     │     │   Gateway       │     │  Vector Store   │
│                 │     │                 │     │                 │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                        ┌────────┴────────┐
                        │                 │
                        ▼                 ▼
                ┌──────────────┐  ┌──────────────┐
                │              │  │              │
                │   OpenAI     │  │    Redis     │
                │   LLM API    │  │    Cache     │
                │              │  │              │
                └──────────────┘  └──────────────┘
```

## Core Components

### 1. API Gateway (FastAPI)
- **Location**: `src/api/`
- **Responsibility**: HTTP request handling, authentication, rate limiting
- **Key Features**:
  - Automatic API documentation (OpenAPI/Swagger)
  - Request validation with Pydantic
  - Streaming response support
  - Health checks and monitoring endpoints

### 2. Document Processing Pipeline
- **Location**: `src/core/`
- **Components**:
  - **Document Loader** (`utils/document_loader.py`): Multi-format support
  - **Text Chunker** (`core/chunking.py`): Intelligent text segmentation
  - **Embedding Generator** (`core/embeddings.py`): Vector generation

### 3. RAG Engine
- **Location**: `src/rag/`
- **Components**:
  - **Retriever** (`retriever.py`): Semantic search implementation
  - **Generator** (`generator.py`): LLM-based answer generation
  - **Hybrid Search** (`hybrid_search.py`): Vector + keyword combination
  - **Reranker** (`reranker.py`): Cross-encoder for result optimization

### 4. Vector Database (ChromaDB)
- **Purpose**: Persistent storage for document embeddings
- **Features**:
  - High-performance similarity search
  - Metadata filtering
  - Collection management
  - Scalable to millions of documents

### 5. Caching Layer (Redis)
- **Purpose**: Performance optimization
- **Cached Data**:
  - Search results
  - Generated embeddings
  - LLM responses
  - Document metadata

## Data Flow

### Document Upload Flow
```
1. Client uploads document
2. API validates file format and size
3. Document loader extracts text
4. Text chunker segments content
5. Embeddings generated for each chunk
6. Vectors stored in ChromaDB
7. Metadata indexed in Redis
8. Success response to client
```

### Query Processing Flow
```
1. Client sends query
2. Query embedding generated
3. Hybrid search executed:
   - Vector similarity search
   - BM25 keyword search
   - Results merged and reranked
4. Context retrieved from top results
5. LLM generates answer with context
6. Response streamed to client
7. Results cached for performance
```

## Scalability Considerations

### Horizontal Scaling
- **API Layer**: Multiple FastAPI instances behind load balancer
- **Vector Store**: ChromaDB supports sharding and replication
- **Cache**: Redis cluster for high availability

### Performance Optimizations
1. **Lazy Model Loading**: ML models loaded on-demand
2. **Connection Pooling**: Reused database connections
3. **Batch Processing**: Bulk operations for embeddings
4. **Async Operations**: Non-blocking I/O throughout

## Security Architecture

### API Security
- API key authentication
- Rate limiting per client
- Input validation and sanitization
- CORS configuration

### Data Security
- Encrypted storage for sensitive documents
- Secure communication (HTTPS)
- Environment variable management
- No hardcoded secrets

## Monitoring & Observability

### Metrics Collection
- **Prometheus**: System and application metrics
- **OpenTelemetry**: Distributed tracing
- **Custom Metrics**:
  - Request latency
  - Document processing time
  - Search accuracy
  - Cache hit rates

### Health Checks
- Component-level health status
- Database connectivity checks
- External service availability
- Resource utilization monitoring

## Deployment Architecture

### Docker Containerization
- **Multi-stage builds**: Optimized image sizes
- **Layer caching**: Fast rebuilds
- **Non-root users**: Security best practice
- **Resource limits**: Prevent resource exhaustion

### Kubernetes Ready
- Configurable via environment variables
- Stateless API design
- Persistent volume support
- Service mesh compatible

## Technology Stack

### Core Technologies
- **Python 3.11**: Modern Python features
- **FastAPI**: High-performance web framework
- **Pydantic**: Data validation
- **ChromaDB**: Vector database
- **Redis**: Caching layer

### ML/AI Stack
- **OpenAI GPT**: Text generation
- **Sentence Transformers**: Embeddings
- **LangChain**: RAG orchestration
- **NumPy/Pandas**: Data processing

### Infrastructure
- **Docker**: Containerization
- **GitHub Actions**: CI/CD
- **Prometheus**: Monitoring
- **pytest**: Testing framework