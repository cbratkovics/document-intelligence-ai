from typing import List, Dict, Any, Optional
import numpy as np
from rank_bm25 import BM25Okapi
from ..core.vector_store import VectorStore
from ..core.config import settings
import logging

logger = logging.getLogger(__name__)


class HybridSearch:
    """Implements hybrid search combining vector and keyword search"""
    
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
        self.bm25_index = None
        self.documents = []
        self.tokenized_docs = []
    
    def add_documents(self, documents: List[Dict[str, Any]]):
        """Add documents to both vector and BM25 indices"""
        # Extract data for vector store
        texts = [doc['content'] for doc in documents]
        metadatas = [doc['metadata'] for doc in documents]
        ids = [doc['chunk_id'] for doc in documents]
        
        # Add to vector store
        self.vector_store.add_documents(
            documents=texts,
            metadatas=metadatas,
            ids=ids
        )
        
        # Build BM25 index
        self.documents.extend(documents)
        tokenized_docs = [self._tokenize(doc['content']) for doc in documents]
        self.tokenized_docs.extend(tokenized_docs)
        
        # Rebuild BM25 index with all documents
        if self.tokenized_docs:
            self.bm25_index = BM25Okapi(self.tokenized_docs)
            logger.info(f"BM25 index rebuilt with {len(self.tokenized_docs)} documents")
    
    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization for BM25"""
        # Convert to lowercase and split on whitespace and punctuation
        import re
        tokens = re.findall(r'\b\w+\b', text.lower())
        return tokens
    
    async def search(
        self, 
        query: str, 
        k: int = 10, 
        alpha: float = 0.5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search combining vector and BM25.
        
        Args:
            query: Search query
            k: Number of results to return
            alpha: Weight for vector search (1-alpha for BM25)
            filters: Optional filters for vector search
        
        Returns:
            List of search results with combined scores
        """
        if not self.documents:
            logger.warning("No documents in index")
            return []
        
        # Get more results than needed for better fusion
        search_k = min(k * 3, len(self.documents))
        
        # Vector search
        vector_results = await self.vector_store.search(
            query=query,
            k=search_k,
            filters=filters
        )
        
        # BM25 search
        bm25_results = []
        if self.bm25_index:
            tokenized_query = self._tokenize(query)
            bm25_scores = self.bm25_index.get_scores(tokenized_query)
            
            # Get top-k BM25 results
            top_indices = np.argsort(bm25_scores)[::-1][:search_k]
            
            for idx in top_indices:
                if idx < len(self.documents) and bm25_scores[idx] > 0:
                    doc = self.documents[idx].copy()
                    doc['bm25_score'] = float(bm25_scores[idx])
                    bm25_results.append(doc)
        
        # Combine results using Reciprocal Rank Fusion
        combined_results = self._reciprocal_rank_fusion(
            vector_results, bm25_results, alpha, k
        )
        
        return combined_results
    
    def _reciprocal_rank_fusion(
        self,
        vector_results: List[Dict[str, Any]],
        bm25_results: List[Dict[str, Any]],
        alpha: float,
        k: int
    ) -> List[Dict[str, Any]]:
        """
        Combine results using Reciprocal Rank Fusion (RRF).
        
        RRF score = Σ(1 / (k + rank_i)) where k is a constant (typically 60)
        """
        rrf_k = 60  # Standard RRF constant
        
        # Create score dictionaries
        doc_scores = {}
        
        # Process vector search results
        for rank, result in enumerate(vector_results):
            # Use content as key for matching
            doc_key = result.get('content', '')
            if doc_key:
                score = alpha * (1.0 / (rrf_k + rank + 1))
                if doc_key not in doc_scores:
                    doc_scores[doc_key] = {
                        'doc': result,
                        'score': 0.0,
                        'vector_rank': rank + 1,
                        'vector_score': result.get('relevance_score', 0.0)
                    }
                doc_scores[doc_key]['score'] += score
        
        # Process BM25 results
        for rank, result in enumerate(bm25_results):
            doc_key = result.get('content', '')
            if doc_key:
                score = (1 - alpha) * (1.0 / (rrf_k + rank + 1))
                if doc_key not in doc_scores:
                    doc_scores[doc_key] = {
                        'doc': result,
                        'score': 0.0,
                        'bm25_rank': rank + 1,
                        'bm25_score': result.get('bm25_score', 0.0)
                    }
                else:
                    doc_scores[doc_key]['bm25_rank'] = rank + 1
                    doc_scores[doc_key]['bm25_score'] = result.get('bm25_score', 0.0)
                doc_scores[doc_key]['score'] += score
        
        # Sort by combined score
        sorted_docs = sorted(
            doc_scores.values(),
            key=lambda x: x['score'],
            reverse=True
        )[:k]
        
        # Prepare final results
        results = []
        for item in sorted_docs:
            result = item['doc'].copy()
            result['hybrid_score'] = item['score']
            result['vector_rank'] = item.get('vector_rank', -1)
            result['bm25_rank'] = item.get('bm25_rank', -1)
            if 'vector_score' in item:
                result['vector_score'] = item['vector_score']
            if 'bm25_score' in item:
                result['bm25_score'] = item['bm25_score']
            results.append(result)
        
        return results
    
    def clear(self):
        """Clear all indices"""
        self.bm25_index = None
        self.documents = []
        self.tokenized_docs = []
        logger.info("Hybrid search indices cleared")