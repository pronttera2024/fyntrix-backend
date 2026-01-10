from fastapi import APIRouter, Query
from datetime import datetime
from ..services import data
from ..services import global_markets

router = APIRouter(tags=["market"]) 

@router.get("/market/summary")
async def market_summary(region: str = Query("India", description="Market region: India or Global")):
    """
    Get market summary for specified region.
    - India: NIFTY, BANKNIFTY, GOLD, USD/INR
    - Global: S&P500, NASDAQ, LSE (FTSE), Hang Seng
    """
    if region.lower() == "global":
        ind = await global_markets.get_global_indices()
    else:
        ind = await data.indices_summary()

    # Preserve backend-provided quote timestamp. Only fall back to server time
    # when the upstream provider did not return any timestamp.
    if not ind.get("as_of"):
        ind["as_of"] = ind.get("fetched_at") or (datetime.utcnow().isoformat() + "Z")
    ind["region"] = region
    
    # Add cache metadata if present
    if "_cached" in ind:
        ind["data_source"] = "Last Trading Day (Cached)"
        ind["cached_at"] = ind.get("_cached_timestamp", "")
    else:
        ind["data_source"] = "Live"
    
    return ind

@router.get("/flows")
async def flows():
    vals = await data.flows_live()
    return {
        "as_of": datetime.utcnow().isoformat() + "Z",
        **vals,
    }

@router.get("/mini/series")
async def mini_series(symbols: str, points: int = 20, region: str = Query("India", description="Market region")):
    """
    Get mini chart series for symbols.
    Supports both Indian and Global market symbols.
    """
    if region.lower() == "global":
        # Parse symbols and fetch global data
        symbol_list = [s.strip() for s in symbols.split(",")]
        series_data = {}
        for symbol in symbol_list:
            try:
                series_data[symbol] = await global_markets.get_global_mini_series(symbol, points)
            except Exception:
                series_data[symbol] = []
        return {"series": series_data, "region": "Global"}
    else:
        series = await data.mini_series(symbols, points)
        return {"series": series, "region": "India"}
