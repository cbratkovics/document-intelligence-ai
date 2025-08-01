from typing import List, Dict, Any, Optional, Tuple
import logging
from datetime import datetime
import asyncio

from langchain.schema import Document
from ..core.vector_store import VectorStore
from ..core.embeddings import EmbeddingService
from ..core.chunking import DocumentChunker
from ..utils.document_loader import DocumentLoader
from ..core.config import settings

logger = logging.getLogger(__name__)


class RAGRetriever:
    """RAG retriever for document search and retrieval"""
    
    def __init__(self):
        self.vector_store = VectorStore()
        self.embedding_service = EmbeddingService()
        self.chunker = DocumentChunker()
        self.document_loader = DocumentLoader()
        self._document_cache = {}
    
    async def add_document(
        self,
        filename: str,
        content: bytes,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Add a document to the RAG system
        
        Args:
            filename: Document filename
            content: Document content as bytes
            metadata: Additional metadata
            
        Returns:
            Document ID
        """
        try:
            # Save uploaded file
            file_path = self.document_loader.save_uploaded_file(filename, content)
            
            # Load document
            document = self.document_loader.load_document(file_path, content)
            
            # Add custom metadata
            if metadata:
                document.metadata.update(metadata)
            
            # Chunk document
            chunks = self.chunker.smart_chunk_document(document)
            
            # Prepare for vector store
            texts = [chunk.page_content for chunk in chunks]
            metadatas = [chunk.metadata for chunk in chunks]
            
            # Generate unique IDs for chunks
            chunk_ids = [
                f"{document.metadata['doc_id']}_{i}"
                for i in range(len(chunks))
            ]
            
            # Add to vector store
            self.vector_store.add_documents(texts, metadatas, chunk_ids)
            
            # Cache document info
            doc_id = document.metadata['doc_id']
            self._document_cache[doc_id] = {
                'filename': filename,
                'chunks': len(chunks),
                'added_at': datetime.utcnow().isoformat()
            }
            
            logger.info(
                f"Added document '{filename}' with {len(chunks)} chunks"
            )
            
            return doc_id
            
        except Exception as e:
            logger.error(f"Error adding document: {e}")
            raise
    
    async def search(
        self,
        query: str,
        top_k: int = None,
        filters: Optional[Dict[str, Any]] = None,
        include_metadata: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant documents
        
        Args:
            query: Search query
            top_k: Number of results to return
            filters: Metadata filters
            include_metadata: Whether to include metadata in results
            
        Returns:
            List of search results
        """
        try:
            top_k = top_k or settings.search_top_k
            
            # Search vector store
            results = self.vector_store.search(
                query=query,
                n_results=top_k,
                filter=filters
            )
            
            # Format results
            formatted_results = []
            for result in results:
                formatted = {
                    'content': result['content'],
                    'relevance_score': result['similarity'],
                    'chunk_id': result['id']
                }
                
                if include_metadata:
                    formatted['metadata'] = result['metadata']
                
                formatted_results.append(formatted)
            
            # Filter by similarity threshold
            formatted_results = [
                r for r in formatted_results
                if r['relevance_score'] >= settings.similarity_threshold
            ]
            
            logger.info(
                f"Search for '{query[:50]}...' returned "
                f"{len(formatted_results)} results"
            )
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error searching documents: {e}")
            raise
    
    async def hybrid_search(
        self,
        query: str,
        top_k: int = None,
        keyword_weight: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid search (vector + keyword)
        
        Args:
            query: Search query
            top_k: Number of results to return
            keyword_weight: Weight for keyword search (0-1)
            
        Returns:
            List of search results
        """
        try:
            top_k = top_k or settings.search_top_k
            
            # Vector search
            vector_results = await self.search(query, top_k * 2)
            
            # Simple keyword search in results
            query_terms = query.lower().split()
            
            # Score results based on keyword matches
            for result in vector_results:
                content_lower = result['content'].lower()
                keyword_score = sum(
                    1 for term in query_terms
                    if term in content_lower
                ) / len(query_terms)
                
                # Combine scores
                result['hybrid_score'] = (
                    (1 - keyword_weight) * result['relevance_score'] +
                    keyword_weight * keyword_score
                )
            
            # Sort by hybrid score
            vector_results.sort(
                key=lambda x: x['hybrid_score'],
                reverse=True
            )
            
            return vector_results[:top_k]
            
        except Exception as e:
            logger.error(f"Error in hybrid search: {e}")
            raise
    
    async def get_context_for_generation(
        self,
        query: str,
        max_context_length: int = 3000
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Get context for answer generation
        
        Args:
            query: User query
            max_context_length: Maximum context length in characters
            
        Returns:
            Tuple of (context_string, source_documents)
        """
        try:
            # Perform hybrid search
            results = await self.hybrid_search(query)
            
            if not results:
                return "", []
            
            # Build context string
            context_parts = []
            total_length = 0
            used_results = []
            
            for result in results:
                chunk_text = result['content']
                chunk_length = len(chunk_text)
                
                if total_length + chunk_length > max_context_length:
                    break
                
                context_parts.append(chunk_text)
                total_length += chunk_length
                used_results.append(result)
            
            context = "\n\n---\n\n".join(context_parts)
            
            return context, used_results
            
        except Exception as e:
            logger.error(f"Error getting context: {e}")
            raise
    
    def delete_document(self, doc_id: str) -> bool:
        """
        Delete a document and all its chunks
        
        Args:
            doc_id: Document ID
            
        Returns:
            Success status
        """
        try:
            # Get all chunk IDs for this document
            chunk_ids = []
            for i in range(100):  # Assume max 100 chunks per document
                chunk_id = f"{doc_id}_{i}"
                if self.vector_store.get_document(chunk_id):
                    chunk_ids.append(chunk_id)
                else:
                    break
            
            if chunk_ids:
                self.vector_store.delete_documents(chunk_ids)
                
                # Remove from cache
                if doc_id in self._document_cache:
                    del self._document_cache[doc_id]
                
                logger.info(f"Deleted document {doc_id} with {len(chunk_ids)} chunks")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error deleting document: {e}")
            return False
    
    def get_document_info(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a document"""
        return self._document_cache.get(doc_id)
    
    def list_documents(self) -> List[Dict[str, Any]]:
        """List all documents in the system"""
        documents = []
        for doc_id, info in self._document_cache.items():
            documents.append({
                'doc_id': doc_id,
                **info
            })
        return documents
    
    def clear_all_documents(self) -> bool:
        """Clear all documents from the system"""
        try:
            self.vector_store.clear_collection()
            self._document_cache.clear()
            logger.info("Cleared all documents")
            return True
        except Exception as e:
            logger.error(f"Error clearing documents: {e}")
            return False