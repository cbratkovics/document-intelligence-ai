from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import numpy as np
import logging
from enum import Enum
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import time

logger = logging.getLogger(__name__)


class CrossEncoderModel(str, Enum):
    MS_MARCO_MINILM_L6 = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    MS_MARCO_MINILM_L12 = "cross-encoder/ms-marco-MiniLM-L-12-v2"
    MS_MARCO_ELECTRA = "cross-encoder/ms-marco-electra-base"
    QNLI_DISTILROBERTA = "cross-encoder/qnli-distilroberta-base"
    STSB_ROBERTA = "cross-encoder/stsb-roberta-large"
    NLI_DEBERTA_V3 = "cross-encoder/nli-deberta-v3-base"


@dataclass
class RerankResult:
    doc_id: str
    content: str
    original_score: float
    rerank_score: float
    metadata: Dict[str, Any]
    original_rank: int
    new_rank: int


@dataclass
class CrossEncoderConfig:
    model_name: str = CrossEncoderModel.MS_MARCO_MINILM_L6.value
    device: str = "cpu"
    max_length: int = 512
    batch_size: int = 32
    num_workers: int = 2
    cache_size: int = 1000
    use_fp16: bool = False


class CrossEncoderReranker:
    def __init__(self, config: CrossEncoderConfig = None):
        self.config = config or CrossEncoderConfig()
        
        if torch.cuda.is_available() and self.config.device == "cpu":
            self.config.device = "cuda"
            logger.info("CUDA available, using GPU for reranking")
        
        self.device = torch.device(self.config.device)
        
        self.tokenizer = AutoTokenizer.from_pretrained(self.config.model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.config.model_name)
        self.model.to(self.device)
        self.model.eval()
        
        if self.config.use_fp16 and self.device.type == "cuda":
            self.model = self.model.half()
        
        self.executor = ThreadPoolExecutor(max_workers=self.config.num_workers)
        
        self._score_cache = {}
        self.stats = {
            "total_reranks": 0,
            "total_documents": 0,
            "avg_rerank_time": 0.0,
            "cache_hits": 0
        }
    
    @lru_cache(maxsize=1000)
    def _get_cache_key(self, query: str, document: str) -> str:
        return f"{hash(query)}_{hash(document[:500])}"
    
    def _prepare_inputs(
        self,
        query: str,
        documents: List[str]
    ) -> torch.Tensor:
        inputs = self.tokenizer(
            [query] * len(documents),
            documents,
            padding=True,
            truncation=True,
            max_length=self.config.max_length,
            return_tensors="pt"
        )
        
        return {k: v.to(self.device) for k, v in inputs.items()}
    
    def _compute_scores_batch(
        self,
        query: str,
        documents: List[str]
    ) -> List[float]:
        with torch.no_grad():
            inputs = self._prepare_inputs(query, documents)
            outputs = self.model(**inputs)
            
            if outputs.logits.shape[-1] == 1:
                scores = outputs.logits.squeeze(-1)
            else:
                scores = torch.nn.functional.softmax(outputs.logits, dim=-1)[:, 1]
            
            return scores.cpu().numpy().tolist()
    
    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: Optional[int] = None
    ) -> List[RerankResult]:
        start_time = time.time()
        self.stats["total_reranks"] += 1
        self.stats["total_documents"] += len(documents)
        
        results = []
        scores = []
        
        for i in range(0, len(documents), self.config.batch_size):
            batch = documents[i:i + self.config.batch_size]
            batch_texts = [doc.get("content", "") for doc in batch]
            
            batch_scores = []
            for text in batch_texts:
                cache_key = self._get_cache_key(query, text)
                
                if cache_key in self._score_cache:
                    batch_scores.append(self._score_cache[cache_key])
                    self.stats["cache_hits"] += 1
                else:
                    computed_scores = self._compute_scores_batch(query, [text])
                    score = computed_scores[0]
                    self._score_cache[cache_key] = score
                    batch_scores.append(score)
                    
                    if len(self._score_cache) > self.config.cache_size:
                        self._score_cache.popitem()
            
            scores.extend(batch_scores)
        
        for i, (doc, score) in enumerate(zip(documents, scores)):
            results.append(RerankResult(
                doc_id=doc.get("id", str(i)),
                content=doc.get("content", ""),
                original_score=doc.get("score", 0.0),
                rerank_score=float(score),
                metadata=doc.get("metadata", {}),
                original_rank=i + 1,
                new_rank=0
            ))
        
        results.sort(key=lambda x: x.rerank_score, reverse=True)
        
        for i, result in enumerate(results):
            result.new_rank = i + 1
        
        elapsed_time = time.time() - start_time
        self.stats["avg_rerank_time"] = (
            self.stats["avg_rerank_time"] * 0.9 + elapsed_time * 0.1
        )
        
        if top_k:
            results = results[:top_k]
        
        logger.debug(
            f"Reranked {len(documents)} documents in {elapsed_time:.3f}s, "
            f"returning top {len(results)}"
        )
        
        return results
    
    async def rerank_async(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: Optional[int] = None
    ) -> List[RerankResult]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self.rerank,
            query,
            documents,
            top_k
        )
    
    def batch_rerank(
        self,
        queries: List[str],
        documents_list: List[List[Dict[str, Any]]],
        top_k: Optional[int] = None
    ) -> List[List[RerankResult]]:
        results = []
        
        for query, documents in zip(queries, documents_list):
            results.append(self.rerank(query, documents, top_k))
        
        return results
    
    def get_statistics(self) -> Dict[str, Any]:
        return {
            "model": self.config.model_name,
            "device": str(self.device),
            "total_reranks": self.stats["total_reranks"],
            "total_documents": self.stats["total_documents"],
            "avg_documents_per_rerank": (
                self.stats["total_documents"] / self.stats["total_reranks"]
                if self.stats["total_reranks"] > 0 else 0
            ),
            "avg_rerank_time_ms": self.stats["avg_rerank_time"] * 1000,
            "cache_size": len(self._score_cache),
            "cache_hits": self.stats["cache_hits"],
            "cache_hit_rate": (
                self.stats["cache_hits"] / self.stats["total_documents"]
                if self.stats["total_documents"] > 0 else 0
            )
        }


class LightweightReranker:
    def __init__(self):
        self.stats = {
            "total_reranks": 0,
            "avg_rerank_time": 0.0
        }
    
    def _calculate_relevance_score(
        self,
        query: str,
        document: str
    ) -> float:
        query_terms = set(query.lower().split())
        doc_terms = set(document.lower().split())
        
        if not query_terms:
            return 0.0
        
        exact_matches = len(query_terms.intersection(doc_terms))
        
        partial_matches = 0
        for q_term in query_terms:
            for d_term in doc_terms:
                if q_term in d_term or d_term in q_term:
                    partial_matches += 0.5
                    break
        
        query_coverage = (exact_matches + partial_matches) / len(query_terms)
        
        doc_length_penalty = min(1.0, 100 / max(len(doc_terms), 1))
        
        return query_coverage * 0.7 + doc_length_penalty * 0.3
    
    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: Optional[int] = None
    ) -> List[RerankResult]:
        start_time = time.time()
        self.stats["total_reranks"] += 1
        
        results = []
        
        for i, doc in enumerate(documents):
            content = doc.get("content", "")
            relevance_score = self._calculate_relevance_score(query, content)
            
            combined_score = (
                doc.get("score", 0.0) * 0.4 +
                relevance_score * 0.6
            )
            
            results.append(RerankResult(
                doc_id=doc.get("id", str(i)),
                content=content,
                original_score=doc.get("score", 0.0),
                rerank_score=combined_score,
                metadata=doc.get("metadata", {}),
                original_rank=i + 1,
                new_rank=0
            ))
        
        results.sort(key=lambda x: x.rerank_score, reverse=True)
        
        for i, result in enumerate(results):
            result.new_rank = i + 1
        
        elapsed_time = time.time() - start_time
        self.stats["avg_rerank_time"] = (
            self.stats["avg_rerank_time"] * 0.9 + elapsed_time * 0.1
        )
        
        if top_k:
            results = results[:top_k]
        
        return results


class RerankingFactory:
    @classmethod
    def create_reranker(
        cls,
        use_cross_encoder: bool = True,
        config: Optional[CrossEncoderConfig] = None
    ):
        if use_cross_encoder:
            try:
                return CrossEncoderReranker(config)
            except Exception as e:
                logger.warning(
                    f"Failed to load cross-encoder model: {e}. "
                    "Falling back to lightweight reranker."
                )
                return LightweightReranker()
        else:
            return LightweightReranker()
    
    @classmethod
    def get_available_models(cls) -> List[Dict[str, Any]]:
        return [
            {
                "model": CrossEncoderModel.MS_MARCO_MINILM_L6,
                "size": "22M params",
                "speed": "Very Fast",
                "quality": "Good",
                "use_case": "General purpose reranking"
            },
            {
                "model": CrossEncoderModel.MS_MARCO_MINILM_L12,
                "size": "33M params",
                "speed": "Fast",
                "quality": "Very Good",
                "use_case": "Balanced speed/quality"
            },
            {
                "model": CrossEncoderModel.MS_MARCO_ELECTRA,
                "size": "110M params",
                "speed": "Moderate",
                "quality": "Excellent",
                "use_case": "High-quality reranking"
            },
            {
                "model": "lightweight",
                "size": "No model",
                "speed": "Instant",
                "quality": "Basic",
                "use_case": "Fallback/testing"
            }
        ]