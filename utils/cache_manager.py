"""
Caching utilities for Football Analytics AI
"""
import json
import hashlib
import time
from typing import Any, Optional, Dict
import os

# Try to import Redis, fall back to in-memory cache
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

class CacheManager:
    """Unified cache manager supporting Redis and in-memory fallback"""
    
    def __init__(self):
        self.redis_client = None
        self.memory_cache: Dict[str, Dict[str, Any]] = {}
        self.max_memory_items = 1000
        
        if REDIS_AVAILABLE:
            try:
                redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
                self.redis_client = redis.from_url(redis_url, decode_responses=True)
                # Test connection
                self.redis_client.ping()
                print("✅ Redis cache connected")
            except Exception as e:
                print(f"⚠️ Redis unavailable, using memory cache: {e}")
                self.redis_client = None
    
    def _generate_key(self, prefix: str, **kwargs) -> str:
        """Generate cache key from parameters"""
        # Sort kwargs for consistent keys
        sorted_params = sorted(kwargs.items())
        param_str = json.dumps(sorted_params, sort_keys=True)
        hash_obj = hashlib.md5(param_str.encode())
        return f"{prefix}:{hash_obj.hexdigest()}"
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if self.redis_client:
            try:
                value = self.redis_client.get(key)
                if value:
                    return json.loads(value)
            except Exception as e:
                print(f"Redis get error: {e}")
        
        # Fallback to memory cache
        if key in self.memory_cache:
            item = self.memory_cache[key]
            if time.time() - item["timestamp"] < item["ttl"]:
                return item["value"]
            else:
                del self.memory_cache[key]
        
        return None
    
    def set(self, key: str, value: Any, ttl: int = 3600):
        """Set value in cache with TTL"""
        if self.redis_client:
            try:
                self.redis_client.setex(key, ttl, json.dumps(value, default=str))
                return
            except Exception as e:
                print(f"Redis set error: {e}")
        
        # Fallback to memory cache
        if len(self.memory_cache) >= self.max_memory_items:
            # Remove oldest items
            oldest_keys = sorted(
                self.memory_cache.keys(),
                key=lambda k: self.memory_cache[k]["timestamp"]
            )[:100]
            for old_key in oldest_keys:
                del self.memory_cache[old_key]
        
        self.memory_cache[key] = {
            "value": value,
            "timestamp": time.time(),
            "ttl": ttl
        }
    
    def cache_player_search(self, query: str, k: int = 5):
        """Cache decorator for player search"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                cache_key = self._generate_key("player_search", query=query, k=k)
                cached = self.get(cache_key)
                if cached is not None:
                    return cached
                
                result = func(*args, **kwargs)
                self.set(cache_key, result, ttl=1800)  # 30 minutes
                return result
            return wrapper
        return decorator
    
    def cache_player_stats(self, player: str, stat: str, seasons_back: int):
        """Cache decorator for player statistics"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                cache_key = self._generate_key("player_stats", 
                                              player=player, stat=stat, seasons_back=seasons_back)
                cached = self.get(cache_key)
                if cached is not None:
                    return cached
                
                result = func(*args, **kwargs)
                self.set(cache_key, result, ttl=3600)  # 1 hour
                return result
            return wrapper
        return decorator

# Global cache instance
cache_manager = CacheManager()