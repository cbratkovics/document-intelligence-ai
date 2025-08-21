# Integration Examples

This guide provides practical examples for integrating with the Document Intelligence API using various programming languages and tools.

## Table of Contents

- [Python Examples](#python-examples)
- [JavaScript/TypeScript Examples](#javascripttypescript-examples)
- [cURL Examples](#curl-examples)
- [Postman Collection](#postman-collection)
- [Advanced Workflows](#advanced-workflows)
- [Error Handling](#error-handling)
- [Best Practices](#best-practices)

---

## Python Examples

### Installation

```bash
pip install requests aiohttp pandas python-dotenv
```

### Basic Setup

```python
import requests
import json
import os
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

class DocumentIntelligenceClient:
    def __init__(self, base_url: str = "http://localhost:8000", api_key: Optional[str] = None):
        self.base_url = base_url
        self.api_prefix = "/api/v1"
        self.session = requests.Session()
        if api_key:
            self.session.headers.update({"X-API-Key": api_key})
    
    def upload_document(self, file_path: str, metadata: Optional[Dict] = None) -> Dict:
        """Upload a document for processing."""
        with open(file_path, 'rb') as f:
            files = {'file': f}
            data = {'metadata': json.dumps(metadata)} if metadata else {}
            response = self.session.post(
                f"{self.base_url}{self.api_prefix}/documents/upload",
                files=files,
                data=data
            )
            response.raise_for_status()
            return response.json()
    
    def search(self, query: str, top_k: int = 10, use_hybrid: bool = True) -> Dict:
        """Search across documents."""
        response = self.session.post(
            f"{self.base_url}{self.api_prefix}/search",
            json={
                "text": query,  # Note: uses 'text' not 'query'
                "top_k": top_k,
                "filters": None
            }
        )
        response.raise_for_status()
        return response.json()
    
    def advanced_search(
        self, 
        query: str, 
        top_k: int = 10,
        use_hybrid: bool = True,
        use_reranker: bool = True,
        alpha: float = 0.7
    ) -> Dict:
        """Advanced search with hybrid mode and reranking."""
        response = self.session.post(
            f"{self.base_url}{self.api_prefix}/search/advanced",
            json={
                "text": query,
                "top_k": top_k,
                "use_hybrid": use_hybrid,
                "use_reranker": use_reranker,
                "alpha": alpha,
                "filters": None
            }
        )
        response.raise_for_status()
        return response.json()
    
    def ask_question(self, question: str, top_k: int = 5, stream: bool = False) -> Dict:
        """Ask a question using RAG."""
        endpoint = "/query/stream" if stream else "/query"
        response = self.session.post(
            f"{self.base_url}{self.api_prefix}{endpoint}",
            json={
                "text": question,  # Note: uses 'text' not 'question'
                "top_k": top_k,
                "filters": None,
                "stream": stream
            }
        )
        response.raise_for_status()
        return response.json()
    
    def list_documents(self) -> List[Dict]:
        """List all documents."""
        response = self.session.get(f"{self.base_url}{self.api_prefix}/documents")
        response.raise_for_status()
        return response.json()
    
    def get_document(self, doc_id: str) -> Dict:
        """Get document information."""
        response = self.session.get(f"{self.base_url}{self.api_prefix}/documents/{doc_id}")
        response.raise_for_status()
        return response.json()
    
    def delete_document(self, doc_id: str) -> Dict:
        """Delete a document."""
        response = self.session.delete(f"{self.base_url}{self.api_prefix}/documents/{doc_id}")
        response.raise_for_status()
        return response.json()

# Initialize client
client = DocumentIntelligenceClient(api_key=os.getenv("API_KEY"))
```

### Document Upload Example

```python
# Upload a single document
result = client.upload_document(
    "reports/quarterly_report.pdf",
    metadata={
        "department": "finance",
        "quarter": "Q4",
        "year": 2024
    }
)
print(f"Document uploaded: {result['document_id']}")
print(f"Chunks created: {result['chunks_created']}")

# Upload multiple documents with error handling
import glob

pdf_files = glob.glob("documents/*.pdf")
for pdf_file in pdf_files:
    try:
        result = client.upload_document(pdf_file)
        print(f"✓ Uploaded: {os.path.basename(pdf_file)} - {result['chunks_created']} chunks")
    except requests.HTTPError as e:
        if e.response.status_code == 413:
            print(f"✗ File too large: {os.path.basename(pdf_file)}")
        else:
            print(f"✗ Failed: {os.path.basename(pdf_file)} - {e}")
```

### Search Examples

```python
# Basic semantic search
results = client.search(
    query="What are the key performance metrics?",
    top_k=5
)

# Display results
for i, result in enumerate(results['results'], 1):
    print(f"\n{i}. Score: {result.get('score', result.get('relevance_score', 0)):.3f}")
    print(f"   Chunk ID: {result.get('chunk_id', 'N/A')}")
    print(f"   Content: {result['content'][:200]}...")
    if 'metadata' in result:
        print(f"   File: {result['metadata'].get('filename', 'Unknown')}")

# Advanced hybrid search with reranking
results = client.advanced_search(
    query="Docker optimization techniques",
    top_k=10,
    use_hybrid=True,
    use_reranker=True,
    alpha=0.7  # 70% vector, 30% BM25
)

print(f"\nSearch configuration:")
print(f"  Hybrid: {results['search_config']['hybrid']}")
print(f"  Reranker: {results['search_config']['reranker']}")
print(f"  Alpha: {results['search_config']['alpha']}")
print(f"\nFound {results['total']} results")
```

### RAG Question-Answering Example

```python
# Ask a question
response = client.ask_question(
    "How can I optimize Docker container size?",
    top_k=5,
    stream=False
)

print(f"Answer:\n{response['answer']}\n")
print(f"Confidence: {response.get('confidence', 'N/A')}")
print(f"Processing time: {response.get('processing_time', 'N/A')}s")

if 'sources' in response:
    print(f"\nSources ({len(response['sources'])} documents):")
    for source in response['sources']:
        filename = source.get('metadata', {}).get('filename', 'Unknown')
        score = source.get('score', source.get('relevance_score', 0))
        print(f"  - {filename} (relevance: {score:.3f})")
```

### Streaming Response Example

```python
import requests

def stream_answer(question: str, api_key: str = None):
    """Stream answer from the API."""
    headers = {"X-API-Key": api_key} if api_key else {}
    
    response = requests.post(
        "http://localhost:8000/api/v1/query/stream",
        json={"text": question, "top_k": 5, "stream": True},
        headers=headers,
        stream=True
    )
    
    for chunk in response.iter_content(chunk_size=1):
        if chunk:
            print(chunk.decode('utf-8'), end='', flush=True)

# Usage
stream_answer("Explain the RAG architecture")
```

### Batch Processing Example

```python
import asyncio
import aiohttp
from pathlib import Path

async def upload_document_async(session, file_path, base_url, api_key):
    """Async document upload."""
    headers = {"X-API-Key": api_key} if api_key else {}
    
    with open(file_path, 'rb') as f:
        data = aiohttp.FormData()
        data.add_field('file', f, filename=file_path.name)
        
        async with session.post(
            f"{base_url}/api/v1/documents/upload",
            data=data,
            headers=headers
        ) as response:
            return await response.json()

async def batch_upload(directory: str, api_key: str = None):
    """Upload all documents in a directory asynchronously."""
    base_url = "http://localhost:8000"
    files = list(Path(directory).glob("**/*.pdf")) + list(Path(directory).glob("**/*.txt"))
    
    async with aiohttp.ClientSession() as session:
        tasks = [
            upload_document_async(session, file, base_url, api_key)
            for file in files
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results
    successful = sum(1 for r in results if not isinstance(r, Exception))
    print(f"Uploaded {successful}/{len(files)} documents successfully")
    return results

# Run batch upload
results = asyncio.run(batch_upload("documents/", os.getenv("API_KEY")))
```

---

## JavaScript/TypeScript Examples

### Installation

```bash
npm install axios form-data dotenv
# or
yarn add axios form-data dotenv
```

### TypeScript Client

```typescript
import axios, { AxiosInstance } from 'axios';
import FormData from 'form-data';
import fs from 'fs';
import path from 'path';

interface SearchResult {
  chunk_id: string;
  content: string;
  score?: number;
  relevance_score?: number;
  metadata: Record<string, any>;
}

interface QueryResponse {
  answer: string;
  sources: SearchResult[];
  confidence: number;
  processing_time: number;
}

interface SearchResponse {
  query: string;
  results: SearchResult[];
  total: number;
  search_config?: {
    hybrid: boolean;
    reranker: boolean;
    alpha: number;
  };
}

class DocumentIntelligenceClient {
  private client: AxiosInstance;
  private apiPrefix = '/api/v1';

  constructor(baseURL: string = 'http://localhost:8000', apiKey?: string) {
    this.client = axios.create({
      baseURL,
      headers: apiKey ? { 'X-API-Key': apiKey } : {},
    });
  }

  async uploadDocument(
    filePath: string,
    metadata?: Record<string, any>
  ): Promise<any> {
    const form = new FormData();
    form.append('file', fs.createReadStream(filePath));
    if (metadata) {
      form.append('metadata', JSON.stringify(metadata));
    }

    const response = await this.client.post(
      `${this.apiPrefix}/documents/upload`,
      form,
      { headers: form.getHeaders() }
    );
    return response.data;
  }

  async search(
    query: string,
    options: {
      topK?: number;
      filters?: Record<string, any>;
    } = {}
  ): Promise<SearchResponse> {
    const response = await this.client.post(`${this.apiPrefix}/search`, {
      text: query,  // Note: API uses 'text' not 'query'
      top_k: options.topK || 10,
      filters: options.filters || null,
    });
    return response.data;
  }

  async advancedSearch(
    query: string,
    options: {
      topK?: number;
      useHybrid?: boolean;
      useReranker?: boolean;
      alpha?: number;
      filters?: Record<string, any>;
    } = {}
  ): Promise<SearchResponse> {
    const response = await this.client.post(`${this.apiPrefix}/search/advanced`, {
      text: query,
      top_k: options.topK || 10,
      use_hybrid: options.useHybrid ?? true,
      use_reranker: options.useReranker ?? true,
      alpha: options.alpha ?? 0.7,
      filters: options.filters || null,
    });
    return response.data;
  }

  async ask(
    question: string,
    topK: number = 5,
    stream: boolean = false
  ): Promise<QueryResponse> {
    const endpoint = stream ? '/query/stream' : '/query';
    const response = await this.client.post(`${this.apiPrefix}${endpoint}`, {
      text: question,  // Note: API uses 'text' not 'question'
      top_k: topK,
      filters: null,
      stream: stream,
    });
    return response.data;
  }

  async listDocuments(): Promise<any[]> {
    const response = await this.client.get(`${this.apiPrefix}/documents`);
    return response.data;
  }

  async deleteDocument(docId: string): Promise<any> {
    const response = await this.client.delete(
      `${this.apiPrefix}/documents/${docId}`
    );
    return response.data;
  }
}

// Usage example
const client = new DocumentIntelligenceClient(
  process.env.API_URL || 'http://localhost:8000',
  process.env.API_KEY
);
```

### React Integration Example

```tsx
import React, { useState, useEffect } from 'react';
import { DocumentIntelligenceClient } from './client';

const SearchInterface: React.FC = () => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<any[]>([]);
  const [answer, setAnswer] = useState('');
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<'search' | 'ask'>('search');
  
  const client = new DocumentIntelligenceClient(
    process.env.REACT_APP_API_URL || 'http://localhost:8000',
    process.env.REACT_APP_API_KEY
  );

  const handleSearch = async () => {
    setLoading(true);
    setAnswer('');
    try {
      const response = await client.advancedSearch(query, {
        topK: 5,
        useHybrid: true,
        useReranker: true,
      });
      setResults(response.results);
    } catch (error) {
      console.error('Search failed:', error);
      alert('Search failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleAsk = async () => {
    setLoading(true);
    setResults([]);
    try {
      const response = await client.ask(query, 5, false);
      setAnswer(response.answer);
      setResults(response.sources || []);
    } catch (error) {
      console.error('Question failed:', error);
      alert('Failed to get answer. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="search-interface">
      <div className="search-bar">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Enter your search query or question..."
          onKeyPress={(e) => e.key === 'Enter' && (mode === 'search' ? handleSearch() : handleAsk())}
        />
        <select value={mode} onChange={(e) => setMode(e.target.value as 'search' | 'ask')}>
          <option value="search">Search</option>
          <option value="ask">Ask</option>
        </select>
        <button 
          onClick={mode === 'search' ? handleSearch : handleAsk} 
          disabled={loading || !query}
        >
          {loading ? 'Processing...' : mode === 'search' ? 'Search' : 'Ask'}
        </button>
      </div>
      
      {answer && (
        <div className="answer-section">
          <h3>Answer:</h3>
          <p>{answer}</p>
        </div>
      )}
      
      {results.length > 0 && (
        <div className="results">
          <h3>{answer ? 'Sources:' : 'Search Results:'}</h3>
          {results.map((result, index) => (
            <div key={index} className="result-item">
              <div className="result-header">
                <span className="result-score">
                  Score: {(result.score || result.relevance_score || 0).toFixed(3)}
                </span>
                <span className="result-file">
                  {result.metadata?.filename || 'Unknown source'}
                </span>
              </div>
              <p className="result-content">{result.content}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default SearchInterface;
```

---

## cURL Examples

### Health Check

```bash
# Check API health
curl http://localhost:8000/health

# Check specific component health with pretty print
curl http://localhost:8000/health | python -m json.tool
```

### Upload Document

```bash
# Simple upload
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "file=@document.pdf"

# With metadata
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "file=@document.pdf" \
  -F 'metadata={"department":"engineering","project":"RAG","version":"1.0"}'

# Upload text file
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "file=@notes.txt" \
  -F 'metadata={"type":"notes","author":"John Doe"}'
```

### List and Manage Documents

```bash
# List all documents
curl -X GET http://localhost:8000/api/v1/documents \
  -H "X-API-Key: YOUR_API_KEY"

# Get specific document info
curl -X GET http://localhost:8000/api/v1/documents/doc_abc123 \
  -H "X-API-Key: YOUR_API_KEY"

# Delete document
curl -X DELETE http://localhost:8000/api/v1/documents/doc_abc123 \
  -H "X-API-Key: YOUR_API_KEY"

# Generate document summary
curl -X POST http://localhost:8000/api/v1/documents/doc_abc123/summary?max_length=500 \
  -H "X-API-Key: YOUR_API_KEY"
```

### Search Documents

```bash
# Basic search
curl -X POST http://localhost:8000/api/v1/search \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "performance optimization techniques",
    "top_k": 5
  }'

# Advanced hybrid search with reranking
curl -X POST http://localhost:8000/api/v1/search/advanced \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Docker best practices",
    "top_k": 10,
    "use_hybrid": true,
    "use_reranker": true,
    "alpha": 0.7,
    "filters": null
  }'

# Search with metadata filters
curl -X POST http://localhost:8000/api/v1/search/advanced \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "security guidelines",
    "top_k": 5,
    "use_hybrid": true,
    "filters": {
      "department": "engineering",
      "year": 2024
    }
  }'
```

### Ask Questions (RAG)

```bash
# Simple question
curl -X POST http://localhost:8000/api/v1/query \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "What are the main components of the RAG system?",
    "top_k": 5
  }'

# Question with all parameters
curl -X POST http://localhost:8000/api/v1/query \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "How can I improve search relevance in my RAG system?",
    "top_k": 10,
    "filters": null,
    "stream": false
  }'

# Stream response (use --no-buffer for real-time streaming)
curl --no-buffer -X POST http://localhost:8000/api/v1/query/stream \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Explain the benefits of hybrid search",
    "top_k": 5
  }'
```

---

## Postman Collection

Import this collection into Postman for easy API testing:

```json
{
  "info": {
    "name": "Document Intelligence API",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "auth": {
    "type": "apikey",
    "apikey": [
      {
        "key": "key",
        "value": "X-API-Key",
        "type": "string"
      },
      {
        "key": "value",
        "value": "{{api_key}}",
        "type": "string"
      },
      {
        "key": "in",
        "value": "header",
        "type": "string"
      }
    ]
  },
  "variable": [
    {
      "key": "base_url",
      "value": "http://localhost:8000",
      "type": "string"
    },
    {
      "key": "api_key",
      "value": "YOUR_API_KEY",
      "type": "string"
    }
  ],
  "item": [
    {
      "name": "Health",
      "item": [
        {
          "name": "Health Check",
          "request": {
            "method": "GET",
            "url": "{{base_url}}/health"
          }
        },
        {
          "name": "API Info",
          "request": {
            "method": "GET",
            "url": "{{base_url}}/"
          }
        }
      ]
    },
    {
      "name": "Documents",
      "item": [
        {
          "name": "Upload Document",
          "request": {
            "method": "POST",
            "url": "{{base_url}}/api/v1/documents/upload",
            "body": {
              "mode": "formdata",
              "formdata": [
                {
                  "key": "file",
                  "type": "file",
                  "src": "document.pdf"
                },
                {
                  "key": "metadata",
                  "value": "{\"department\":\"engineering\"}",
                  "type": "text"
                }
              ]
            }
          }
        },
        {
          "name": "List Documents",
          "request": {
            "method": "GET",
            "url": "{{base_url}}/api/v1/documents"
          }
        },
        {
          "name": "Get Document",
          "request": {
            "method": "GET",
            "url": "{{base_url}}/api/v1/documents/:doc_id"
          }
        },
        {
          "name": "Delete Document",
          "request": {
            "method": "DELETE",
            "url": "{{base_url}}/api/v1/documents/:doc_id"
          }
        }
      ]
    },
    {
      "name": "Search",
      "item": [
        {
          "name": "Basic Search",
          "request": {
            "method": "POST",
            "url": "{{base_url}}/api/v1/search",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "body": {
              "mode": "raw",
              "raw": "{\n  \"text\": \"test query\",\n  \"top_k\": 5\n}"
            }
          }
        },
        {
          "name": "Advanced Search",
          "request": {
            "method": "POST",
            "url": "{{base_url}}/api/v1/search/advanced",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "body": {
              "mode": "raw",
              "raw": "{\n  \"text\": \"Docker optimization\",\n  \"top_k\": 10,\n  \"use_hybrid\": true,\n  \"use_reranker\": true,\n  \"alpha\": 0.7\n}"
            }
          }
        }
      ]
    },
    {
      "name": "Query",
      "item": [
        {
          "name": "Ask Question",
          "request": {
            "method": "POST",
            "url": "{{base_url}}/api/v1/query",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "body": {
              "mode": "raw",
              "raw": "{\n  \"text\": \"What is RAG?\",\n  \"top_k\": 5\n}"
            }
          }
        },
        {
          "name": "Stream Answer",
          "request": {
            "method": "POST",
            "url": "{{base_url}}/api/v1/query/stream",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "body": {
              "mode": "raw",
              "raw": "{\n  \"text\": \"Explain hybrid search\",\n  \"top_k\": 5\n}"
            }
          }
        }
      ]
    }
  ]
}
```

---

## Advanced Workflows

### Document Processing Pipeline

```python
import time
from pathlib import Path
from typing import List, Dict
import json

class DocumentProcessor:
    def __init__(self, client: DocumentIntelligenceClient):
        self.client = client
        self.processing_log = []
    
    def process_directory(
        self, 
        directory: str, 
        extensions: List[str] = ['.pdf', '.txt', '.md', '.rst'],
        metadata_file: str = None
    ) -> Dict:
        """Process all documents in a directory."""
        
        # Load metadata if provided
        metadata_map = {}
        if metadata_file and Path(metadata_file).exists():
            with open(metadata_file, 'r') as f:
                metadata_map = json.load(f)
        
        results = {
            'successful': [],
            'failed': [],
            'skipped': [],
            'total_chunks': 0
        }
        
        # Find all documents
        doc_files = []
        for ext in extensions:
            doc_files.extend(Path(directory).rglob(f"*{ext}"))
        
        print(f"Found {len(doc_files)} documents to process")
        
        for i, file_path in enumerate(doc_files, 1):
            file_str = str(file_path)
            file_name = file_path.name
            
            # Check file size
            file_size = file_path.stat().st_size
            if file_size > 10 * 1024 * 1024:  # 10MB limit
                print(f"[{i}/{len(doc_files)}] ⚠️  Skipping {file_name} - too large ({file_size / 1024 / 1024:.1f}MB)")
                results['skipped'].append(file_str)
                continue
            
            # Get metadata for this file
            metadata = metadata_map.get(file_name, {})
            
            try:
                print(f"[{i}/{len(doc_files)}] 📄 Processing {file_name}...")
                result = self.client.upload_document(file_str, metadata)
                
                results['successful'].append({
                    'file': file_str,
                    'document_id': result['document_id'],
                    'chunks': result.get('chunks_created', 0)
                })
                results['total_chunks'] += result.get('chunks_created', 0)
                
                print(f"    ✅ Success - {result.get('chunks_created', 0)} chunks created")
                
                # Rate limiting
                time.sleep(0.5)
                
            except Exception as e:
                print(f"    ❌ Failed: {str(e)[:100]}")
                results['failed'].append({
                    'file': file_str,
                    'error': str(e)
                })
        
        # Summary
        print(f"\n📊 Processing Summary:")
        print(f"   ✅ Successful: {len(results['successful'])}")
        print(f"   ❌ Failed: {len(results['failed'])}")
        print(f"   ⚠️  Skipped: {len(results['skipped'])}")
        print(f"   📝 Total chunks: {results['total_chunks']}")
        
        return results

# Usage
client = DocumentIntelligenceClient(api_key=os.getenv("API_KEY"))
processor = DocumentProcessor(client)

# Process with metadata
results = processor.process_directory(
    "documents/",
    extensions=['.pdf', '.txt', '.md'],
    metadata_file="documents/metadata.json"
)

# Save processing log
with open("processing_log.json", "w") as f:
    json.dump(results, f, indent=2)
```

### Semantic Cache with Redis

```python
import hashlib
import json
from typing import Optional, Dict
import redis
import numpy as np
from datetime import datetime, timedelta

class SemanticCache:
    def __init__(self, redis_url: str = "redis://localhost:6379", ttl_hours: int = 24):
        self.redis = redis.from_url(redis_url)
        self.ttl = ttl_hours * 3600
        
    def _generate_key(self, query: str, params: Dict) -> str:
        """Generate cache key from query and parameters."""
        # Normalize query
        normalized_query = query.lower().strip()
        
        # Create stable key
        cache_data = {
            'query': normalized_query,
            'top_k': params.get('top_k', 10),
            'use_hybrid': params.get('use_hybrid', True),
            'use_reranker': params.get('use_reranker', False),
            'alpha': params.get('alpha', 0.7)
        }
        
        cache_str = json.dumps(cache_data, sort_keys=True)
        return f"rag:search:{hashlib.md5(cache_str.encode()).hexdigest()}"
    
    def get(self, query: str, params: Dict) -> Optional[Dict]:
        """Retrieve cached results."""
        key = self._generate_key(query, params)
        cached = self.redis.get(key)
        
        if cached:
            data = json.loads(cached)
            print(f"🎯 Cache hit for query: '{query[:50]}...'")
            return data
        
        return None
    
    def set(self, query: str, params: Dict, results: Dict):
        """Cache search results."""
        key = self._generate_key(query, params)
        
        # Add timestamp to cached data
        results['cached_at'] = datetime.now().isoformat()
        
        self.redis.setex(
            key, 
            self.ttl, 
            json.dumps(results)
        )
        
    def clear_pattern(self, pattern: str = "rag:search:*"):
        """Clear cache entries matching pattern."""
        keys = self.redis.keys(pattern)
        if keys:
            self.redis.delete(*keys)
            print(f"Cleared {len(keys)} cache entries")

# Enhanced client with caching
class CachedDocumentClient(DocumentIntelligenceClient):
    def __init__(self, base_url: str = "http://localhost:8000", api_key: str = None):
        super().__init__(base_url, api_key)
        self.cache = SemanticCache()
    
    def search_with_cache(self, query: str, **kwargs) -> Dict:
        """Search with semantic caching."""
        # Check cache
        cached = self.cache.get(query, kwargs)
        if cached:
            return cached
        
        # Perform search
        results = self.search(query, **kwargs)
        
        # Cache results
        self.cache.set(query, kwargs, results)
        
        return results

# Usage
cached_client = CachedDocumentClient(api_key=os.getenv("API_KEY"))

# First search - hits API
results1 = cached_client.search_with_cache("Docker optimization", top_k=5)

# Second search - from cache
results2 = cached_client.search_with_cache("Docker optimization", top_k=5)

# Clear cache when needed
cached_client.cache.clear_pattern("rag:search:*")
```

---

## Error Handling

### Comprehensive Error Handler

```python
from enum import Enum
from typing import Optional, Callable
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RetryStrategy(Enum):
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIXED = "fixed"

class RobustAPIClient:
    def __init__(
        self, 
        base_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        max_retries: int = 3,
        retry_strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    ):
        self.client = DocumentIntelligenceClient(base_url, api_key)
        self.max_retries = max_retries
        self.retry_strategy = retry_strategy
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay based on retry strategy."""
        if self.retry_strategy == RetryStrategy.EXPONENTIAL:
            return min(2 ** attempt, 30)  # Cap at 30 seconds
        elif self.retry_strategy == RetryStrategy.LINEAR:
            return attempt * 2
        else:  # FIXED
            return 5
    
    def _execute_with_retry(
        self, 
        func: Callable, 
        *args, 
        **kwargs
    ) -> any:
        """Execute function with retry logic."""
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
                
            except requests.HTTPError as e:
                status_code = e.response.status_code if e.response else 0
                
                # Don't retry client errors (4xx)
                if 400 <= status_code < 500:
                    if status_code == 429:  # Rate limited
                        retry_after = e.response.headers.get('Retry-After', 60)
                        logger.warning(f"Rate limited. Waiting {retry_after}s...")
                        time.sleep(int(retry_after))
                        continue
                    else:
                        logger.error(f"Client error {status_code}: {e}")
                        raise
                
                # Retry server errors (5xx)
                if status_code >= 500:
                    delay = self._calculate_delay(attempt)
                    logger.warning(f"Server error {status_code}. Retry {attempt + 1}/{self.max_retries} in {delay}s...")
                    time.sleep(delay)
                    last_exception = e
                    continue
                    
            except requests.ConnectionError as e:
                delay = self._calculate_delay(attempt)
                logger.warning(f"Connection error. Retry {attempt + 1}/{self.max_retries} in {delay}s...")
                time.sleep(delay)
                last_exception = e
                continue
                
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                raise
        
        # All retries exhausted
        logger.error(f"All {self.max_retries} retries failed")
        raise last_exception
    
    def upload_document(self, file_path: str, metadata: Optional[Dict] = None) -> Dict:
        """Upload with retry logic."""
        return self._execute_with_retry(
            self.client.upload_document,
            file_path,
            metadata
        )
    
    def search(self, query: str, **kwargs) -> Dict:
        """Search with retry logic."""
        return self._execute_with_retry(
            self.client.search,
            query,
            **kwargs
        )

# Usage with error handling
robust_client = RobustAPIClient(
    api_key=os.getenv("API_KEY"),
    max_retries=3,
    retry_strategy=RetryStrategy.EXPONENTIAL
)

try:
    # This will retry on server errors
    result = robust_client.upload_document("large_document.pdf")
    print(f"Success: {result['document_id']}")
    
except requests.HTTPError as e:
    if e.response.status_code == 413:
        print("File too large. Please reduce file size.")
    elif e.response.status_code == 400:
        print("Invalid request. Check your parameters.")
    else:
        print(f"HTTP error: {e}")
        
except Exception as e:
    print(f"Unexpected error: {e}")
```

---

## Best Practices

### 1. **Configuration Management**

```python
# config.py
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class APIConfig:
    base_url: str = os.getenv("API_BASE_URL", "http://localhost:8000")
    api_key: str = os.getenv("API_KEY", "")
    max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
    timeout: int = int(os.getenv("API_TIMEOUT", "30"))
    
    # Search defaults
    default_top_k: int = int(os.getenv("DEFAULT_TOP_K", "10"))
    use_hybrid: bool = os.getenv("USE_HYBRID", "true").lower() == "true"
    use_reranker: bool = os.getenv("USE_RERANKER", "true").lower() == "true"
    
    # Cache settings
    cache_ttl_hours: int = int(os.getenv("CACHE_TTL_HOURS", "24"))
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")

config = APIConfig()
```

### 2. **Logging and Monitoring**

```python
import logging
import time
from functools import wraps

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def log_api_call(func):
    """Decorator to log API calls."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        logger = logging.getLogger(func.__module__)
        
        logger.info(f"Calling {func.__name__} with args={args[:2]}, kwargs={list(kwargs.keys())}")
        
        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time
            logger.info(f"Success: {func.__name__} completed in {elapsed:.2f}s")
            return result
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed: {func.__name__} after {elapsed:.2f}s - {str(e)}")
            raise
    
    return wrapper
```

### 3. **Testing Strategy**

```python
# test_api.py
import pytest
from unittest.mock import Mock, patch
import json

class TestDocumentIntelligenceAPI:
    @pytest.fixture
    def client(self):
        return DocumentIntelligenceClient(
            base_url="http://test-api:8000",
            api_key="test-key"
        )
    
    def test_upload_document_success(self, client):
        with patch('requests.Session.post') as mock_post:
            mock_post.return_value.json.return_value = {
                "document_id": "doc_123",
                "chunks_created": 10
            }
            mock_post.return_value.raise_for_status = Mock()
            
            result = client.upload_document("test.pdf")
            
            assert result["document_id"] == "doc_123"
            assert result["chunks_created"] == 10
    
    def test_search_with_reranking(self, client):
        with patch('requests.Session.post') as mock_post:
            mock_post.return_value.json.return_value = {
                "results": [
                    {"content": "test", "score": 0.9}
                ],
                "total": 1
            }
            
            result = client.advanced_search(
                "test query",
                use_reranker=True
            )
            
            assert len(result["results"]) == 1
            assert result["results"][0]["score"] == 0.9
```

### 4. **Performance Tips**

- **Batch Operations**: Process multiple documents concurrently
- **Connection Pooling**: Reuse HTTP connections
- **Caching**: Cache frequently accessed results
- **Compression**: Enable gzip for large payloads
- **Streaming**: Use streaming for large responses
- **Pagination**: Handle large result sets efficiently

---

## Next Steps

1. **Explore the API**: Visit [http://localhost:8000/docs](http://localhost:8000/docs) for interactive documentation
2. **Check Health**: Monitor system status at [http://localhost:8000/health](http://localhost:8000/health)
3. **View Metrics**: Access Prometheus metrics at [http://localhost:8000/metrics](http://localhost:8000/metrics)
4. **Join Community**: Report issues and request features on [GitHub](https://github.com/cbratkovics/document-intelligence-ai)

For the complete API reference, see the [API Documentation](README.md).