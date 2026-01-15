"""
Redis Cache Service
Comprehensive caching layer for all application cache needs
"""
import json
import pickle
from typing import Any, Optional, List, Dict
from datetime import datetime, timedelta
import redis
from app.config.redis_config import get_redis_client
from app.utils.json_encoder import safe_json_dumps, convert_numpy_types


class RedisCache:
    """
    Redis cache service with support for:
    - String values with TTL
    - JSON data
    - Hash maps
    - Sorted sets
    - Lists
    """
    
    def __init__(self, namespace: str = "fyntrix"):
        """
        Initialize Redis cache with namespace
        
        Args:
            namespace: Prefix for all keys to avoid collisions
        """
        self.redis = get_redis_client()
        self.namespace = namespace
    
    def _make_key(self, key: str) -> str:
        """Create namespaced key"""
        return f"{self.namespace}:{key}"
    
    # ========== STRING OPERATIONS ==========
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set a value with optional TTL
        
        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time to live in seconds
            
        Returns:
            True if successful
        """
        try:
            namespaced_key = self._make_key(key)
            # Convert numpy/pandas types before serialization
            safe_value = convert_numpy_types(value)
            serialized = safe_json_dumps(safe_value)
            
            if ttl:
                return self.redis.setex(namespaced_key, ttl, serialized)
            else:
                return self.redis.set(namespaced_key, serialized)
        except Exception as e:
            print(f"Redis set error: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value from cache
        
        Args:
            key: Cache key
            default: Default value if key not found
            
        Returns:
            Cached value or default
        """
        try:
            namespaced_key = self._make_key(key)
            value = self.redis.get(namespaced_key)
            
            if value is None:
                return default
            
            return json.loads(value)
        except Exception as e:
            print(f"Redis get error: {e}")
            return default
    
    def delete(self, key: str) -> bool:
        """Delete a key"""
        try:
            namespaced_key = self._make_key(key)
            return self.redis.delete(namespaced_key) > 0
        except Exception as e:
            print(f"Redis delete error: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists"""
        try:
            namespaced_key = self._make_key(key)
            return self.redis.exists(namespaced_key) > 0
        except Exception as e:
            print(f"Redis exists error: {e}")
            return False
    
    def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on existing key"""
        try:
            namespaced_key = self._make_key(key)
            return self.redis.expire(namespaced_key, ttl)
        except Exception as e:
            print(f"Redis expire error: {e}")
            return False
    
    def ttl(self, key: str) -> int:
        """Get remaining TTL in seconds (-1 = no expiry, -2 = doesn't exist)"""
        try:
            namespaced_key = self._make_key(key)
            return self.redis.ttl(namespaced_key)
        except Exception as e:
            print(f"Redis ttl error: {e}")
            return -2
    
    # ========== HASH OPERATIONS ==========
    
    def hset(self, key: str, field: str, value: Any) -> bool:
        """Set hash field"""
        try:
            namespaced_key = self._make_key(key)
            # Convert numpy/pandas types before serialization
            safe_value = convert_numpy_types(value)
            serialized = safe_json_dumps(safe_value)
            return self.redis.hset(namespaced_key, field, serialized) >= 0
        except Exception as e:
            print(f"Redis hset error: {e}")
            return False
    
    def hget(self, key: str, field: str, default: Any = None) -> Any:
        """Get hash field"""
        try:
            namespaced_key = self._make_key(key)
            value = self.redis.hget(namespaced_key, field)
            
            if value is None:
                return default
            
            return json.loads(value)
        except Exception as e:
            print(f"Redis hget error: {e}")
            return default
    
    def hgetall(self, key: str) -> Dict[str, Any]:
        """Get all hash fields"""
        try:
            namespaced_key = self._make_key(key)
            data = self.redis.hgetall(namespaced_key)
            
            result = {}
            for field, value in data.items():
                try:
                    result[field] = json.loads(value)
                except:
                    result[field] = value
            
            return result
        except Exception as e:
            print(f"Redis hgetall error: {e}")
            return {}
    
    def hdel(self, key: str, *fields: str) -> int:
        """Delete hash fields"""
        try:
            namespaced_key = self._make_key(key)
            return self.redis.hdel(namespaced_key, *fields)
        except Exception as e:
            print(f"Redis hdel error: {e}")
            return 0
    
    def hkeys(self, key: str) -> List[str]:
        """Get all hash field names"""
        try:
            namespaced_key = self._make_key(key)
            return self.redis.hkeys(namespaced_key)
        except Exception as e:
            print(f"Redis hkeys error: {e}")
            return []
    
    # ========== SORTED SET OPERATIONS ==========
    
    def zadd(self, key: str, mapping: Dict[str, float], nx: bool = False) -> int:
        """
        Add members to sorted set
        
        Args:
            key: Cache key
            mapping: Dict of {member: score}
            nx: Only add new elements (don't update existing)
            
        Returns:
            Number of elements added
        """
        try:
            namespaced_key = self._make_key(key)
            # Serialize members with safe encoder
            serialized_mapping = {safe_json_dumps(convert_numpy_types(k)): v for k, v in mapping.items()}
            return self.redis.zadd(namespaced_key, serialized_mapping, nx=nx)
        except Exception as e:
            print(f"Redis zadd error: {e}")
            return 0
    
    def zrange(self, key: str, start: int = 0, end: int = -1, 
               withscores: bool = False, desc: bool = False) -> List:
        """
        Get sorted set members by rank
        
        Args:
            key: Cache key
            start: Start index
            end: End index (-1 for all)
            withscores: Include scores in result
            desc: Descending order
            
        Returns:
            List of members or (member, score) tuples
        """
        try:
            namespaced_key = self._make_key(key)
            
            if desc:
                result = self.redis.zrevrange(namespaced_key, start, end, withscores=withscores)
            else:
                result = self.redis.zrange(namespaced_key, start, end, withscores=withscores)
            
            # Deserialize members
            if withscores:
                return [(json.loads(member), score) for member, score in result]
            else:
                return [json.loads(member) for member in result]
        except Exception as e:
            print(f"Redis zrange error: {e}")
            return []
    
    def zrem(self, key: str, *members: Any) -> int:
        """Remove members from sorted set"""
        try:
            namespaced_key = self._make_key(key)
            # Convert numpy/pandas types before serialization
            serialized_members = [safe_json_dumps(convert_numpy_types(m)) for m in members]
            return self.redis.zrem(namespaced_key, *serialized_members)
        except Exception as e:
            print(f"Redis zrem error: {e}")
            return 0
    
    def zcard(self, key: str) -> int:
        """Get sorted set size"""
        try:
            namespaced_key = self._make_key(key)
            return self.redis.zcard(namespaced_key)
        except Exception as e:
            print(f"Redis zcard error: {e}")
            return 0
    
    # ========== LIST OPERATIONS ==========
    
    def lpush(self, key: str, *values: Any) -> int:
        """Push values to list head"""
        try:
            namespaced_key = self._make_key(key)
            # Convert numpy/pandas types before serialization
            serialized = [safe_json_dumps(convert_numpy_types(v)) for v in values]
            return self.redis.lpush(namespaced_key, *serialized)
        except Exception as e:
            print(f"Redis lpush error: {e}")
            return 0
    
    def rpush(self, key: str, *values: Any) -> int:
        """Push values to list tail"""
        try:
            namespaced_key = self._make_key(key)
            # Convert numpy/pandas types before serialization
            serialized = [safe_json_dumps(convert_numpy_types(v)) for v in values]
            return self.redis.rpush(namespaced_key, *serialized)
        except Exception as e:
            print(f"Redis rpush error: {e}")
            return 0
    
    def lrange(self, key: str, start: int = 0, end: int = -1) -> List[Any]:
        """Get list range"""
        try:
            namespaced_key = self._make_key(key)
            values = self.redis.lrange(namespaced_key, start, end)
            return [json.loads(v) for v in values]
        except Exception as e:
            print(f"Redis lrange error: {e}")
            return []
    
    def llen(self, key: str) -> int:
        """Get list length"""
        try:
            namespaced_key = self._make_key(key)
            return self.redis.llen(namespaced_key)
        except Exception as e:
            print(f"Redis llen error: {e}")
            return 0
    
    # ========== UTILITY OPERATIONS ==========
    
    def keys(self, pattern: str = "*") -> List[str]:
        """Get keys matching pattern (use sparingly in production)"""
        try:
            namespaced_pattern = self._make_key(pattern)
            keys = self.redis.keys(namespaced_pattern)
            # Remove namespace prefix
            prefix = f"{self.namespace}:"
            return [k.replace(prefix, "", 1) for k in keys]
        except Exception as e:
            print(f"Redis keys error: {e}")
            return []
    
    def flushdb(self) -> bool:
        """Clear all keys in current database (USE WITH CAUTION)"""
        try:
            return self.redis.flushdb()
        except Exception as e:
            print(f"Redis flushdb error: {e}")
            return False
    
    def ping(self) -> bool:
        """Check Redis connection"""
        try:
            return self.redis.ping()
        except Exception as e:
            print(f"Redis ping error: {e}")
            return False


# Global cache instances for different namespaces
general_cache = RedisCache("fyntrix:general")
historical_cache = RedisCache("fyntrix:historical")
score_cache = RedisCache("fyntrix:scores")
sr_cache = RedisCache("fyntrix:support_resistance")
context_cache = RedisCache("fyntrix:context")
