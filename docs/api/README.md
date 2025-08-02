# API Reference Guide

## Overview

The Document Intelligence API provides a comprehensive RESTful interface for document processing, search, and question-answering capabilities. Built on OpenAPI 3.0 standards, our API offers predictable resource-oriented URLs, standard HTTP response codes, and JSON-formatted responses.

## Base URL

```
Production: https://api.document-intelligence.ai/v1
Development: http://localhost:8000/api/v1
```

## Authentication

All API requests require authentication using an API key passed in the header:

```http
X-API-Key: your-api-key-here
```

## Rate Limiting

API requests are rate-limited to ensure service stability:

- **Standard tier**: 100 requests per minute
- **Enterprise tier**: 1000 requests per minute

Rate limit headers are included in all responses:
- `X-RateLimit-Limit`: Maximum requests per window
- `X-RateLimit-Remaining`: Requests remaining in current window
- `X-RateLimit-Reset`: UTC timestamp when window resets

## API Endpoints

### Document Management

#### Upload Document
```http
POST /documents/upload
```

Uploads a document for processing and indexing.

**Request:**
- Method: `POST`
- Content-Type: `multipart/form-data`
- Body: File upload (PDF, TXT, MD, RST)

**Response:**
```json
{
  "document_id": "doc_123abc",
  "filename": "report.pdf",
  "status": "processed",
  "chunks_created": 42,
  "processing_time": 1.23
}
```

#### List Documents
```http
GET /documents
```

Retrieves a paginated list of all documents.

**Query Parameters:**
- `page` (integer): Page number (default: 1)
- `limit` (integer): Items per page (default: 20, max: 100)
- `sort` (string): Sort field (created_at, filename)
- `order` (string): Sort order (asc, desc)

#### Get Document
```http
GET /documents/{document_id}
```

Retrieves detailed information about a specific document.

#### Delete Document
```http
DELETE /documents/{document_id}
```

Permanently removes a document and its associated data.

### Search Operations

#### Vector Search
```http
POST /search
```

Performs semantic search across all documents.

**Request Body:**
```json
{
  "text": "search query",
  "top_k": 5,
  "similarity_threshold": 0.7,
  "filter": {
    "document_ids": ["doc_123", "doc_456"],
    "date_range": {
      "start": "2024-01-01",
      "end": "2024-12-31"
    }
  }
}
```

#### Advanced Search
```http
POST /search/advanced
```

Performs hybrid search combining vector similarity and keyword matching.

**Request Body:**
```json
{
  "text": "search query",
  "search_type": "hybrid",
  "top_k": 10,
  "rerank": true,
  "boost_keywords": ["important", "critical"]
}
```

### Question Answering

#### Generate Answer
```http
POST /query
```

Generates an answer based on document context.

**Request Body:**
```json
{
  "text": "What is the main conclusion?",
  "max_tokens": 500,
  "temperature": 0.7,
  "stream": false
}
```

#### Stream Answer
```http
POST /query/stream
```

Generates an answer with real-time streaming response.

### System Operations

#### Health Check
```http
GET /health
```

Returns system health status and component availability.

#### Readiness Check
```http
GET /ready
```

Indicates if the service is ready to handle requests.

## Error Handling

The API uses standard HTTP status codes and returns detailed error messages:

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "The request body is missing required fields",
    "details": {
      "missing_fields": ["text"],
      "request_id": "req_abc123"
    }
  }
}
```

### Common Error Codes

| Status Code | Error Code | Description |
|-------------|------------|-------------|
| 400 | INVALID_REQUEST | Malformed request syntax |
| 401 | UNAUTHORIZED | Missing or invalid API key |
| 403 | FORBIDDEN | Insufficient permissions |
| 404 | NOT_FOUND | Resource not found |
| 413 | PAYLOAD_TOO_LARGE | File size exceeds limit |
| 429 | RATE_LIMITED | Too many requests |
| 500 | INTERNAL_ERROR | Server error |

## SDKs and Libraries

Official SDKs are available for:
- Python: `pip install document-intelligence-sdk`
- Node.js: `npm install @document-intelligence/sdk`
- Java: Maven dependency available
- Go: `go get github.com/document-intelligence/go-sdk`

## Webhooks

Configure webhooks to receive real-time notifications:

```json
{
  "url": "https://your-server.com/webhook",
  "events": ["document.processed", "document.deleted"],
  "secret": "webhook_secret_key"
}
```

## Best Practices

1. **Pagination**: Always use pagination for list endpoints
2. **Caching**: Implement client-side caching using ETags
3. **Retries**: Implement exponential backoff for failed requests
4. **Compression**: Enable gzip compression for responses
5. **Monitoring**: Track API usage and response times

## Support

For API support and questions:
- Email: api-support@document-intelligence.ai
- Documentation: https://docs.document-intelligence.ai
- Status Page: https://status.document-intelligence.ai