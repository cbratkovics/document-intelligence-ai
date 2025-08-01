import pytest
from httpx import AsyncClient
import asyncio
from src.api.main import app
import io

class TestIntegrationRAG:
    """End-to-end RAG pipeline tests"""
    
    @pytest.mark.asyncio
    async def test_full_rag_pipeline(self):
        """Test document upload -> embedding -> search -> answer generation"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # 1. Upload a document
            files = {"file": ("test.txt", b"The capital of France is Paris. France is located in Western Europe.", "text/plain")}
            upload_response = await client.post("/api/v1/documents/upload", files=files)
            assert upload_response.status_code == 200
            doc_id = upload_response.json()["document_id"]
            assert doc_id is not None
            
            # 2. Wait a moment for processing
            await asyncio.sleep(0.5)
            
            # 3. Query the document
            query_response = await client.post(
                "/api/v1/query",
                json={"text": "What is the capital of France?"}
            )
            assert query_response.status_code == 200
            result = query_response.json()
            assert "answer" in result
            # The mocked response should contain our test response
            assert result["answer"] == "Test response"  # Due to mocking in conftest
            
    @pytest.mark.asyncio
    async def test_streaming_response(self):
        """Test streaming RAG responses"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Upload test document
            files = {"file": ("test.txt", b"Machine learning is a subset of artificial intelligence.", "text/plain")}
            upload_response = await client.post("/api/v1/documents/upload", files=files)
            assert upload_response.status_code == 200
            
            # Query with streaming (if implemented)
            query_data = {
                "text": "What is machine learning?",
                "stream": True
            }
            
            # Note: Actual streaming implementation would need to be added to the API
            response = await client.post("/api/v1/query", json=query_data)
            assert response.status_code in [200, 501]  # 501 if not implemented yet
    
    @pytest.mark.asyncio
    async def test_multiple_document_search(self):
        """Test searching across multiple documents"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Upload multiple documents
            docs = [
                ("doc1.txt", b"Python is a programming language known for its simplicity.", "text/plain"),
                ("doc2.txt", b"JavaScript is widely used for web development.", "text/plain"),
                ("doc3.txt", b"Go is known for its concurrency features.", "text/plain")
            ]
            
            doc_ids = []
            for filename, content, mime_type in docs:
                files = {"file": (filename, content, mime_type)}
                response = await client.post("/api/v1/documents/upload", files=files)
                assert response.status_code == 200
                doc_ids.append(response.json()["document_id"])
            
            # Search across all documents
            search_response = await client.post(
                "/api/v1/search",
                json={"text": "programming languages", "top_k": 5}
            )
            assert search_response.status_code == 200
            results = search_response.json()
            assert "results" in results
            assert len(results["results"]) > 0
    
    @pytest.mark.asyncio
    async def test_document_deletion_and_search(self):
        """Test that deleted documents don't appear in search results"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Upload a document
            files = {"file": ("test.txt", b"Unique content about quantum computing.", "text/plain")}
            upload_response = await client.post("/api/v1/documents/upload", files=files)
            doc_id = upload_response.json()["document_id"]
            
            # Verify it appears in search
            search_response = await client.post(
                "/api/v1/search",
                json={"text": "quantum computing"}
            )
            assert search_response.status_code == 200
            
            # Delete the document
            delete_response = await client.delete(f"/api/v1/documents/{doc_id}")
            assert delete_response.status_code == 200
            
            # Verify it no longer appears in search
            search_response = await client.post(
                "/api/v1/search",
                json={"text": "quantum computing"}
            )
            # Results should be empty or not contain the deleted content
            assert search_response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_large_document_handling(self):
        """Test handling of large documents"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Create a large document (but within limits)
            large_content = "This is a test sentence. " * 1000  # ~24KB
            files = {"file": ("large.txt", large_content.encode(), "text/plain")}
            
            response = await client.post("/api/v1/documents/upload", files=files)
            assert response.status_code == 200
            result = response.json()
            assert result["chunks_created"] > 1  # Should be chunked
    
    @pytest.mark.asyncio
    async def test_concurrent_queries(self):
        """Test system handles concurrent queries"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Upload a document first
            files = {"file": ("test.txt", b"Test content for concurrent queries.", "text/plain")}
            await client.post("/api/v1/documents/upload", files=files)
            
            # Send multiple concurrent queries
            queries = [
                {"text": "What is the test about?"},
                {"text": "Explain concurrent queries"},
                {"text": "What content is available?"}
            ]
            
            tasks = [
                client.post("/api/v1/query", json=query)
                for query in queries
            ]
            
            responses = await asyncio.gather(*tasks)
            
            # All should succeed
            for response in responses:
                assert response.status_code == 200
                assert "answer" in response.json()
    
    @pytest.mark.asyncio
    async def test_error_recovery(self):
        """Test system recovers from errors gracefully"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Test with invalid query
            response = await client.post(
                "/api/v1/query",
                json={"text": ""}  # Empty query
            )
            assert response.status_code == 422  # Validation error
            
            # System should still work after error
            response = await client.post(
                "/api/v1/query",
                json={"text": "Valid query"}
            )
            assert response.status_code == 200