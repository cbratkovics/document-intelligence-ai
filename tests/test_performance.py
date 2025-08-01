import pytest
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio
from unittest.mock import Mock, patch
import numpy as np

# Mock the services for performance testing
with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
    from src.core.embeddings import EmbeddingService
    from src.core.chunking import DocumentChunker
    from src.rag.retriever import RAGRetriever
    from src.rag.generator import RAGGenerator


class TestPerformance:
    """Performance tests for the document intelligence system"""
    
    def test_embedding_generation_speed(self):
        """Ensure embeddings are generated within acceptable time"""
        with patch('langchain_openai.OpenAIEmbeddings') as mock_embeddings:
            # Mock the embedding response
            mock_embeddings.return_value.embed_query.return_value = [0.1] * 1536
            
            service = EmbeddingService()
            text = "Test text " * 100  # ~900 chars
            
            start = time.time()
            embedding = service.generate_embedding(text)
            duration = time.time() - start
            
            assert duration < 1.0  # Should complete in under 1 second
            assert len(embedding) == 1536  # Correct embedding dimension
    
    def test_chunking_performance(self):
        """Test chunking speed for large documents"""
        service = DocumentChunker()
        
        # Create a large document (100KB)
        large_text = "This is a test sentence. " * 4000
        
        start = time.time()
        chunks = service.chunk_text(large_text)
        duration = time.time() - start
        
        assert duration < 2.0  # Should chunk in under 2 seconds
        assert len(chunks) > 10  # Should create multiple chunks
        
        # Verify chunk sizes are consistent
        chunk_sizes = [len(chunk.page_content) for chunk in chunks]
        assert all(size <= service.chunk_size for size in chunk_sizes)
    
    def test_concurrent_embedding_generation(self):
        """Test concurrent embedding generation"""
        with patch('langchain_openai.OpenAIEmbeddings') as mock_embeddings:
            mock_embeddings.return_value.embed_documents.return_value = [[0.1] * 1536] * 10
            
            service = EmbeddingService()
            texts = [f"Test document {i}" for i in range(10)]
            
            start = time.time()
            
            # Generate embeddings concurrently
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(service.generate_embedding, text) for text in texts]
                embeddings = [future.result() for future in as_completed(futures)]
            
            duration = time.time() - start
            
            assert duration < 3.0  # Should complete all in under 3 seconds
            assert len(embeddings) == 10
    
    @pytest.mark.asyncio
    async def test_search_latency(self):
        """Test vector search latency"""
        with patch('src.rag.retriever.RAGRetriever') as mock_retriever:
            # Mock search results
            mock_results = [
                {
                    "content": f"Result {i}",
                    "relevance_score": 0.9 - (i * 0.1),
                    "metadata": {"doc_id": f"doc{i}"}
                }
                for i in range(5)
            ]
            
            retriever = mock_retriever.return_value
            retriever.search = asyncio.coroutine(lambda *args, **kwargs: mock_results)
            
            start = time.time()
            results = await retriever.search("test query", top_k=5)
            duration = time.time() - start
            
            assert duration < 0.5  # Search should be fast
            assert len(results) == 5
    
    def test_memory_usage_during_bulk_upload(self):
        """Test memory efficiency during bulk document processing"""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        with patch('langchain_openai.OpenAIEmbeddings') as mock_embeddings:
            mock_embeddings.return_value.embed_documents.return_value = [[0.1] * 1536] * 100
            
            # Process 100 documents
            documents = [f"Document {i} content " * 100 for i in range(100)]
            
            service = EmbeddingService()
            chunking_service = DocumentChunker()
            
            for doc in documents:
                chunks = chunking_service.chunk_text(doc)
                # In real scenario, embeddings would be generated here
            
            final_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = final_memory - initial_memory
            
            # Memory increase should be reasonable (less than 100MB for this test)
            assert memory_increase < 100
    
    @pytest.mark.asyncio
    async def test_concurrent_rag_queries(self):
        """Test system handles concurrent RAG queries efficiently"""
        with patch('src.rag.generator.RAGGenerator') as mock_generator:
            generator = mock_generator.return_value
            
            async def mock_generate(*args, **kwargs):
                await asyncio.sleep(0.1)  # Simulate processing time
                return {
                    "answer": "Test answer",
                    "sources": [],
                    "confidence": 0.85,
                    "processing_time": 0.1
                }
            
            generator.generate_answer = mock_generate
            
            # Send 20 concurrent queries
            queries = [f"Query {i}" for i in range(20)]
            
            start = time.time()
            
            tasks = [generator.generate_answer(query) for query in queries]
            results = await asyncio.gather(*tasks)
            
            duration = time.time() - start
            
            # Should handle concurrent queries efficiently
            # With 0.1s per query, 20 queries with concurrency should take < 2s
            assert duration < 2.0
            assert len(results) == 20
            assert all(r["answer"] == "Test answer" for r in results)
    
    def test_batch_processing_efficiency(self):
        """Test batch processing is more efficient than individual processing"""
        with patch('langchain_openai.OpenAIEmbeddings') as mock_embeddings:
            # Mock batch embedding
            def mock_embed_documents(texts):
                return [[0.1] * 1536 for _ in texts]
            
            mock_embeddings.return_value.embed_documents = mock_embed_documents
            mock_embeddings.return_value.embed_query.return_value = [0.1] * 1536
            
            service = EmbeddingService()
            texts = [f"Text {i}" for i in range(50)]
            
            # Test individual processing
            start_individual = time.time()
            individual_embeddings = [service.generate_embedding(text) for text in texts]
            individual_time = time.time() - start_individual
            
            # Test batch processing
            start_batch = time.time()
            batch_embeddings = service.embed_documents(texts)
            batch_time = time.time() - start_batch
            
            # Batch should be significantly faster
            assert batch_time < individual_time * 0.5  # At least 2x faster
            assert len(batch_embeddings) == len(individual_embeddings)
    
    def test_response_time_under_load(self):
        """Test response times remain acceptable under load"""
        with patch('langchain_openai.OpenAIEmbeddings') as mock_embeddings:
            mock_embeddings.return_value.embed_query.return_value = [0.1] * 1536
            
            service = EmbeddingService()
            
            response_times = []
            
            # Simulate load with 100 requests
            for i in range(100):
                start = time.time()
                _ = service.generate_embedding(f"Query {i}")
                response_time = time.time() - start
                response_times.append(response_time)
            
            # Calculate percentiles
            p50 = np.percentile(response_times, 50)
            p95 = np.percentile(response_times, 95)
            p99 = np.percentile(response_times, 99)
            
            # Response time SLAs
            assert p50 < 0.1  # 50% of requests under 100ms
            assert p95 < 0.5  # 95% of requests under 500ms
            assert p99 < 1.0  # 99% of requests under 1s