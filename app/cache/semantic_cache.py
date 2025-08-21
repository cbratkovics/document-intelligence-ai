from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import json
import hashlib
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import redis
from redis.exceptions import RedisError
import logging
import pickle
from enum import Enum
from collections import OrderedDict
import asyncio
from functools import wraps

logger = logging.getLogger(__name__)


class CacheStrategy(str, Enum):
    EXACT_MATCH = "exact_match"
    SEMANTIC_SIMILARITY = "semantic_similarity"
    HYBRID = "hybrid"


class TTLStrategy(str, Enum):
    FIXED = "fixed"
    SLIDING_WINDOW = "sliding_window"
    ADAPTIVE = "adaptive"


@dataclass
class CacheEntry:
    query: str
    query_embedding: List[float]
    response: str
    metadata: Dict[str, Any]
    timestamp: datetime
    hit_count: int = 0
    last_accessed: datetime = None
    ttl_seconds: int = 3600


class SemanticCache:
    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        similarity_threshold: float = 0.95,
        max_cache_size: int = 10000,
        default_ttl: int = 3600,
        cache_strategy: CacheStrategy = CacheStrategy.HYBRID,
        ttl_strategy: TTLStrategy = TTLStrategy.SLIDING_WINDOW
    ):
        self.redis_client = redis_client or self._create_redis_client()
        self.similarity_threshold = similarity_threshold
        self.max_cache_size = max_cache_size
        self.default_ttl = default_ttl
        self.cache_strategy = cache_strategy
        self.ttl_strategy = ttl_strategy
        
        self.local_cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.embeddings_cache: Dict[str, List[float]] = {}
        
        self.stats = {
            "total_queries": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "semantic_hits": 0,
            "exact_hits": 0,
            "avg_similarity_score": 0.0
        }
    
    def _create_redis_client(self) -> redis.Redis:
        try:
            client = redis.Redis(
                host='localhost',
                port=6379,
                db=0,
                decode_responses=False,
                socket_connect_timeout=5
            )
            client.ping()
            logger.info("Connected to Redis for semantic caching")
            return client
        except RedisError as e:
            logger.warning(f"Redis connection failed: {e}. Using in-memory cache only.")
            return None
    
    def _get_cache_key(self, query: str) -> str:
        return f"semantic_cache:{hashlib.md5(query.encode()).hexdigest()}"
    
    def _calculate_ttl(self, entry: CacheEntry) -> int:
        if self.ttl_strategy == TTLStrategy.FIXED:
            return self.default_ttl
        
        elif self.ttl_strategy == TTLStrategy.SLIDING_WINDOW:
            base_ttl = self.default_ttl
            extension = min(entry.hit_count * 600, 7200)
            return base_ttl + extension
        
        elif self.ttl_strategy == TTLStrategy.ADAPTIVE:
            now = datetime.now()
            time_since_creation = (now - entry.timestamp).seconds
            
            if entry.hit_count > 10:
                return 7200
            elif entry.hit_count > 5:
                return 3600
            elif time_since_creation < 300:
                return 1800
            else:
                return self.default_ttl
        
        return self.default_ttl
    
    def _find_semantic_match(
        self,
        query_embedding: List[float],
        top_k: int = 5
    ) -> Optional[Tuple[str, float, CacheEntry]]:
        if not self.embeddings_cache:
            return None
        
        query_vec = np.array(query_embedding).reshape(1, -1)
        
        best_match = None
        best_score = 0.0
        
        for cached_query, cached_embedding in self.embeddings_cache.items():
            cached_vec = np.array(cached_embedding).reshape(1, -1)
            similarity = cosine_similarity(query_vec, cached_vec)[0][0]
            
            if similarity >= self.similarity_threshold and similarity > best_score:
                if cached_query in self.local_cache:
                    best_match = (cached_query, similarity, self.local_cache[cached_query])
                    best_score = similarity
        
        return best_match
    
    def _evict_if_needed(self):
        if len(self.local_cache) >= self.max_cache_size:
            num_to_evict = len(self.local_cache) // 10
            
            sorted_entries = sorted(
                self.local_cache.items(),
                key=lambda x: (x[1].hit_count, x[1].last_accessed or x[1].timestamp)
            )
            
            for key, _ in sorted_entries[:num_to_evict]:
                del self.local_cache[key]
                if key in self.embeddings_cache:
                    del self.embeddings_cache[key]
                
                if self.redis_client:
                    try:
                        self.redis_client.delete(self._get_cache_key(key))
                    except RedisError:
                        pass
    
    async def get_async(
        self,
        query: str,
        query_embedding: Optional[List[float]] = None
    ) -> Optional[str]:
        return await asyncio.get_event_loop().run_in_executor(
            None,
            self.get,
            query,
            query_embedding
        )
    
    def get(
        self,
        query: str,
        query_embedding: Optional[List[float]] = None
    ) -> Optional[str]:
        self.stats["total_queries"] += 1
        
        if self.cache_strategy in [CacheStrategy.EXACT_MATCH, CacheStrategy.HYBRID]:
            if query in self.local_cache:
                entry = self.local_cache[query]
                entry.hit_count += 1
                entry.last_accessed = datetime.now()
                
                self.local_cache.move_to_end(query)
                
                self.stats["cache_hits"] += 1
                self.stats["exact_hits"] += 1
                
                logger.debug(f"Exact cache hit for query: {query[:50]}...")
                return entry.response
            
            if self.redis_client:
                try:
                    cache_key = self._get_cache_key(query)
                    cached_data = self.redis_client.get(cache_key)
                    
                    if cached_data:
                        entry = pickle.loads(cached_data)
                        entry.hit_count += 1
                        entry.last_accessed = datetime.now()
                        
                        self.local_cache[query] = entry
                        if len(self.local_cache) > self.max_cache_size:
                            self.local_cache.popitem(last=False)
                        
                        ttl = self._calculate_ttl(entry)
                        self.redis_client.setex(cache_key, ttl, pickle.dumps(entry))
                        
                        self.stats["cache_hits"] += 1
                        self.stats["exact_hits"] += 1
                        
                        return entry.response
                except RedisError as e:
                    logger.warning(f"Redis get error: {e}")
        
        if self.cache_strategy in [CacheStrategy.SEMANTIC_SIMILARITY, CacheStrategy.HYBRID]:
            if query_embedding:
                match = self._find_semantic_match(query_embedding)
                
                if match:
                    matched_query, similarity, entry = match
                    entry.hit_count += 1
                    entry.last_accessed = datetime.now()
                    
                    self.stats["cache_hits"] += 1
                    self.stats["semantic_hits"] += 1
                    self.stats["avg_similarity_score"] = (
                        self.stats["avg_similarity_score"] * 0.9 + similarity * 0.1
                    )
                    
                    logger.debug(
                        f"Semantic cache hit (similarity: {similarity:.3f}) "
                        f"for query: {query[:50]}..."
                    )
                    
                    return entry.response
        
        self.stats["cache_misses"] += 1
        return None
    
    async def set_async(
        self,
        query: str,
        response: str,
        query_embedding: Optional[List[float]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        return await asyncio.get_event_loop().run_in_executor(
            None,
            self.set,
            query,
            response,
            query_embedding,
            metadata
        )
    
    def set(
        self,
        query: str,
        response: str,
        query_embedding: Optional[List[float]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self._evict_if_needed()
        
        entry = CacheEntry(
            query=query,
            query_embedding=query_embedding or [],
            response=response,
            metadata=metadata or {},
            timestamp=datetime.now(),
            last_accessed=datetime.now(),
            ttl_seconds=self.default_ttl
        )
        
        self.local_cache[query] = entry
        
        if query_embedding:
            self.embeddings_cache[query] = query_embedding
        
        if self.redis_client:
            try:
                cache_key = self._get_cache_key(query)
                ttl = self._calculate_ttl(entry)
                self.redis_client.setex(cache_key, ttl, pickle.dumps(entry))
            except RedisError as e:
                logger.warning(f"Redis set error: {e}")
        
        logger.debug(f"Cached response for query: {query[:50]}...")
    
    def invalidate(self, query: str):
        if query in self.local_cache:
            del self.local_cache[query]
        
        if query in self.embeddings_cache:
            del self.embeddings_cache[query]
        
        if self.redis_client:
            try:
                self.redis_client.delete(self._get_cache_key(query))
            except RedisError:
                pass
    
    def clear(self):
        self.local_cache.clear()
        self.embeddings_cache.clear()
        
        if self.redis_client:
            try:
                pattern = "semantic_cache:*"
                for key in self.redis_client.scan_iter(match=pattern):
                    self.redis_client.delete(key)
            except RedisError as e:
                logger.warning(f"Redis clear error: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        hit_rate = (
            self.stats["cache_hits"] / self.stats["total_queries"]
            if self.stats["total_queries"] > 0
            else 0.0
        )
        
        return {
            "total_queries": self.stats["total_queries"],
            "cache_hits": self.stats["cache_hits"],
            "cache_misses": self.stats["cache_misses"],
            "hit_rate": hit_rate,
            "semantic_hits": self.stats["semantic_hits"],
            "exact_hits": self.stats["exact_hits"],
            "avg_similarity_score": self.stats["avg_similarity_score"],
            "cache_size": len(self.local_cache),
            "embeddings_cached": len(self.embeddings_cache),
            "cache_strategy": self.cache_strategy.value,
            "ttl_strategy": self.ttl_strategy.value,
            "similarity_threshold": self.similarity_threshold
        }


def semantic_cache_decorator(
    cache: SemanticCache,
    get_embedding_func=None
):
    def decorator(func):
        @wraps(func)
        async def async_wrapper(query: str, *args, **kwargs):
            embedding = None
            if get_embedding_func:
                embedding = await get_embedding_func(query)
            
            cached_response = await cache.get_async(query, embedding)
            if cached_response:
                return cached_response
            
            response = await func(query, *args, **kwargs)
            
            await cache.set_async(query, response, embedding)
            
            return response
        
        @wraps(func)
        def sync_wrapper(query: str, *args, **kwargs):
            embedding = None
            if get_embedding_func:
                embedding = get_embedding_func(query)
            
            cached_response = cache.get(query, embedding)
            if cached_response:
                return cached_response
            
            response = func(query, *args, **kwargs)
            
            cache.set(query, response, embedding)
            
            return response
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator