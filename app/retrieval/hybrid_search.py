from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import numpy as np
from rank_bm25 import BM25Okapi
import chromadb
from chromadb.config import Settings
import logging
from collections import defaultdict
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    doc_id: str
    content: str
    score: float
    metadata: Dict[str, Any]
    source: str  # 'vector', 'bm25', or 'hybrid'


@dataclass
class HybridSearchConfig:
    vector_weight: float = 0.6
    bm25_weight: float = 0.4
    top_k: int = 10
    rerank_top_k: int = 20
    min_score_threshold: float = 0.0
    normalize_scores: bool = True
    use_reciprocal_rank_fusion: bool = False
    rrf_k: int = 60


class BM25Index:
    def __init__(self):
        self.documents: List[str] = []
        self.doc_ids: List[str] = []
        self.metadata: Dict[str, Dict[str, Any]] = {}
        self.bm25: Optional[BM25Okapi] = None
        self.tokenized_docs: List[List[str]] = []
    
    def add_documents(self, documents: List[str], doc_ids: List[str], metadata: List[Dict[str, Any]] = None):
        self.documents.extend(documents)
        self.doc_ids.extend(doc_ids)
        
        if metadata:
            for doc_id, meta in zip(doc_ids, metadata):
                self.metadata[doc_id] = meta
        
        self._rebuild_index()
    
    def _tokenize(self, text: str) -> List[str]:
        return text.lower().split()
    
    def _rebuild_index(self):
        self.tokenized_docs = [self._tokenize(doc) for doc in self.documents]
        self.bm25 = BM25Okapi(self.tokenized_docs)
        logger.info(f"BM25 index rebuilt with {len(self.documents)} documents")
    
    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float, str, Dict[str, Any]]]:
        if not self.bm25:
            return []
        
        tokenized_query = self._tokenize(query)
        scores = self.bm25.get_scores(tokenized_query)
        
        top_indices = np.argsort(scores)[-top_k:][::-1]
        
        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                doc_id = self.doc_ids[idx]
                results.append((
                    doc_id,
                    float(scores[idx]),
                    self.documents[idx],
                    self.metadata.get(doc_id, {})
                ))
        
        return results


class HybridSearchEngine:
    def __init__(
        self,
        chroma_client: chromadb.Client = None,
        collection_name: str = "documents",
        config: HybridSearchConfig = None
    ):
        self.config = config or HybridSearchConfig()
        
        if chroma_client is None:
            chroma_client = chromadb.Client(Settings(
                persist_directory="./chroma_db",
                anonymized_telemetry=False
            ))
        
        self.chroma_client = chroma_client
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name
        )
        
        self.bm25_index = BM25Index()
        self.executor = ThreadPoolExecutor(max_workers=2)
    
    def add_documents(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        doc_ids: List[str],
        metadata: List[Dict[str, Any]] = None
    ):
        metadata = metadata or [{} for _ in doc_ids]
        
        self.collection.add(
            embeddings=embeddings,
            documents=documents,
            ids=doc_ids,
            metadatas=metadata
        )
        
        self.bm25_index.add_documents(documents, doc_ids, metadata)
        
        logger.info(f"Added {len(documents)} documents to hybrid search index")
    
    def _normalize_scores(self, scores: List[float]) -> List[float]:
        if not scores:
            return []
        
        min_score = min(scores)
        max_score = max(scores)
        
        if max_score == min_score:
            return [1.0] * len(scores)
        
        return [(s - min_score) / (max_score - min_score) for s in scores]
    
    def _reciprocal_rank_fusion(
        self,
        vector_results: List[SearchResult],
        bm25_results: List[SearchResult],
        k: int = 60
    ) -> List[SearchResult]:
        scores = defaultdict(float)
        metadata_map = {}
        content_map = {}
        
        for rank, result in enumerate(vector_results, 1):
            scores[result.doc_id] += self.config.vector_weight / (k + rank)
            metadata_map[result.doc_id] = result.metadata
            content_map[result.doc_id] = result.content
        
        for rank, result in enumerate(bm25_results, 1):
            scores[result.doc_id] += self.config.bm25_weight / (k + rank)
            if result.doc_id not in metadata_map:
                metadata_map[result.doc_id] = result.metadata
                content_map[result.doc_id] = result.content
        
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        return [
            SearchResult(
                doc_id=doc_id,
                content=content_map[doc_id],
                score=score,
                metadata=metadata_map[doc_id],
                source='hybrid'
            )
            for doc_id, score in sorted_results[:self.config.top_k]
        ]
    
    def _weighted_fusion(
        self,
        vector_results: List[SearchResult],
        bm25_results: List[SearchResult]
    ) -> List[SearchResult]:
        combined_scores = defaultdict(float)
        metadata_map = {}
        content_map = {}
        
        if self.config.normalize_scores:
            vector_scores = self._normalize_scores([r.score for r in vector_results])
            bm25_scores = self._normalize_scores([r.score for r in bm25_results])
            
            for result, norm_score in zip(vector_results, vector_scores):
                combined_scores[result.doc_id] += norm_score * self.config.vector_weight
                metadata_map[result.doc_id] = result.metadata
                content_map[result.doc_id] = result.content
            
            for result, norm_score in zip(bm25_results, bm25_scores):
                combined_scores[result.doc_id] += norm_score * self.config.bm25_weight
                if result.doc_id not in metadata_map:
                    metadata_map[result.doc_id] = result.metadata
                    content_map[result.doc_id] = result.content
        else:
            for result in vector_results:
                combined_scores[result.doc_id] += result.score * self.config.vector_weight
                metadata_map[result.doc_id] = result.metadata
                content_map[result.doc_id] = result.content
            
            for result in bm25_results:
                combined_scores[result.doc_id] += result.score * self.config.bm25_weight
                if result.doc_id not in metadata_map:
                    metadata_map[result.doc_id] = result.metadata
                    content_map[result.doc_id] = result.content
        
        sorted_results = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)
        
        return [
            SearchResult(
                doc_id=doc_id,
                content=content_map[doc_id],
                score=score,
                metadata=metadata_map[doc_id],
                source='hybrid'
            )
            for doc_id, score in sorted_results[:self.config.top_k]
            if score >= self.config.min_score_threshold
        ]
    
    async def search_async(
        self,
        query: str,
        query_embedding: List[float]
    ) -> List[SearchResult]:
        loop = asyncio.get_event_loop()
        
        vector_task = loop.run_in_executor(
            self.executor,
            self._vector_search,
            query_embedding
        )
        
        bm25_task = loop.run_in_executor(
            self.executor,
            self._bm25_search,
            query
        )
        
        vector_results, bm25_results = await asyncio.gather(vector_task, bm25_task)
        
        if self.config.use_reciprocal_rank_fusion:
            return self._reciprocal_rank_fusion(vector_results, bm25_results, self.config.rrf_k)
        else:
            return self._weighted_fusion(vector_results, bm25_results)
    
    def search(
        self,
        query: str,
        query_embedding: List[float]
    ) -> List[SearchResult]:
        vector_results = self._vector_search(query_embedding)
        bm25_results = self._bm25_search(query)
        
        if self.config.use_reciprocal_rank_fusion:
            return self._reciprocal_rank_fusion(vector_results, bm25_results, self.config.rrf_k)
        else:
            return self._weighted_fusion(vector_results, bm25_results)
    
    def _vector_search(self, query_embedding: List[float]) -> List[SearchResult]:
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=self.config.rerank_top_k
        )
        
        search_results = []
        if results['ids'] and results['ids'][0]:
            for i in range(len(results['ids'][0])):
                search_results.append(SearchResult(
                    doc_id=results['ids'][0][i],
                    content=results['documents'][0][i] if results['documents'] else "",
                    score=1.0 - results['distances'][0][i] if results['distances'] else 0.0,
                    metadata=results['metadatas'][0][i] if results['metadatas'] else {},
                    source='vector'
                ))
        
        return search_results
    
    def _bm25_search(self, query: str) -> List[SearchResult]:
        bm25_results = self.bm25_index.search(query, self.config.rerank_top_k)
        
        return [
            SearchResult(
                doc_id=doc_id,
                content=content,
                score=score,
                metadata=metadata,
                source='bm25'
            )
            for doc_id, score, content, metadata in bm25_results
        ]
    
    def get_statistics(self) -> Dict[str, Any]:
        return {
            "total_documents": len(self.bm25_index.documents),
            "vector_collection_count": self.collection.count(),
            "config": {
                "vector_weight": self.config.vector_weight,
                "bm25_weight": self.config.bm25_weight,
                "fusion_method": "RRF" if self.config.use_reciprocal_rank_fusion else "Weighted",
                "normalize_scores": self.config.normalize_scores
            }
        }