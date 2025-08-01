import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils import embedding_functions
from typing import List, Dict, Any, Optional, Tuple
import logging
from datetime import datetime
import uuid

from .config import settings
from .embeddings import EmbeddingService

logger = logging.getLogger(__name__)


class VectorStore:
    """ChromaDB vector store for document storage and retrieval"""
    
    def __init__(self, collection_name: str = None):
        self.collection_name = collection_name or settings.chroma_collection_name
        self.embedding_service = EmbeddingService()
        self.client = self._initialize_client()
        self.collection = self._get_or_create_collection()
    
    def _initialize_client(self) -> chromadb.Client:
        """Initialize ChromaDB client"""
        try:
            # For development, use in-memory client
            if settings.is_development and settings.chroma_host == "localhost":
                logger.info("Using in-memory ChromaDB for development")
                client = chromadb.Client()
            else:
                # For production, connect to ChromaDB server
                client = chromadb.HttpClient(
                    host=settings.chroma_host,
                    port=settings.chroma_port,
                    settings=ChromaSettings(anonymized_telemetry=False)
                )
            
            logger.info(f"Connected to ChromaDB")
            return client
            
        except Exception as e:
            logger.error(f"Failed to connect to ChromaDB: {e}")
            # Fallback to in-memory client
            logger.warning("Falling back to in-memory ChromaDB")
            return chromadb.Client()
    
    def _get_or_create_collection(self):
        """Get or create a collection"""
        try:
            # Custom embedding function that uses our EmbeddingService
            class CustomEmbeddingFunction(embedding_functions.EmbeddingFunction):
                def __init__(self, embedding_service):
                    self.embedding_service = embedding_service
                
                def __call__(self, input: List[str]) -> List[List[float]]:
                    return self.embedding_service.embed_documents(input)
            
            embedding_function = CustomEmbeddingFunction(self.embedding_service)
            
            # Try to get existing collection
            try:
                collection = self.client.get_collection(
                    name=self.collection_name,
                    embedding_function=embedding_function
                )
                logger.info(f"Using existing collection: {self.collection_name}")
            except:
                # Create new collection
                collection = self.client.create_collection(
                    name=self.collection_name,
                    embedding_function=embedding_function,
                    metadata={"created_at": datetime.utcnow().isoformat()}
                )
                logger.info(f"Created new collection: {self.collection_name}")
            
            return collection
            
        except Exception as e:
            logger.error(f"Error with collection: {e}")
            raise
    
    def add_documents(
        self,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        ids: Optional[List[str]] = None
    ) -> List[str]:
        """
        Add documents to the vector store
        
        Args:
            documents: List of document texts
            metadatas: List of metadata dictionaries
            ids: Optional list of document IDs
            
        Returns:
            List of document IDs
        """
        if not documents:
            return []
        
        try:
            # Generate IDs if not provided
            if ids is None:
                ids = [str(uuid.uuid4()) for _ in documents]
            
            # Add to collection
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            
            logger.info(f"Added {len(documents)} documents to vector store")
            return ids
            
        except Exception as e:
            logger.error(f"Error adding documents: {e}")
            raise
    
    def search(
        self,
        query: str,
        n_results: int = None,
        filter: Dict[str, Any] = None,
        include: List[str] = None
    ) -> Dict[str, Any]:
        """
        Search for similar documents
        
        Args:
            query: Search query
            n_results: Number of results to return
            filter: Metadata filter
            include: Fields to include in results
            
        Returns:
            Search results dictionary
        """
        n_results = n_results or settings.search_top_k
        include = include or ["documents", "metadatas", "distances"]
        
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where=filter,
                include=include
            )
            
            # Format results
            formatted_results = self._format_search_results(results)
            
            logger.info(
                f"Search for '{query[:50]}...' returned "
                f"{len(formatted_results)} results"
            )
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error searching documents: {e}")
            raise
    
    def search_by_embedding(
        self,
        embedding: List[float],
        n_results: int = None,
        filter: Dict[str, Any] = None,
        include: List[str] = None
    ) -> Dict[str, Any]:
        """
        Search using an embedding vector
        
        Args:
            embedding: Query embedding
            n_results: Number of results to return
            filter: Metadata filter
            include: Fields to include in results
            
        Returns:
            Search results dictionary
        """
        n_results = n_results or settings.search_top_k
        include = include or ["documents", "metadatas", "distances"]
        
        try:
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=n_results,
                where=filter,
                include=include
            )
            
            return self._format_search_results(results)
            
        except Exception as e:
            logger.error(f"Error searching by embedding: {e}")
            raise
    
    def delete_documents(self, ids: List[str]) -> bool:
        """
        Delete documents by IDs
        
        Args:
            ids: List of document IDs to delete
            
        Returns:
            Success status
        """
        try:
            self.collection.delete(ids=ids)
            logger.info(f"Deleted {len(ids)} documents")
            return True
        except Exception as e:
            logger.error(f"Error deleting documents: {e}")
            return False
    
    def update_document(
        self,
        id: str,
        document: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update a document
        
        Args:
            id: Document ID
            document: New document text
            metadata: New metadata
            
        Returns:
            Success status
        """
        try:
            update_kwargs = {"ids": [id]}
            
            if document is not None:
                update_kwargs["documents"] = [document]
            
            if metadata is not None:
                update_kwargs["metadatas"] = [metadata]
            
            self.collection.update(**update_kwargs)
            logger.info(f"Updated document: {id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating document: {e}")
            return False
    
    def get_document(self, id: str) -> Optional[Dict[str, Any]]:
        """Get a specific document by ID"""
        try:
            result = self.collection.get(
                ids=[id],
                include=["documents", "metadatas"]
            )
            
            if result["documents"]:
                return {
                    "id": id,
                    "document": result["documents"][0],
                    "metadata": result["metadatas"][0]
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting document: {e}")
            return None
    
    def count_documents(self) -> int:
        """Get total number of documents in collection"""
        try:
            return self.collection.count()
        except Exception as e:
            logger.error(f"Error counting documents: {e}")
            return 0
    
    def clear_collection(self) -> bool:
        """Clear all documents from collection"""
        try:
            # Delete and recreate collection
            self.client.delete_collection(self.collection_name)
            self.collection = self._get_or_create_collection()
            logger.info(f"Cleared collection: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"Error clearing collection: {e}")
            return False
    
    def _format_search_results(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Format ChromaDB search results"""
        formatted = []
        
        # ChromaDB returns results in a nested structure
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        ids = results.get("ids", [[]])[0]
        
        for i in range(len(documents)):
            # Convert distance to similarity score (1 - normalized_distance)
            # ChromaDB uses L2 distance by default
            similarity = 1.0 - (distances[i] / 2.0)  # Normalize to 0-1
            
            formatted.append({
                "id": ids[i],
                "content": documents[i],
                "metadata": metadatas[i],
                "similarity": max(0.0, min(1.0, similarity))
            })
        
        return formatted