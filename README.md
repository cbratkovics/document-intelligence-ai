# Document Intelligence AI

A production-grade document intelligence system with RAG (Retrieval-Augmented Generation) architecture for intelligent document processing and question answering.

## Features

- **Document Processing**: Support for PDF, TXT, MD, and RST files
- **Intelligent Chunking**: Smart document splitting with configurable chunk sizes
- **Vector Search**: ChromaDB-powered semantic search with hybrid (vector + keyword) capabilities
- **AI-Powered Answers**: Generate contextual answers using OpenAI LLMs
- **RESTful API**: FastAPI-based endpoints with automatic documentation
- **Streaming Responses**: Real-time answer generation with streaming support
- **Document Management**: Upload, list, retrieve, and delete documents
- **Production Ready**: Docker support, CI/CD pipeline, comprehensive testing

## Quick Start

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- OpenAI API key

### Local Development

1. Clone the repository:
```bash
git clone https://github.com/cbratkovics/document-intelligence-ai.git
cd document-intelligence-ai
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env and add your OpenAI API key
```

5. Run the application:
```bash
uvicorn src.api.main:app --reload
```

The API will be available at `http://localhost:8000`

### Docker Deployment

1. Start the services:
```bash
docker-compose -f docker/docker-compose.yml up -d
```

This will start:
- Document Intelligence API (port 8000)
- ChromaDB vector database (port 8001)
- Redis cache (port 6379)

2. Access the API documentation at `http://localhost:8000/docs`

## API Usage

### Upload a Document

```bash
curl -X POST "http://localhost:8000/api/v1/documents/upload" \
  -F "file=@document.pdf"
```

### Query Documents

```bash
curl -X POST "http://localhost:8000/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{"text": "What is the main topic of the document?"}'
```

### Search Documents

```bash
curl -X POST "http://localhost:8000/api/v1/search" \
  -H "Content-Type: application/json" \
  -d '{"text": "machine learning", "top_k": 5}'
```

## Architecture

```
document-intelligence-ai/
├── src/
│   ├── api/          # FastAPI endpoints
│   ├── core/         # Core functionality (config, chunking, embeddings)
│   ├── rag/          # RAG retriever and generator
│   └── utils/        # Utilities (document loader)
├── tests/            # Test suite
├── docker/           # Docker configuration
└── .github/          # CI/CD workflows
```

## Configuration

Key configuration options in `.env`:

- `OPENAI_API_KEY`: Your OpenAI API key (required)
- `CHUNK_SIZE`: Document chunk size (default: 1000)
- `CHUNK_OVERLAP`: Overlap between chunks (default: 200)
- `SEARCH_TOP_K`: Number of search results (default: 5)
- `SIMILARITY_THRESHOLD`: Minimum similarity score (default: 0.7)

## Testing

Run the test suite:

```bash
pytest tests/ -v
```

Run with coverage:

```bash
pytest tests/ --cov=src --cov-report=html
```

## CI/CD

The project includes GitHub Actions workflows for:
- Running tests on push/PR
- Building and testing Docker images
- Pushing to Docker Hub (on main branch)
- Security scanning with Trivy
- Secret detection with TruffleHog

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and feature requests, please use the [GitHub Issues](https://github.com/cbratkovics/document-intelligence-ai/issues) page.