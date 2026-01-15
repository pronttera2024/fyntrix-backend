"""
Redis Monitoring and Dashboard API
Provides comprehensive Redis visibility and management
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List, Optional
from datetime import datetime
import json

router = APIRouter(prefix="/v1/redis", tags=["redis-monitor"])


def get_redis_connection():
    """Get Redis connection with error handling"""
    try:
        from ..services.redis_client import get_redis_client
        client = get_redis_client()
        if not client:
            return None
        return client
    except Exception as e:
        print(f"Redis connection error: {e}")
        return None


@router.get("/status")
async def redis_status() -> Dict[str, Any]:
    """
    Get Redis connection status and basic info
    
    Returns:
        Connection status, version, and basic metrics
    """
    redis = get_redis_connection()
    
    if not redis:
        return {
            "status": "disconnected",
            "connected": False,
            "message": "Redis is not available or not configured"
        }
    
    try:
        # Test connection
        redis.ping()
        
        # Get server info
        info = redis.info()
        
        return {
            "status": "connected",
            "connected": True,
            "redis_version": info.get("redis_version", "unknown"),
            "uptime_seconds": info.get("uptime_in_seconds", 0),
            "uptime_days": round(info.get("uptime_in_seconds", 0) / 86400, 2),
            "connected_clients": info.get("connected_clients", 0),
            "used_memory_human": info.get("used_memory_human", "0B"),
            "used_memory_peak_human": info.get("used_memory_peak_human", "0B"),
            "total_commands_processed": info.get("total_commands_processed", 0),
            "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
        }
    except Exception as e:
        return {
            "status": "error",
            "connected": False,
            "error": str(e)
        }


@router.get("/info")
async def redis_info(section: Optional[str] = Query(None, description="Info section: server, memory, stats, etc.")) -> Dict[str, Any]:
    """
    Get detailed Redis INFO output
    
    Args:
        section: Optional section filter (server, memory, stats, replication, etc.)
        
    Returns:
        Detailed Redis server information
    """
    redis = get_redis_connection()
    
    if not redis:
        raise HTTPException(status_code=503, detail="Redis not available")
    
    try:
        if section:
            info = redis.info(section)
        else:
            info = redis.info()
        
        return {
            "status": "success",
            "section": section or "all",
            "data": info
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get Redis info: {str(e)}")


@router.get("/keys")
async def list_keys(
    pattern: str = Query("*", description="Key pattern (e.g., 'top_picks:*', 'fyntrix:*')"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum keys to return")
) -> Dict[str, Any]:
    """
    List Redis keys matching a pattern
    
    Args:
        pattern: Glob pattern for key matching
        limit: Maximum number of keys to return
        
    Returns:
        List of matching keys with metadata
    """
    redis = get_redis_connection()
    
    if not redis:
        raise HTTPException(status_code=503, detail="Redis not available")
    
    try:
        # Get matching keys
        keys = []
        for key in redis.scan_iter(match=pattern, count=100):
            if len(keys) >= limit:
                break
            
            key_str = key.decode() if isinstance(key, bytes) else str(key)
            
            # Get key type and TTL
            key_type = redis.type(key).decode() if isinstance(redis.type(key), bytes) else redis.type(key)
            ttl = redis.ttl(key)
            
            # Get memory usage (if available)
            try:
                memory = redis.memory_usage(key)
            except:
                memory = None
            
            keys.append({
                "key": key_str,
                "type": key_type,
                "ttl": ttl if ttl >= 0 else None,
                "ttl_human": f"{ttl}s" if ttl > 0 else ("no expiry" if ttl == -1 else "expired"),
                "memory_bytes": memory
            })
        
        return {
            "status": "success",
            "pattern": pattern,
            "count": len(keys),
            "limit": limit,
            "keys": keys
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list keys: {str(e)}")


@router.get("/key/{key:path}")
async def get_key_value(key: str) -> Dict[str, Any]:
    """
    Get value of a specific Redis key
    
    Args:
        key: Redis key name
        
    Returns:
        Key value and metadata
    """
    redis = get_redis_connection()
    
    if not redis:
        raise HTTPException(status_code=503, detail="Redis not available")
    
    try:
        # Check if key exists
        if not redis.exists(key):
            raise HTTPException(status_code=404, detail=f"Key '{key}' not found")
        
        # Get key type
        key_type = redis.type(key).decode() if isinstance(redis.type(key), bytes) else redis.type(key)
        ttl = redis.ttl(key)
        
        # Get value based on type
        value = None
        if key_type == "string":
            raw_value = redis.get(key)
            if raw_value:
                value_str = raw_value.decode() if isinstance(raw_value, bytes) else str(raw_value)
                # Try to parse as JSON
                try:
                    value = json.loads(value_str)
                except:
                    value = value_str
        elif key_type == "hash":
            value = redis.hgetall(key)
        elif key_type == "list":
            value = redis.lrange(key, 0, -1)
        elif key_type == "set":
            value = list(redis.smembers(key))
        elif key_type == "zset":
            value = redis.zrange(key, 0, -1, withscores=True)
        
        return {
            "status": "success",
            "key": key,
            "type": key_type,
            "ttl": ttl if ttl >= 0 else None,
            "value": value
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get key: {str(e)}")


@router.delete("/key/{key:path}")
async def delete_key(key: str) -> Dict[str, Any]:
    """
    Delete a specific Redis key
    
    Args:
        key: Redis key name
        
    Returns:
        Deletion status
    """
    redis = get_redis_connection()
    
    if not redis:
        raise HTTPException(status_code=503, detail="Redis not available")
    
    try:
        deleted = redis.delete(key)
        
        if deleted:
            return {
                "status": "success",
                "message": f"Key '{key}' deleted",
                "deleted": True
            }
        else:
            return {
                "status": "success",
                "message": f"Key '{key}' not found",
                "deleted": False
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete key: {str(e)}")


@router.get("/stats")
async def redis_stats() -> Dict[str, Any]:
    """
    Get Redis statistics and metrics
    
    Returns:
        Comprehensive Redis statistics
    """
    redis = get_redis_connection()
    
    if not redis:
        raise HTTPException(status_code=503, detail="Redis not available")
    
    try:
        info = redis.info()
        
        # Memory stats
        memory_stats = {
            "used_memory": info.get("used_memory", 0),
            "used_memory_human": info.get("used_memory_human", "0B"),
            "used_memory_peak": info.get("used_memory_peak", 0),
            "used_memory_peak_human": info.get("used_memory_peak_human", "0B"),
            "maxmemory": info.get("maxmemory", 0),
            "maxmemory_human": info.get("maxmemory_human", "0B"),
            "mem_fragmentation_ratio": info.get("mem_fragmentation_ratio", 0),
        }
        
        # Stats
        stats = {
            "total_connections_received": info.get("total_connections_received", 0),
            "total_commands_processed": info.get("total_commands_processed", 0),
            "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
            "total_net_input_bytes": info.get("total_net_input_bytes", 0),
            "total_net_output_bytes": info.get("total_net_output_bytes", 0),
            "keyspace_hits": info.get("keyspace_hits", 0),
            "keyspace_misses": info.get("keyspace_misses", 0),
        }
        
        # Calculate hit rate
        hits = stats["keyspace_hits"]
        misses = stats["keyspace_misses"]
        total = hits + misses
        hit_rate = round((hits / total * 100), 2) if total > 0 else 0
        
        # Keyspace info
        keyspace = {}
        for key, value in info.items():
            if key.startswith("db"):
                keyspace[key] = value
        
        return {
            "status": "success",
            "memory": memory_stats,
            "stats": stats,
            "hit_rate_percent": hit_rate,
            "keyspace": keyspace,
            "uptime_seconds": info.get("uptime_in_seconds", 0),
            "connected_clients": info.get("connected_clients", 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.post("/flush")
async def flush_redis(
    confirm: bool = Query(False, description="Must be true to confirm flush")
) -> Dict[str, Any]:
    """
    Flush all Redis data (DANGEROUS!)
    
    Args:
        confirm: Must be true to execute
        
    Returns:
        Flush status
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Must set confirm=true to flush Redis. This will delete ALL data!"
        )
    
    redis = get_redis_connection()
    
    if not redis:
        raise HTTPException(status_code=503, detail="Redis not available")
    
    try:
        redis.flushdb()
        
        return {
            "status": "success",
            "message": "Redis database flushed successfully",
            "warning": "All cache data has been deleted"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to flush Redis: {str(e)}")


@router.get("/dashboard")
async def redis_dashboard() -> Dict[str, Any]:
    """
    Get comprehensive Redis dashboard data
    
    Returns:
        All Redis metrics for dashboard display
    """
    redis = get_redis_connection()
    
    if not redis:
        return {
            "status": "disconnected",
            "connected": False,
            "message": "Redis is not available"
        }
    
    try:
        info = redis.info()
        
        # Count keys by pattern
        key_patterns = {
            "top_picks": "top_picks:*",
            "fyntrix_general": "fyntrix:general:*",
            "fyntrix_scores": "fyntrix:scores:*",
            "portfolio": "portfolio:*",
            "dashboard": "dashboard:*",
            "scalping": "scalping:*",
        }
        
        key_counts = {}
        for name, pattern in key_patterns.items():
            count = sum(1 for _ in redis.scan_iter(match=pattern, count=1000))
            key_counts[name] = count
        
        # Get total keys
        total_keys = redis.dbsize()
        
        # Calculate hit rate
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        total = hits + misses
        hit_rate = round((hits / total * 100), 2) if total > 0 else 0
        
        return {
            "status": "connected",
            "connected": True,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "server": {
                "version": info.get("redis_version", "unknown"),
                "uptime_days": round(info.get("uptime_in_seconds", 0) / 86400, 2),
                "connected_clients": info.get("connected_clients", 0),
            },
            "memory": {
                "used": info.get("used_memory_human", "0B"),
                "peak": info.get("used_memory_peak_human", "0B"),
                "max": info.get("maxmemory_human", "0B"),
                "fragmentation_ratio": info.get("mem_fragmentation_ratio", 0),
            },
            "performance": {
                "ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
                "total_commands": info.get("total_commands_processed", 0),
                "hit_rate_percent": hit_rate,
                "hits": hits,
                "misses": misses,
            },
            "keys": {
                "total": total_keys,
                "by_pattern": key_counts,
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "connected": False,
            "error": str(e)
        }
