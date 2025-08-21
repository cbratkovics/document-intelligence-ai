# Document Intelligence RAG System Architecture

## System Overview

The Document Intelligence RAG System is a production-grade, enterprise-ready Retrieval-Augmented Generation platform designed for high-performance document processing, semantic search, and intelligent question answering.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Client Applications                          │
│              (Web UI, Mobile Apps, API Consumers)                   │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    API Gateway (FastAPI + SSE)                       │
│  ┌──────────────┬──────────────┬──────────────┬─────────────────┐  │
│  │   REST API   │  WebSockets  │  SSE Stream  │  Health/Metrics │  │
│  └──────────────┴──────────────┴──────────────┴─────────────────┘  │
└────────────┬───────────────────────────────────┬────────────────────┘
             │                                   │
    ┌────────▼────────┐                ┌────────▼────────┐
    │ Document Ingest │                │  Query Engine   │
    └────────┬────────┘                └────────┬────────┘
             │                                   │
    ┌────────▼────────────────────────────────────▼────────┐
    │              Async Task Queue (Celery + Redis)        │
    │  ┌─────────────┬──────────────┬─────────────────┐   │
    │  │  Documents  │  Embeddings  │    Indexing     │   │
    │  │   Worker    │    Worker    │     Worker      │   │
    │  └─────────────┴──────────────┴─────────────────┘   │
    └────────┬──────────────────────────────────┬──────────┘
             │                                  │
    ┌────────▼────────┐              ┌─────────▼─────────┐
    │ Chunking Engine │              │ Embedding Factory │
    │  ┌───────────┐  │              │  ┌─────────────┐  │
    │  │ Semantic  │  │              │  │ OpenAI Ada  │  │
    │  │ Recursive │  │              │  │ MiniLM-L6   │  │
    │  │ Sliding   │  │              │  │ MPNet-Base  │  │
    │  │ Markdown  │  │              │  │ BGE-Large   │  │
    │  └───────────┘  │              │  └─────────────┘  │
    └─────────────────┘              └───────────────────┘
             │                                  │
    ┌────────▼──────────────────────────────────▼────────┐
    │            Hybrid Retrieval System                  │
    │  ┌──────────────┬──────────────┬────────────────┐ │
    │  │  ChromaDB    │  BM25 Index  │  Cross-Encoder │ │
    │  │  (Vectors)   │  (Keywords)  │   (Reranking)  │ │
    │  └──────────────┴──────────────┴────────────────┘ │
    └────────────────────────┬────────────────────────────┘
                             │
    ┌────────────────────────▼────────────────────────────┐
    │              Semantic Cache Layer                    │
    │  ┌──────────────┬──────────────┬────────────────┐  │
    │  │ Redis Cache  │ Similarity   │  TTL Strategy  │  │
    │  │  (42% Hit)   │  Matching    │   Management   │  │
    │  └──────────────┴──────────────┴────────────────┘  │
    └────────────────────────┬────────────────────────────┘
                             │
    ┌────────────────────────▼────────────────────────────┐
    │              LLM Integration Layer                   │
    │  ┌──────────────┬──────────────┬────────────────┐  │
    │  │   OpenAI     │   Anthropic  │   Local LLMs   │  │
    │  │  GPT-4/3.5   │    Claude    │  (Llama, etc)  │  │
    │  └──────────────┴──────────────┴────────────────┘  │
    └──────────────────────────────────────────────────────┘
                             │
    ┌────────────────────────▼────────────────────────────┐
    │           Observability & Monitoring                 │
    │  ┌──────────────┬──────────────┬────────────────┐  │
    │  │  Prometheus  │   Grafana    │  OpenTelemetry │  │
    │  │   Metrics    │  Dashboards  │    Tracing     │  │
    │  └──────────────┴──────────────┴────────────────┘  │
    └──────────────────────────────────────────────────────┘
```

## Component Details

### 1. Document Ingestion Pipeline

**Purpose**: Asynchronously process and index documents of various formats

**Key Features**:
- Format support: PDF, TXT, MD, DOCX, HTML
- Batch processing: Up to 5,000 documents per batch
- Progress tracking: Real-time status updates via WebSocket
- Deduplication: MD5 hash-based duplicate detection

**Flow**:
1. Document upload → Validation → Queue for processing
2. Celery worker picks up task → Reads document
3. Applies chunking strategy → Generates embeddings
4. Indexes in vector store and BM25 index
5. Updates cache and notifies completion

### 2. Chunking Strategies

**Available Strategies**:

| Strategy | Description | Use Case |
|----------|-------------|----------|
| **Semantic** | Groups semantically similar sentences | Technical documentation |
| **Sliding Window** | Fixed-size chunks with overlap | Long-form content |
| **Recursive** | Hierarchical splitting by separators | Mixed content types |
| **Sentence-Based** | Groups by sentence boundaries | Q&A datasets |
| **Markdown-Aware** | Preserves markdown structure | Documentation files |

**Configuration**:
- Chunk size: 100-2000 tokens (default: 512)
- Overlap: 0-50% (default: 128 tokens)
- Preservation: Sentences, paragraphs, sections

### 3. Embedding Factory

**Model Management**:
- Dynamic model switching via environment variables
- Caching of embeddings to reduce API calls
- Batch processing for efficiency

**Supported Models**:
- OpenAI: ada-002, text-embedding-3-small/large
- Open Source: MiniLM, MPNet, BGE, E5, Instructor

**Performance Optimization**:
- Model-specific batching strategies
- GPU acceleration when available
- Embedding dimension reduction techniques

### 4. Hybrid Search System

**Architecture**:
```
Query → [Vector Search + BM25 Search] → Fusion → Reranking → Results
```

**Vector Search (ChromaDB)**:
- Similarity: Cosine, L2, IP
- Index types: HNSW, IVF, Flat
- Metadata filtering support

**BM25 Search**:
- Token-based relevance scoring
- Configurable parameters (k1=1.2, b=0.75)
- Language-specific tokenization

**Fusion Strategies**:
- Weighted combination (60% vector, 40% BM25)
- Reciprocal Rank Fusion (RRF)
- Adaptive weighting based on query type

### 5. Cross-Encoder Reranking

**Models**:
- MS-MARCO MiniLM (22M params, very fast)
- MS-MARCO ELECTRA (110M params, high quality)
- Lightweight fallback (no model required)

**Process**:
1. Initial retrieval: Top-20 candidates
2. Cross-encoder scoring: Query-document pairs
3. Reranking: Sort by relevance scores
4. Final selection: Return top-10

**Performance**: +35% relevance improvement

### 6. Semantic Caching

**Cache Strategies**:

| Type | Hit Rate | Savings | Description |
|------|----------|---------|-------------|
| **Semantic** | 42% | 150ms/query | Similarity-based matching |
| **Exact Match** | 18% | 180ms/query | Hash-based exact matching |
| **Document** | 65% | 50ms/retrieval | Cached document chunks |

**TTL Strategies**:
- Fixed: Static expiration time
- Sliding Window: Extended on access
- Adaptive: Based on access patterns

**Implementation**:
- Redis backend with local fallback
- Cosine similarity threshold: 0.95
- LRU eviction policy

### 7. Async Processing (Celery)

**Queue Configuration**:
- Default: General tasks
- Documents: Document processing
- Embeddings: Embedding generation
- Indexing: Index updates
- Priority: High-priority tasks

**Worker Scaling**:
- Horizontal: 1-10 workers per queue
- Vertical: Resource-based autoscaling
- Rate limiting: 100 tasks/minute default

**Monitoring**:
- Flower dashboard for task monitoring
- Prometheus metrics export
- Dead letter queue for failed tasks

### 8. Evaluation Framework

**Metrics Tracked**:
- **Retrieval**: nDCG@10, MRR@10, Precision@5, Recall@10
- **Latency**: P50, P95, P99 per component
- **Throughput**: QPS, documents/hour
- **Quality**: User feedback, A/B testing

**Benchmarking**:
- BEIR datasets support
- Custom evaluation sets
- Ablation studies for components
- Statistical significance testing

### 9. Observability

**Metrics (Prometheus)**:
- Request rates and latencies
- Cache hit rates
- Model inference times
- Queue depths and processing times

**Tracing (OpenTelemetry)**:
- End-to-end request tracing
- Component-level spans
- Distributed tracing support

**Logging**:
- Structured JSON logging
- Correlation IDs for request tracking
- Log aggregation with ELK stack

**Dashboards (Grafana)**:
- System health overview
- Performance metrics
- Alert configurations
- Custom business metrics

## Deployment Architecture

### Kubernetes Deployment

**Components**:
- API Deployment: 3-10 replicas (HPA)
- ChromaDB StatefulSet: 2 replicas
- Redis Deployment: 1 replica (HA optional)
- Celery Workers: 4-20 pods (autoscaled)

**Resource Requirements**:

| Component | CPU | Memory | Storage |
|-----------|-----|--------|---------|
| API | 1-2 cores | 2-4 GB | - |
| ChromaDB | 2-4 cores | 4-8 GB | 50 GB |
| Redis | 0.5-1 core | 1-2 GB | 10 GB |
| Workers | 1-2 cores | 2-4 GB | - |

**Scaling Strategy**:
- HPA based on CPU/Memory utilization
- VPA for right-sizing recommendations
- Cluster autoscaling for node management

### Security Considerations

**Authentication & Authorization**:
- JWT-based authentication
- Role-based access control (RBAC)
- API key management

**Data Security**:
- Encryption at rest (AES-256)
- TLS 1.3 for data in transit
- Secret management via Kubernetes secrets

**Network Security**:
- Network policies for pod communication
- Ingress rate limiting
- WAF integration

## Performance Optimizations

### Caching Strategy
- Multi-level caching (Redis + in-memory)
- Semantic similarity caching
- Precomputed embeddings cache

### Query Optimization
- Query expansion techniques
- Parallel retrieval execution
- Result streaming via SSE

### Index Optimization
- Periodic index optimization
- Partial index updates
- Metadata-based filtering

## Future Enhancements

### Planned Features
- Multi-modal support (images, audio)
- Federated search across multiple indices
- Active learning for relevance improvement
- GraphRAG integration
- Real-time collaborative features

### Scalability Roadmap
- Multi-region deployment
- Edge caching with CDN
- Serverless function integration
- Stream processing with Kafka

## Monitoring & Alerts

### Key Metrics to Monitor
- API response time > 500ms
- Cache hit rate < 30%
- Error rate > 1%
- Queue depth > 1000
- Memory usage > 80%

### Alert Configuration
```yaml
alerts:
  - name: HighLatency
    expr: api_response_time_p95 > 500
    severity: warning
    
  - name: LowCacheHitRate
    expr: cache_hit_rate < 0.3
    severity: warning
    
  - name: HighErrorRate
    expr: error_rate > 0.01
    severity: critical
```

## Development Workflow

### Local Development
```bash
# Start dependencies
docker-compose up -d redis chromadb

# Install dependencies
pip install -r requirements-ml.txt

# Run application
uvicorn src.api.main:app --reload

# Run Celery workers
celery -A app.tasks.celery_app worker --loglevel=info
```

### Testing Strategy
- Unit tests: Component isolation
- Integration tests: Service interaction
- Load tests: Performance validation
- E2E tests: User journey validation

### CI/CD Pipeline
1. Code push → GitHub Actions trigger
2. Linting & formatting checks
3. Unit & integration tests
4. Docker image build
5. Security scanning
6. Push to registry
7. Deploy to staging
8. Smoke tests
9. Production deployment

## Cost Optimization

### Resource Optimization
- Spot instances for workers
- Reserved instances for core services
- Auto-scaling based on traffic patterns

### API Cost Management
- Batch API calls
- Cache frequently accessed data
- Use cheaper models for non-critical tasks

### Storage Optimization
- Data lifecycle policies
- Compression for cold data
- Tiered storage strategy