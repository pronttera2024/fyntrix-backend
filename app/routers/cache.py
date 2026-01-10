"""
Cache Management API Router
Handles historical data cache operations
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional
from datetime import datetime
from ..services.historical_cache import get_historical_cache
from ..services.redis_client import get_json

router = APIRouter(tags=["cache"])


@router.get("/cache/stats")
async def get_cache_stats() -> Dict[str, Any]:
    """
    Get cache statistics
    
    Returns:
        Cache statistics including hits, misses, hit rate, size
    """
    cache = get_historical_cache()
    stats = cache.get_stats()
    
    return {
        "status": "success",
        "cache_stats": stats
    }


@router.get("/cache/info")
async def get_cache_info(limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
    """
    Get detailed information about cached entries
    
    Args:
        limit: Maximum number of entries to return
        
    Returns:
        List of cached entries with metadata
    """
    cache = get_historical_cache()
    info = cache.get_cache_info()
    
    return {
        "status": "success",
        "total_entries": len(info),
        "entries": info[:limit]
    }


@router.post("/cache/invalidate")
async def invalidate_cache(
    symbol: Optional[str] = Query(None, description="Specific symbol to invalidate"),
    interval: Optional[str] = Query(None, description="Specific interval to invalidate"),
    older_than_hours: Optional[int] = Query(None, ge=1, description="Invalidate entries older than X hours")
) -> Dict[str, Any]:
    """
    Invalidate cache entries based on filters
    
    Args:
        symbol: Specific symbol to invalidate (None = all)
        interval: Specific interval to invalidate (None = all)
        older_than_hours: Invalidate entries older than X hours
        
    Returns:
        Number of entries invalidated
    """
    cache = get_historical_cache()
    count = cache.invalidate(
        symbol=symbol,
        interval=interval,
        older_than_hours=older_than_hours
    )
    
    return {
        "status": "success",
        "message": f"Invalidated {count} cache entries",
        "invalidated_count": count
    }


@router.post("/cache/clear")
async def clear_cache() -> Dict[str, Any]:
    """
    Clear all cache entries
    
    WARNING: This will delete all cached historical data
    
    Returns:
        Number of entries cleared
    """
    cache = get_historical_cache()
    count = cache.clear_all()
    
    return {
        "status": "success",
        "message": f"Cleared all cache ({count} entries)",
        "cleared_count": count
    }


@router.get("/cache/health")
async def cache_health() -> Dict[str, Any]:
    """
    Get cache health status
    
    Returns:
        Health status with recommendations
    """
    cache = get_historical_cache()
    stats = cache.get_stats()
    
    # Calculate health metrics
    hit_rate = stats.get('hit_rate', 0)
    total_entries = stats.get('total_entries', 0)
    size_mb = stats.get('total_size_mb', 0)
    
    # Determine health status
    if hit_rate >= 70:
        health = "excellent"
    elif hit_rate >= 50:
        health = "good"
    elif hit_rate >= 30:
        health = "fair"
    else:
        health = "poor"
    
    # Generate recommendations
    recommendations = []
    
    if hit_rate < 30:
        recommendations.append("Low hit rate. Consider increasing cache TTL.")
    
    if size_mb > 100:
        recommendations.append("Cache size is large. Consider running cleanup.")
    
    if total_entries == 0:
        recommendations.append("Cache is empty. Data will be fetched from sources.")
    
    if total_entries > 1000:
        recommendations.append("Too many cache entries. Consider invalidating old data.")
    
    if not recommendations:
        recommendations.append("Cache is performing well!")
    
    return {
        "status": "success",
        "health": health,
        "hit_rate": hit_rate,
        "total_entries": total_entries,
        "size_mb": size_mb,
        "recommendations": recommendations
    }


@router.get("/cache/redis/top-picks")
async def get_redis_top_picks(
    universe: str = Query("nifty50", description="Universe key used in Redis: e.g. nifty50, banknifty"),
    mode: str = Query("Intraday", description="Trading mode: Scalping, Intraday, Swing, Options, Futures"),
) -> Dict[str, Any]:
    """Return the latest scheduled top picks payload directly from Redis.

    This reads the value written by TopPicksScheduler under key
    ``top_picks:{universe.lower()}:{mode.lower()}``.
    """
    key = f"top_picks:{universe.lower()}:{mode.lower()}"
    data = get_json(key)

    if data is None:
        return {
            "status": "success",
            "found": False,
            "key": key,
            "universe": universe,
            "mode": mode,
            "message": "No Redis data found for this universe/mode or Redis is not configured.",
        }

    return {
        "status": "success",
        "found": True,
        "key": key,
        "universe": data.get("universe", universe),
        "mode": data.get("mode", mode),
        "data": data,
    }


@router.get("/cache/redis/top-picks-heatmap")
async def get_redis_top_picks_heatmap(
    universe: str = Query("nifty50", description="Universe key used in Redis: e.g. nifty50, banknifty"),
    mode: str = Query("Intraday", description="Trading mode: Scalping, Intraday, Swing, Options, Futures"),
    symbols: Optional[str] = Query(
        None,
        description=(
            "Optional comma-separated list of symbols (e.g. 'TITAN,AXISBANK,RELIANCE'). "
            "If omitted, returns all picks for the universe."
        ),
    ),
) -> Dict[str, Any]:
    """Return raw top pick objects as used by the Market Heat Map.

    This is a diagnostic endpoint so you can inspect fields like
    ``last_price``, ``prev_close`` and ``intraday_change_pct`` populated
    by the realtime price enrichment.
    """
    key = f"top_picks:{universe.lower()}:{mode.lower()}"
    data = get_json(key)

    if data is None:
        return {
            "status": "success",
            "found": False,
            "key": key,
            "universe": universe,
            "mode": mode,
            "message": "No Redis data found for this universe/mode or Redis is not configured.",
        }

    items = data.get("items") or []

    # Optional symbol filter for focused debugging (e.g. TITAN,AXISBANK,RELIANCE)
    if symbols:
        wanted = {s.strip().upper() for s in symbols.split(",") if s.strip()}
        items = [p for p in items if str(p.get("symbol", "")).upper() in wanted]

    return {
        "status": "success",
        "found": True,
        "key": key,
        "universe": data.get("universe", universe),
        "mode": data.get("mode", mode),
        "as_of": data.get("as_of"),
        "count": len(items),
        "symbols": sorted({str(p.get("symbol", "")).upper() for p in items if p.get("symbol")}),
        "items": items,
    }


@router.get("/cache/redis/portfolio-monitor")
async def get_redis_portfolio_monitor(
    scope: str = Query("positions", description="Scope: positions or watchlist"),
) -> Dict[str, Any]:
    """Return portfolio monitor data from Redis.

    Keys used by PortfolioMonitorScheduler (and future watchlist worker):
    - portfolio:monitor:positions:last
    - portfolio:monitor:watchlist:last
    """
    if scope == "positions":
        key = "portfolio:monitor:positions:last"
    elif scope == "watchlist":
        key = "portfolio:monitor:watchlist:last"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported scope: {scope}")

    data = get_json(key)

    if data is None:
        return {
            "status": "success",
            "found": False,
            "key": key,
            "message": "No Redis data found for this portfolio scope or Redis is not configured.",
        }

    return {
        "status": "success",
        "found": True,
        "key": key,
        "data": data,
    }


@router.get("/dashboard/overview")
async def dashboard_overview() -> Dict[str, Any]:
    intraday = get_json("dashboard:overview:intraday")
    performance = get_json("dashboard:overview:performance:7d")

    return {
        "status": "success",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "intraday": {
            "found": intraday is not None,
            "data": intraday,
        },
        "performance_7d": {
            "found": performance is not None,
            "data": performance,
        },
    }


@router.get("/cache/redis/scalping-monitor-last")
async def get_redis_scalping_monitor_last() -> Dict[str, Any]:
    """Return the last scalping monitor summary from Redis.

    This reads the value written by the scalping monitor scheduler under key
    ``scalping:monitor:last``.
    """
    key = "scalping:monitor:last"
    data = get_json(key)

    if data is None:
        return {
            "status": "success",
            "found": False,
            "key": key,
            "message": "No Redis data found for scalping monitor or Redis is not configured.",
        }

    return {
        "status": "success",
        "found": True,
        "key": key,
        "data": data,
    }


@router.get("/cache/redis/dashboard-overview")
async def get_redis_dashboard_overview(
    scope: str = Query("intraday", description="Scope: intraday or performance_7d"),
) -> Dict[str, Any]:
    """Return dashboard overview data from Redis.

    Keys used by DashboardScheduler:
    - dashboard:overview:intraday
    - dashboard:overview:performance:7d
    """
    if scope == "intraday":
        key = "dashboard:overview:intraday"
    elif scope == "performance_7d":
        key = "dashboard:overview:performance:7d"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported scope: {scope}")

    data = get_json(key)

    if data is None:
        return {
            "status": "success",
            "found": False,
            "key": key,
            "message": "No Redis data found for this dashboard scope or Redis is not configured.",
        }

    return {
        "status": "success",
        "found": True,
        "key": key,
        "data": data,
    }
