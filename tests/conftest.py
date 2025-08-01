import pytest
import os
import sys
from unittest.mock import patch, Mock, AsyncMock, MagicMock
from typing import Generator
import tempfile
import shutil
from pathlib import Path

# Set test environment variables BEFORE any imports
os.environ['OPENAI_API_KEY'] = 'test-key'
os.environ['APP_ENV'] = 'testing'

# Create mock OpenAI classes before they're imported
mock_embeddings_instance = MagicMock()
# Make embed_documents return dynamic number of embeddings based on input
mock_embeddings_instance.embed_documents.side_effect = lambda texts: [[0.1] * 1536 for _ in texts]
mock_embeddings_instance.embed_query.return_value = [0.1] * 1536

mock_chat_instance = MagicMock()
mock_chat_instance.ainvoke = AsyncMock()
mock_chat_instance.ainvoke.return_value.content = "Test response"

# Patch at module level before imports
sys.modules['langchain_openai'] = MagicMock()
sys.modules['langchain_openai'].OpenAIEmbeddings = MagicMock(return_value=mock_embeddings_instance)
sys.modules['langchain_openai'].ChatOpenAI = MagicMock(return_value=mock_chat_instance)


@pytest.fixture(autouse=True)
def mock_openai():
    """Ensure OpenAI mocks are properly configured"""
    # The mocks are already set at module level, but we can reconfigure if needed
    mock_embeddings_instance.embed_documents.side_effect = lambda texts: [[0.1] * 1536 for _ in texts]
    mock_embeddings_instance.embed_query.return_value = [0.1] * 1536
    mock_chat_instance.ainvoke.return_value.content = "Test response"
    
    yield {
        'embeddings': sys.modules['langchain_openai'].OpenAIEmbeddings,
        'chat': sys.modules['langchain_openai'].ChatOpenAI,
        'embeddings_instance': mock_embeddings_instance,
        'chat_instance': mock_chat_instance
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
        # Match the actual signature: add_documents(documents: List[str], metadatas: List[Dict[str, Any]], ids: Optional[List[str]] = None)
        store.add_documents = Mock(side_effect=lambda documents, metadatas, ids=None: None)
        store.search = Mock(return_value=[
            {
                "content": "Test content",
                "similarity": 0.9,
                "id": "test_id",
                "metadata": {"doc_id": "test_doc"}
            }
        ])
        yield store


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service"""
    with patch('src.core.embeddings.EmbeddingService') as mock_service:
        service = mock_service.return_value
        service.embed_query = Mock(return_value=[0.1] * 1536)
        service.embed_documents = Mock(return_value=[[0.1] * 1536] * 10)
        yield service