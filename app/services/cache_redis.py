"""
Redis-based cache layer replacing the in-memory/file-based cache
Maintains backward compatibility with existing cache.py API
"""
from __future__ import annotations
import time
import json
from typing import Any, Dict, Optional
from datetime import datetime, timedelta

from ..core.market_hours import is_cash_market_open_ist
from .redis_cache import general_cache

# TTL configurations
DEFAULT_TTL = 60  # 1 minute for live data
LAST_TRADING_DAY_TTL = 86400  # 24 hours for last trading day data
MARKET_HOURS_START = 9  # 9:00 AM IST
MARKET_HOURS_END = 16   # 4:00 PM IST (3:30 PM close + buffer)


def _is_market_open(region: str = "India") -> bool:
    """
    Check if market is currently open based on region.
    """
    now = datetime.utcnow()
    
    if region == "India":
        return is_cash_market_open_ist()
    
    elif region == "Global":
        # For global markets, consider if any major market is open
        if now.weekday() >= 5:
            return False
        return True
    
    return False


async def get_cached(
    key: str,
    fetcher,
    ttl: int = DEFAULT_TTL,
    persist: bool = False,
    region: str = "India"
) -> Any:
    """
    Get cached value or fetch new data using Redis.
    
    Args:
        key: Cache key
        fetcher: Async function to fetch data if not cached
        ttl: Time-to-live in seconds
        persist: If True, use longer TTL for last trading day persistence
        region: Market region (India/Global) for market hours check
        
    Returns:
        Cached or freshly fetched data
    """
    market_open = _is_market_open(region)
    
    # Check Redis cache first
    cached_data = general_cache.get(key)
    if cached_data is not None:
        return cached_data
    
    # If market closed and persist=True, try with longer TTL key
    if not market_open and persist:
        persist_key = f"{key}:persist"
        persistent_data = general_cache.get(persist_key)
        if persistent_data is not None:
            return persistent_data
    
    # Fetch fresh data
    try:
        val = await fetcher()
        
        # Determine TTL based on market status and persist flag
        cache_ttl = ttl
        if persist and market_open:
            # Save both regular and persistent versions
            general_cache.set(key, val, ttl=ttl)
            general_cache.set(f"{key}:persist", val, ttl=LAST_TRADING_DAY_TTL)
        else:
            general_cache.set(key, val, ttl=cache_ttl)
        
        return val
    except Exception as e:
        # If fetch fails and we have persistent cache, use it as fallback
        if persist:
            persist_key = f"{key}:persist"
            persistent_data = general_cache.get(persist_key)
            if persistent_data is not None:
                return persistent_data
        raise e


def clear_memory_cache():
    """Clear Redis cache (use with caution)."""
    # This would clear all keys - implement pattern-based clearing if needed
    pass


def get_cache_info(key: str) -> Optional[Dict[str, Any]]:
    """Get cache metadata for a key."""
    if general_cache.exists(key):
        ttl = general_cache.ttl(key)
        return {
            "key": key,
            "exists": True,
            "ttl_seconds": ttl,
            "in_redis": True
        }
    
    return None


def set_cached(key: str, value: Any, ttl: int = DEFAULT_TTL) -> bool:
    """
    Directly set a cached value.
    
    Args:
        key: Cache key
        value: Value to cache
        ttl: Time-to-live in seconds
        
    Returns:
        True if successful
    """
    return general_cache.set(key, value, ttl=ttl)


def get_cached_sync(key: str, default: Any = None) -> Any:
    """
    Synchronously get a cached value.
    
    Args:
        key: Cache key
        default: Default value if not found
        
    Returns:
        Cached value or default
    """
    return general_cache.get(key, default=default)


def delete_cached(key: str) -> bool:
    """
    Delete a cached value.
    
    Args:
        key: Cache key
        
    Returns:
        True if deleted
    """
    return general_cache.delete(key)
