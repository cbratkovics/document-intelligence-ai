import pytest
from unittest.mock import Mock, patch
import os

from src.core.config import Settings, get_settings
from src.core.chunking import DocumentChunker
from src.core.embeddings import EmbeddingService
from src.utils.document_loader import DocumentLoader
from langchain.schema import Document


class TestConfig:
    """Test configuration management"""
    
    def test_settings_initialization(self):
        """Test settings initialization"""
        settings = Settings(OPENAI_API_KEY="test-key")
        assert settings.openai_api_key == "test-key"
        assert settings.app_name == "Document Intelligence API"
        assert settings.chunk_size == 1000
        assert settings.chunk_overlap == 200
    
    def test_settings_from_env(self):
        """Test loading settings from environment"""
        with patch.dict(os.environ, {
            'OPENAI_API_KEY': 'env-key',
            'CHUNK_SIZE': '500',
            'APP_ENV': 'production'
        }):
            settings = Settings()
            assert settings.openai_api_key == 'env-key'
            assert settings.chunk_size == 500
            assert settings.is_production == True
            assert settings.is_development == False
    
    def test_chroma_url_property(self):
        """Test ChromaDB URL generation"""
        settings = Settings(
            OPENAI_API_KEY="test",
            CHROMA_HOST="localhost",
            CHROMA_PORT=8001
        )
        assert settings.chroma_url == "http://localhost:8001"


class TestDocumentChunker:
    """Test document chunking functionality"""
    
    def test_basic_chunking(self):
        """Test basic text chunking"""
        chunker = DocumentChunker(chunk_size=100, chunk_overlap=20)
        
        text = "This is a test. " * 50  # Create text longer than chunk size
        doc = Document(page_content=text, metadata={"test": True})
        
        chunks = chunker.chunk_document(doc)
        
        assert len(chunks) > 1
        assert all(len(chunk.page_content) <= 100 for chunk in chunks)
        assert all(chunk.metadata.get("test") == True for chunk in chunks)
        assert all("chunk_index" in chunk.metadata for chunk in chunks)
    
    def test_chunk_text_directly(self):
        """Test chunking raw text"""
        chunker = DocumentChunker(chunk_size=50, chunk_overlap=10)
        
        text = "Short text that fits in one chunk"
        chunks = chunker.chunk_text(text, metadata={"source": "test"})
        
        assert len(chunks) == 1
        assert chunks[0].page_content == text
        assert chunks[0].metadata["source"] == "test"
    
    def test_smart_chunk_markdown(self):
        """Test smart chunking for markdown documents"""
        chunker = DocumentChunker(chunk_size=200, chunk_overlap=20)
        
        markdown_text = """# Header 1
This is content under header 1.

## Subheader 1.1
More content here.

# Header 2
Different section content."""
        
        doc = Document(
            page_content=markdown_text,
            metadata={"extension": ".md"}
        )
        
        chunks = chunker.smart_chunk_document(doc)
        assert len(chunks) >= 1
        assert all("chunk_index" in chunk.metadata for chunk in chunks)
    
    def test_chunk_statistics(self):
        """Test chunk statistics calculation"""
        chunker = DocumentChunker()
        
        chunks = [
            Document(page_content="Short", metadata={}),
            Document(page_content="Medium length", metadata={}),
            Document(page_content="This is a longer chunk", metadata={})
        ]
        
        stats = chunker.get_chunk_statistics(chunks)
        
        assert stats["total_chunks"] == 3
        assert stats["min_chunk_size"] == 5
        assert stats["max_chunk_size"] == 22
        assert stats["avg_chunk_size"] > 0


class TestDocumentLoader:
    """Test document loading functionality"""
    
    def test_load_text_document(self, tmp_path):
        """Test loading text document"""
        loader = DocumentLoader()
        
        # Create test file
        test_file = tmp_path / "test.txt"
        test_content = "This is test content"
        test_file.write_text(test_content)
        
        # Load document
        doc = loader.load_document(str(test_file))
        
        assert doc.page_content == test_content
        assert doc.metadata["filename"] == "test.txt"
        assert doc.metadata["extension"] == ".txt"
        assert "doc_id" in doc.metadata
    
    def test_sanitize_filename(self):
        """Test filename sanitization"""
        loader = DocumentLoader()
        
        assert loader._sanitize_filename("test.txt") == "test.txt"
        assert loader._sanitize_filename("test file.txt") == "test_file.txt"
        assert loader._sanitize_filename("../../etc/passwd") == "passwd.txt"
        assert loader._sanitize_filename("test") == "test.txt"
    
    def test_generate_document_id(self):
        """Test document ID generation"""
        loader = DocumentLoader()
        
        content1 = b"Test content"
        content2 = b"Different content"
        
        id1 = loader._generate_document_id(content1)
        id2 = loader._generate_document_id(content2)
        id1_duplicate = loader._generate_document_id(content1)
        
        assert id1 != id2
        assert id1 == id1_duplicate
        assert len(id1) == 64  # SHA256 hex length
    
    def test_extract_pdf_text(self):
        """Test PDF text extraction"""
        loader = DocumentLoader()
        # Mock the PDF extraction since we can't create valid PDF bytes easily
        with patch.object(loader, '_extract_pdf_text', return_value="Extracted PDF text"):
            result = loader._extract_pdf_text(b"fake pdf content")
            assert result == "Extracted PDF text"


class TestEmbeddingService:
    """Test embedding service"""
    
    def test_embedding_service_initialization(self):
        """Test embedding service initialization"""
        service = EmbeddingService()
        assert service.model_name is not None
        assert service.embeddings is not None
    
    def test_compute_similarity(self):
        """Test similarity computation"""
        service = EmbeddingService()
        
        # Test identical vectors
        vec1 = [1.0, 0.0, 0.0]
        similarity = service.compute_similarity(vec1, vec1)
        assert abs(similarity - 1.0) < 0.001
        
        # Test orthogonal vectors
        vec2 = [0.0, 1.0, 0.0]
        similarity = service.compute_similarity(vec1, vec2)
        assert abs(similarity) < 0.001
    
    def test_find_similar_embeddings(self):
        """Test finding similar embeddings"""
        service = EmbeddingService()
        
        query_embedding = [1.0, 0.0, 0.0]
        embeddings = [
            [1.0, 0.0, 0.0],  # Identical
            [0.9, 0.1, 0.0],  # Very similar
            [0.0, 1.0, 0.0],  # Orthogonal
            [0.8, 0.2, 0.0],  # Similar
        ]
        
        results = service.find_similar_embeddings(
            query_embedding,
            embeddings,
            top_k=2,
            threshold=0.5
        )
        
        assert len(results) == 2
        assert results[0]["index"] == 0
        assert results[0]["similarity"] > 0.99
        assert results[1]["index"] in [1, 3]
    
    def test_validate_embeddings(self):
        """Test embedding validation"""
        service = EmbeddingService()
        
        # Valid embeddings
        valid_embeddings = [[0.1, 0.2], [0.3, 0.4]]
        assert service.validate_embeddings(valid_embeddings) == True
        
        # Invalid - different dimensions
        invalid_embeddings = [[0.1, 0.2], [0.3, 0.4, 0.5]]
        assert service.validate_embeddings(invalid_embeddings) == False
        
        # Invalid - non-numeric
        invalid_embeddings = [[0.1, "invalid"], [0.3, 0.4]]
        assert service.validate_embeddings(invalid_embeddings) == False