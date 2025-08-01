import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, AsyncMock
import json
import io

# Import after patching environment variables
with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
    from src.api.main import app
    from src.core.config import settings


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


@pytest.fixture
def mock_retriever():
    """Mock RAG retriever"""
    with patch('src.api.endpoints.retriever') as mock:
        yield mock


@pytest.fixture
def mock_generator():
    """Mock RAG generator"""
    with patch('src.api.endpoints.generator') as mock:
        yield mock


class TestHealthEndpoints:
    """Test health and status endpoints"""
    
    def test_root_endpoint(self, client):
        """Test root endpoint"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == settings.app_name
        assert data["version"] == settings.app_version
        assert "docs" in data
    
    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "services" in data


class TestDocumentEndpoints:
    """Test document management endpoints"""
    
    @pytest.mark.asyncio
    async def test_upload_document_success(self, client, mock_retriever):
        """Test successful document upload"""
        # Mock the retriever
        mock_retriever.add_document = AsyncMock(return_value="doc123")
        
        # Create test file
        file_content = b"This is a test document"
        files = {"file": ("test.txt", file_content, "text/plain")}
        
        response = client.post("/api/v1/documents/upload", files=files)
        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == "doc123"
        assert data["status"] == "processed"
    
    def test_upload_document_invalid_type(self, client):
        """Test document upload with invalid file type"""
        file_content = b"This is a test"
        files = {"file": ("test.exe", file_content, "application/x-msdownload")}
        
        response = client.post("/api/v1/documents/upload", files=files)
        assert response.status_code == 400
        assert "Unsupported file type" in response.json()["detail"]
    
    def test_upload_document_too_large(self, client):
        """Test document upload with file too large"""
        # Create large file content
        file_content = b"x" * (settings.max_upload_size + 1)
        files = {"file": ("large.txt", file_content, "text/plain")}
        
        response = client.post("/api/v1/documents/upload", files=files)
        assert response.status_code == 413
        assert "File too large" in response.json()["detail"]
    
    def test_list_documents(self, client, mock_retriever):
        """Test listing documents"""
        mock_retriever.list_documents.return_value = [
            {
                "doc_id": "doc1",
                "filename": "test1.txt",
                "chunks": 5,
                "added_at": "2024-01-01T00:00:00"
            }
        ]
        
        response = client.get("/api/v1/documents")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["doc_id"] == "doc1"
    
    def test_get_document(self, client, mock_retriever):
        """Test getting specific document"""
        mock_retriever.get_document_info.return_value = {
            "filename": "test.txt",
            "chunks": 5,
            "added_at": "2024-01-01T00:00:00"
        }
        
        response = client.get("/api/v1/documents/doc123")
        assert response.status_code == 200
        data = response.json()
        assert data["doc_id"] == "doc123"
        assert data["filename"] == "test.txt"
    
    def test_get_document_not_found(self, client, mock_retriever):
        """Test getting non-existent document"""
        mock_retriever.get_document_info.return_value = None
        
        response = client.get("/api/v1/documents/nonexistent")
        assert response.status_code == 404
    
    def test_delete_document(self, client, mock_retriever):
        """Test deleting document"""
        mock_retriever.delete_document.return_value = True
        
        response = client.delete("/api/v1/documents/doc123")
        assert response.status_code == 200
        assert "deleted successfully" in response.json()["message"]


class TestQueryEndpoints:
    """Test query and search endpoints"""
    
    @pytest.mark.asyncio
    async def test_query_documents(self, client, mock_generator):
        """Test querying documents"""
        mock_generator.generate_answer = AsyncMock(return_value={
            "answer": "Test answer",
            "sources": [{"chunk_id": "chunk1", "relevance_score": 0.9}],
            "confidence": 0.85,
            "processing_time": 1.5
        })
        
        query_data = {"text": "What is the test about?"}
        response = client.post("/api/v1/query", json=query_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["answer"] == "Test answer"
        assert len(data["sources"]) == 1
        assert data["confidence"] == 0.85
    
    @pytest.mark.asyncio
    async def test_search_documents(self, client, mock_retriever):
        """Test searching documents"""
        mock_retriever.search = AsyncMock(return_value=[
            {
                "content": "Test content",
                "relevance_score": 0.9,
                "chunk_id": "chunk1",
                "metadata": {"filename": "test.txt"}
            }
        ])
        
        search_data = {"text": "test query", "top_k": 5}
        response = client.post("/api/v1/search", json=search_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["results"][0]["content"] == "Test content"


class TestSummaryEndpoints:
    """Test summary generation endpoints"""
    
    @pytest.mark.asyncio
    async def test_generate_summary(self, client, mock_generator):
        """Test document summary generation"""
        mock_generator.generate_summary = AsyncMock(
            return_value="This is a test summary"
        )
        
        response = client.post("/api/v1/documents/doc123/summary?max_length=100")
        assert response.status_code == 200
        data = response.json()
        assert data["summary"] == "This is a test summary"
        assert data["doc_id"] == "doc123"


class TestEvaluationEndpoints:
    """Test answer evaluation endpoints"""
    
    @pytest.mark.asyncio
    async def test_evaluate_answer(self, client, mock_generator):
        """Test answer evaluation"""
        mock_generator.evaluate_answer_quality = AsyncMock(return_value={
            "relevance": 4,
            "accuracy": 5,
            "completeness": 3,
            "clarity": 4,
            "overall": 4.0
        })
        
        eval_data = {
            "question": "What is X?",
            "answer": "X is Y",
            "context": "Context about X"
        }
        
        response = client.post("/api/v1/evaluate", json=eval_data)
        assert response.status_code == 200
        data = response.json()
        assert data["overall"] == 4.0
        assert "relevance" in data


class TestErrorHandling:
    """Test error handling"""
    
    def test_invalid_json(self, client):
        """Test invalid JSON in request"""
        response = client.post(
            "/api/v1/query",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422
    
    def test_missing_required_field(self, client):
        """Test missing required field"""
        response = client.post("/api/v1/query", json={})
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_internal_server_error(self, client, mock_generator):
        """Test internal server error handling"""
        mock_generator.generate_answer = AsyncMock(
            side_effect=Exception("Internal error")
        )
        
        query_data = {"text": "Test query"}
        response = client.post("/api/v1/query", json=query_data)
        
        assert response.status_code == 500
        assert "Internal error" in response.json()["detail"]


# Integration tests would go here, but require actual services
class TestIntegration:
    """Integration tests (skipped in unit tests)"""
    
    @pytest.mark.skip(reason="Requires actual services")
    def test_end_to_end_flow(self, client):
        """Test complete document upload and query flow"""
        pass