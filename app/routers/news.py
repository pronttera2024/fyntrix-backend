from fastapi import APIRouter, Query
from datetime import datetime
from ..services.news_aggregator import aggregate_news, get_symbol_news

router = APIRouter(tags=["news"]) 

@router.get("/news")
async def news(
    category: str = Query("general", description="News category: general, corporate, earnings"),
    limit: int = Query(20, description="Maximum number of news items"),
    symbol: str | None = Query(None, description="Filter by stock symbol")
):
    """
    Get aggregated news from multiple sources.
    NSE announcements are prioritized first.
    
    Sources:
    - NSE (corporate announcements)
    - FMP (Financial Modeling Prep)
    - Yahoo Finance
    - NDTV Profit
    - Bloomberg (if available)
    """
    if symbol:
        items = await get_symbol_news(symbol, limit)
    else:
        items = await aggregate_news(category, limit)
    
    return {
        "category": category,
        "symbol": symbol,
        "items": items,
        "count": len(items),
        "as_of": datetime.utcnow().isoformat() + "Z"
    }
