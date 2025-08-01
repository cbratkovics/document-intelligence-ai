from typing import List, Dict, Any, Optional
import numpy as np
from langchain_openai import OpenAIEmbeddings
from langchain.embeddings.base import Embeddings
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time

from .config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating document embeddings"""
    
    def __init__(self, model_name: str = None):
        self.model_name = model_name or settings.embedding_model
        self.embeddings = self._initialize_embeddings()
        self._executor = ThreadPoolExecutor(max_workers=5)
        
    def _initialize_embeddings(self) -> Embeddings:
        """Initialize the embedding model"""
        try:
            embeddings = OpenAIEmbeddings(
                model=self.model_name,
                openai_api_key=settings.openai_api_key
            )
            logger.info(f"Initialized embedding model: {self.model_name}")
            return embeddings
        except Exception as e:
            logger.error(f"Failed to initialize embeddings: {e}")
            raise
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple documents
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        try:
            start_time = time.time()
            
            # Batch texts if too many
            batch_size = 100
            all_embeddings = []
            
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                batch_embeddings = self.embeddings.embed_documents(batch)
                all_embeddings.extend(batch_embeddings)
                
                # Log progress for large batches
                if len(texts) > batch_size:
                    progress = min(i + batch_size, len(texts))
                    logger.info(f"Embedded {progress}/{len(texts)} documents")
            
            elapsed = time.time() - start_time
            logger.info(f"Generated {len(all_embeddings)} embeddings in {elapsed:.2f}s")
            
            return all_embeddings
            
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            raise
    
    def embed_query(self, text: str) -> List[float]:
        """
        Generate embedding for a single query
        
        Args:
            text: Query text to embed
            
        Returns:
            Embedding vector
        """
        try:
            embedding = self.embeddings.embed_query(text)
            return embedding
        except Exception as e:
            logger.error(f"Error generating query embedding: {e}")
            raise
    
    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Asynchronously generate embeddings for multiple documents
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self.embed_documents,
            texts
        )
    
    async def aembed_query(self, text: str) -> List[float]:
        """
        Asynchronously generate embedding for a query
        
        Args:
            text: Query text to embed
            
        Returns:
            Embedding vector
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self.embed_query,
            text
        )
    
    def compute_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """
        Compute cosine similarity between two embeddings
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Cosine similarity score (0-1)
        """
        # Convert to numpy arrays
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)
        
        # Compute cosine similarity
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        similarity = dot_product / (norm1 * norm2)
        
        # Ensure result is between 0 and 1
        return float(max(0.0, min(1.0, similarity)))
    
    def find_similar_embeddings(
        self,
        query_embedding: List[float],
        embeddings: List[List[float]],
        top_k: int = 5,
        threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Find most similar embeddings to a query
        
        Args:
            query_embedding: Query embedding vector
            embeddings: List of embeddings to search
            top_k: Number of top results to return
            threshold: Minimum similarity threshold
            
        Returns:
            List of dictionaries with index and similarity score
        """
        similarities = []
        
        for i, embedding in enumerate(embeddings):
            similarity = self.compute_similarity(query_embedding, embedding)
            if similarity >= threshold:
                similarities.append({
                    'index': i,
                    'similarity': similarity
                })
        
        # Sort by similarity (descending)
        similarities.sort(key=lambda x: x['similarity'], reverse=True)
        
        # Return top k results
        return similarities[:top_k]
    
    def get_embedding_dimension(self) -> int:
        """Get the dimension of the embedding model"""
        # Generate a test embedding to get dimension
        test_embedding = self.embed_query("test")
        return len(test_embedding)
    
    def validate_embeddings(self, embeddings: List[List[float]]) -> bool:
        """Validate that embeddings are properly formatted"""
        if not embeddings:
            return True
        
        expected_dim = len(embeddings[0])
        
        for i, embedding in enumerate(embeddings):
            if not isinstance(embedding, list):
                logger.error(f"Embedding {i} is not a list")
                return False
            
            if len(embedding) != expected_dim:
                logger.error(
                    f"Embedding {i} has dimension {len(embedding)}, "
                    f"expected {expected_dim}"
                )
                return False
            
            if not all(isinstance(x, (int, float)) for x in embedding):
                logger.error(f"Embedding {i} contains non-numeric values")
                return False
        
        return True