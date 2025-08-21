from typing import List, Union, Dict, Any, Optional
from enum import Enum
import os
from abc import ABC, abstractmethod
import numpy as np
from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings import HuggingFaceEmbeddings
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)


class EmbeddingModel(str, Enum):
    OPENAI_ADA_002 = "text-embedding-ada-002"
    OPENAI_3_SMALL = "text-embedding-3-small"
    OPENAI_3_LARGE = "text-embedding-3-large"
    MINILM_L6_V2 = "all-MiniLM-L6-v2"
    MPNET_BASE_V2 = "all-mpnet-base-v2"
    INSTRUCTOR_XL = "instructor-xl"
    BGE_LARGE_EN = "BAAI/bge-large-en-v1.5"
    E5_LARGE_V2 = "intfloat/e5-large-v2"


class BaseEmbeddingStrategy(ABC):
    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        pass
    
    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        pass
    
    @abstractmethod
    def get_embedding_dimension(self) -> int:
        pass


class OpenAIEmbeddingStrategy(BaseEmbeddingStrategy):
    def __init__(self, model_name: str, api_key: Optional[str] = None):
        self.model_name = model_name
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.embeddings = OpenAIEmbeddings(
            model=model_name,
            openai_api_key=self.api_key
        )
        self.dimension_map = {
            "text-embedding-ada-002": 1536,
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072
        }
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.embeddings.embed_documents(texts)
    
    def embed_query(self, text: str) -> List[float]:
        return self.embeddings.embed_query(text)
    
    def get_embedding_dimension(self) -> int:
        return self.dimension_map.get(self.model_name, 1536)


class HuggingFaceEmbeddingStrategy(BaseEmbeddingStrategy):
    def __init__(self, model_name: str, device: str = "cpu", normalize: bool = True):
        self.model_name = model_name
        self.device = device
        self.normalize = normalize
        
        model_kwargs = {"device": device}
        encode_kwargs = {"normalize_embeddings": normalize}
        
        self.embeddings = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs=model_kwargs,
            encode_kwargs=encode_kwargs
        )
        
        self.dimension_map = {
            "all-MiniLM-L6-v2": 384,
            "all-mpnet-base-v2": 768,
            "instructor-xl": 768,
            "BAAI/bge-large-en-v1.5": 1024,
            "intfloat/e5-large-v2": 1024
        }
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.embeddings.embed_documents(texts)
    
    def embed_query(self, text: str) -> List[float]:
        return self.embeddings.embed_query(text)
    
    def get_embedding_dimension(self) -> int:
        return self.dimension_map.get(self.model_name, 768)


class EmbeddingFactory:
    _instances: Dict[str, BaseEmbeddingStrategy] = {}
    
    @classmethod
    def create_embeddings(
        cls,
        model: Union[str, EmbeddingModel] = None,
        **kwargs
    ) -> BaseEmbeddingStrategy:
        if model is None:
            model = os.getenv("EMBEDDING_MODEL", EmbeddingModel.OPENAI_ADA_002)
        
        if isinstance(model, str) and model not in [e.value for e in EmbeddingModel]:
            logger.warning(f"Unknown model {model}, using default")
            model = EmbeddingModel.OPENAI_ADA_002
        
        model_str = model if isinstance(model, str) else model.value
        
        cache_key = f"{model_str}_{str(kwargs)}"
        if cache_key in cls._instances:
            return cls._instances[cache_key]
        
        if model_str.startswith("text-embedding"):
            strategy = OpenAIEmbeddingStrategy(model_str, **kwargs)
        else:
            strategy = HuggingFaceEmbeddingStrategy(model_str, **kwargs)
        
        cls._instances[cache_key] = strategy
        logger.info(f"Created embedding strategy for model: {model_str}")
        
        return strategy
    
    @classmethod
    def get_available_models(cls) -> List[Dict[str, Any]]:
        return [
            {
                "model": EmbeddingModel.OPENAI_ADA_002,
                "dimension": 1536,
                "provider": "OpenAI",
                "speed": "Fast",
                "quality": "Excellent",
                "cost": "$0.0001/1K tokens"
            },
            {
                "model": EmbeddingModel.OPENAI_3_SMALL,
                "dimension": 1536,
                "provider": "OpenAI",
                "speed": "Very Fast",
                "quality": "Good",
                "cost": "$0.00002/1K tokens"
            },
            {
                "model": EmbeddingModel.OPENAI_3_LARGE,
                "dimension": 3072,
                "provider": "OpenAI",
                "speed": "Moderate",
                "quality": "Best",
                "cost": "$0.00013/1K tokens"
            },
            {
                "model": EmbeddingModel.MINILM_L6_V2,
                "dimension": 384,
                "provider": "HuggingFace",
                "speed": "Very Fast",
                "quality": "Good",
                "cost": "Free (local)"
            },
            {
                "model": EmbeddingModel.MPNET_BASE_V2,
                "dimension": 768,
                "provider": "HuggingFace",
                "speed": "Moderate",
                "quality": "Very Good",
                "cost": "Free (local)"
            },
            {
                "model": EmbeddingModel.BGE_LARGE_EN,
                "dimension": 1024,
                "provider": "HuggingFace",
                "speed": "Slow",
                "quality": "Excellent",
                "cost": "Free (local)"
            }
        ]
    
    @classmethod
    def benchmark_model(
        cls,
        model: Union[str, EmbeddingModel],
        test_texts: List[str] = None
    ) -> Dict[str, Any]:
        import time
        
        if test_texts is None:
            test_texts = [
                "This is a test document for benchmarking.",
                "Machine learning models process text efficiently.",
                "Embeddings capture semantic meaning of text."
            ]
        
        strategy = cls.create_embeddings(model)
        
        start = time.time()
        doc_embeddings = strategy.embed_documents(test_texts)
        doc_time = time.time() - start
        
        start = time.time()
        query_embedding = strategy.embed_query(test_texts[0])
        query_time = time.time() - start
        
        return {
            "model": model if isinstance(model, str) else model.value,
            "dimension": strategy.get_embedding_dimension(),
            "doc_embedding_time": doc_time,
            "query_embedding_time": query_time,
            "avg_time_per_doc": doc_time / len(test_texts),
            "embeddings_shape": (len(doc_embeddings), len(doc_embeddings[0]))
        }