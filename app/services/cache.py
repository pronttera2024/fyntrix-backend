"""
Persistent cache layer for market data with last trading day support.
Stores data in memory with optional disk persistence for critical data.
"""
from __future__ import annotations
import time
import json
import os
from typing import Any, Dict, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path

from ..core.market_hours import is_cash_market_open_ist

# Cache storage
_MEMORY_CACHE: Dict[str, Tuple[float, Any]] = {}
_PERSISTENT_CACHE_DIR = Path("cache")

# TTL configurations
DEFAULT_TTL = 60.0  # 1 minute for live data
LAST_TRADING_DAY_TTL = 86400.0  # 24 hours for last trading day data
MARKET_HOURS_START = 9  # 9:00 AM IST
MARKET_HOURS_END = 16   # 4:00 PM IST (3:30 PM close + buffer)

def _ensure_cache_dir():
    """Create cache directory if it doesn't exist."""
    _PERSISTENT_CACHE_DIR.mkdir(exist_ok=True)

def _is_market_open(region: str = "India") -> bool:
    """
    Check if market is currently open based on region.
    Simplified check - can be enhanced with holidays, weekends, etc.
    """
    now = datetime.utcnow()
    
    if region == "India":
        return is_cash_market_open_ist()
    
    elif region == "Global":
        # For global markets, consider if any major market is open
        # US markets: NYSE 9:30 AM - 4:00 PM EST (UTC-5)
        # For simplicity, return True during weekdays
        if now.weekday() >= 5:
            return False
        return True
    
    return False

async def get_cached(
    key: str,
    fetcher,
    ttl: float = DEFAULT_TTL,
    persist: bool = False,
    region: str = "India"
) -> Any:
    """
    Get cached value or fetch new data.
    
    Args:
        key: Cache key
        fetcher: Async function to fetch data if not cached
        ttl: Time-to-live in seconds
        persist: If True, save to disk for last trading day persistence
        region: Market region (India/Global) for market hours check
        
    Returns:
        Cached or freshly fetched data
    """
    now = time.time()
    market_open = _is_market_open(region)
    
    # Check memory cache first
    hit = _MEMORY_CACHE.get(key)
    if hit and (now - hit[0] < ttl):
        return hit[1]
    
    # If market closed and we have persistent cache, use it
    if not market_open and persist:
        persistent_data = _load_from_disk(key)
        if persistent_data is not None:
            # Update memory cache with persistent data
            _MEMORY_CACHE[key] = (now, persistent_data)
            return persistent_data
    
    # Fetch fresh data
    try:
        val = await fetcher()
        _MEMORY_CACHE[key] = (now, val)
        
        # Save to disk if persist=True and market is open
        if persist and market_open:
            _save_to_disk(key, val)
        
        return val
    except Exception as e:
        # If fetch fails and we have persistent cache, use it as fallback
        if persist:
            persistent_data = _load_from_disk(key)
            if persistent_data is not None:
                return persistent_data
        raise e

def _save_to_disk(key: str, data: Any):
    """Save data to disk for persistence."""
    try:
        _ensure_cache_dir()
        # Sanitize key for filename
        filename = key.replace(":", "_").replace("/", "_") + ".json"
        filepath = _PERSISTENT_CACHE_DIR / filename
        
        cache_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": data
        }
        
        with open(filepath, "w") as f:
            json.dump(cache_data, f, indent=2)
    except Exception:
        # Silently fail - persistence is optional
        pass

def _load_from_disk(key: str) -> Optional[Any]:
    """Load data from disk."""
    try:
        filename = key.replace(":", "_").replace("/", "_") + ".json"
        filepath = _PERSISTENT_CACHE_DIR / filename
        
        if not filepath.exists():
            return None
        
        with open(filepath, "r") as f:
            cache_data = json.load(f)
        
        # Check if data is not too old (max 7 days)
        timestamp = datetime.fromisoformat(cache_data["timestamp"].replace("Z", "+00:00"))
        age = (datetime.utcnow().replace(tzinfo=timestamp.tzinfo) - timestamp).days
        
        if age > 7:
            return None
        
        # Add metadata to indicate this is cached data
        data = cache_data["data"]
        if isinstance(data, dict):
            data["_cached"] = True
            data["_cached_timestamp"] = cache_data["timestamp"]
        
        return data
    except Exception:
        return None

def clear_memory_cache():
    """Clear in-memory cache."""
    global _MEMORY_CACHE
    _MEMORY_CACHE = {}

def get_cache_info(key: str) -> Optional[Dict[str, Any]]:
    """Get cache metadata for a key."""
    hit = _MEMORY_CACHE.get(key)
    if hit:
        return {
            "key": key,
            "cached_at": datetime.fromtimestamp(hit[0]).isoformat() + "Z",
            "age_seconds": time.time() - hit[0],
            "in_memory": True
        }
    
    # Check disk
    filename = key.replace(":", "_").replace("/", "_") + ".json"
    filepath = _PERSISTENT_CACHE_DIR / filename
    if filepath.exists():
        try:
            with open(filepath, "r") as f:
                cache_data = json.load(f)
            return {
                "key": key,
                "cached_at": cache_data["timestamp"],
                "in_memory": False,
                "on_disk": True
            }
        except Exception:
            pass
    
    return None
