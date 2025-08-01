import pytest
import os
from unittest.mock import patch

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