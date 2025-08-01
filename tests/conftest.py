import pytest
import os
from unittest.mock import patch, Mock, AsyncMock
from typing import Generator
import tempfile
import shutil
from pathlib import Path

# Set test environment variables
os.environ['OPENAI_API_KEY'] = 'test-key'
os.environ['APP_ENV'] = 'testing'


@pytest.fixture(autouse=True)
def mock_openai():
    """Mock OpenAI API calls"""
    with patch('langchain_openai.OpenAIEmbeddings') as mock_embeddings:
        with patch('langchain_openai.ChatOpenAI') as mock_chat:
            # Configure mocks
            mock_embeddings.return_value.embed_documents.return_value = [[0.1] * 1536]
            mock_embeddings.return_value.embed_query.return_value = [0.1] * 1536
            
            mock_chat.return_value.ainvoke.return_value.content = "Test response"
            
            yield {
                'embeddings': mock_embeddings,
                'chat': mock_chat
            }


@pytest.fixture
def temp_data_dir() -> Generator[Path, None, None]:
    """Create temporary data directory for tests"""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_documents():
    """Provide sample documents for testing"""
    return {
        "technical": b"Machine learning is a subset of artificial intelligence that enables systems to learn and improve from experience without being explicitly programmed.",
        "legal": b"This agreement is entered into as of the date last signed below between the parties for the purpose of establishing terms and conditions.",
        "medical": b"The patient presented with symptoms consistent with acute respiratory infection, including fever, cough, and shortness of breath."
    }


@pytest.fixture
def test_document_content():
    """Sample document content for testing"""
    return b"""This is a test document for the RAG system.
It contains multiple paragraphs to test chunking.

The document discusses various topics including:
- Document processing
- Embedding generation
- Vector search

This allows us to test the full pipeline."""


@pytest.fixture
def test_pdf_content():
    """Mock PDF content"""
    # This would normally be actual PDF bytes
    # For testing, we'll use a simple text representation
    return b"Mock PDF content"


@pytest.fixture
def mock_vector_store():
    """Mock vector store for testing"""
    with patch('src.core.vector_store.VectorStore') as mock_store:
        store = mock_store.return_value
        store.add_documents = AsyncMock(return_value=True)
        store.search = AsyncMock(return_value=[
            {
                "content": "Test content",
                "relevance_score": 0.9,
                "metadata": {"doc_id": "test_doc"}
            }
        ])
        yield store


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service"""
    with patch('src.core.embeddings.EmbeddingService') as mock_service:
        service = mock_service.return_value
        service.generate_embedding = Mock(return_value=[0.1] * 1536)
        service.embed_documents = Mock(return_value=[[0.1] * 1536] * 10)
        yield service