"""
Global Markets data provider.
Fetches data for S&P500, NASDAQ, LSE, Hang Seng using multiple providers.
"""
from __future__ import annotations
import os
from typing import Any, Dict, List
from datetime import datetime
import httpx
from .cache_redis import get_cached

# API Keys
FMP_API_KEY = os.environ.get("FMP_API_KEY", "1oFKhKppawnk4ndt7wvCqNGXKNPllw1n")

# Symbol mappings for different providers
GLOBAL_SYMBOLS = {
    # Yahoo Finance symbols
    "yahoo": {
        "S&P 500": "^GSPC",
        "Nasdaq": "^IXIC",
        "Dow Jones": "^DJI",
        "Nikkei 225": "^N225",
        "Hang Seng": "^HSI",
        "Shanghai": "000001.SS",
        "FTSE 100": "^FTSE",
        "DAX": "^GDAXI",
        "CAC 40": "^FCHI",
        "VIX": "^VIX"
    },
    # FMP symbols
    "fmp": {
        "S&P 500": "^GSPC",
        "Nasdaq": "^IXIC",
        "Dow Jones": "^DJI",
        "Nikkei 225": "^N225",
        "Hang Seng": "^HSI",
        "Shanghai": "000001.SS",
        "FTSE 100": "^FTSE",
        "DAX": "^GDAXI",
        "CAC 40": "^FCHI",
        "VIX": "^VIX"
    }
}

async def fetch_yahoo_quote(symbol: str) -> Dict[str, Any]:
    """Fetch quote from Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d"
    async with httpx.AsyncClient(timeout=10) as cx:
        r = await cx.get(url)
        r.raise_for_status()
        j = r.json()
        
        result = j.get("chart", {}).get("result", [{}])[0]
        meta = result.get("meta", {})
        quote = result.get("indicators", {}).get("quote", [{}])[0]
        
        # Prefer meta-provided live quote fields.
        latest = meta.get("regularMarketPrice")
        previous = (
            meta.get("previousClose")
            or meta.get("chartPreviousClose")
            or meta.get("regularMarketPreviousClose")
        )

        change_pct = 0
        try:
            if isinstance(latest, (int, float)) and isinstance(previous, (int, float)) and previous:
                change_pct = ((float(latest) - float(previous)) / float(previous) * 100)
        except Exception:
            change_pct = 0

        # Timestamp from Yahoo's market time (epoch seconds)
        as_of = ""
        try:
            mt = meta.get("regularMarketTime")
            if isinstance(mt, (int, float)):
                as_of = datetime.utcfromtimestamp(float(mt)).isoformat() + "Z"
        except Exception:
            as_of = ""
        
        return {
            "price": round(latest, 2) if latest else None,
            "chg_pct": round(change_pct, 2),
            "currency": meta.get("currency", "USD"),
            "as_of": as_of,
        }

async def fetch_fmp_quote(symbol: str) -> Dict[str, Any]:
    """Fetch quote from Financial Modeling Prep API."""
    if not FMP_API_KEY:
        raise RuntimeError("FMP_API_KEY not configured")
    
    url = f"https://financialmodelingprep.com/api/v3/quote/{symbol}?apikey={FMP_API_KEY}"
    async with httpx.AsyncClient(timeout=10) as cx:
        r = await cx.get(url)
        r.raise_for_status()
        data = r.json()
        
        if not data or len(data) == 0:
            raise RuntimeError(f"No data for {symbol}")
        
        quote = data[0]
        return {
            "price": round(quote.get("price", 0), 2),
            "chg_pct": round(quote.get("changesPercentage", 0), 2),
            "currency": "USD"
        }

async def get_global_indices() -> Dict[str, Any]:
    """
    Fetch global market indices data.
    Returns data for S&P500, NASDAQ, LSE (FTSE 100), and Hang Seng.
    """
    async def _fetch():
        indices = []
        as_of_candidates: List[str] = []
        
        for name, yahoo_symbol in GLOBAL_SYMBOLS["yahoo"].items():
            try:
                # Try Yahoo first
                data = await fetch_yahoo_quote(yahoo_symbol)
                if data.get("as_of"):
                    as_of_candidates.append(str(data.get("as_of")))
                indices.append({
                    "name": name,
                    "price": data["price"],
                    "chg_pct": data["chg_pct"],
                    "source": "Yahoo Finance",
                    "currency": data.get("currency", "USD")
                })
            except Exception as e:
                # Fallback to FMP if Yahoo fails
                try:
                    fmp_symbol = GLOBAL_SYMBOLS["fmp"].get(name)
                    if fmp_symbol:
                        data = await fetch_fmp_quote(fmp_symbol)
                        indices.append({
                            "name": name,
                            "price": data["price"],
                            "chg_pct": data["chg_pct"],
                            "source": "FMP",
                            "currency": data.get("currency", "USD")
                        })
                except Exception:
                    # Skip if both fail
                    continue
        
        if len(indices) == 0:
            # Fallback with demo data when all APIs fail
            return {
                "indices": [
                    {"name": "S&P 500", "price": 4567.89, "chg_pct": 0.45, "source": "Demo"},
                    {"name": "NASDAQ", "price": 14234.56, "chg_pct": 0.72, "source": "Demo"},
                    {"name": "LSE (FTSE 100)", "price": 7456.32, "chg_pct": 0.18, "source": "Demo"},
                    {"name": "Hang Seng", "price": 18765.43, "chg_pct": -0.23, "source": "Demo"}
                ],
                "source": "Fallback",
                "region": "Global",
                "as_of": "",
                "fetched_at": datetime.utcnow().isoformat() + "Z",
            }

        # Choose the freshest as_of from candidates (string compare safe for ISO Z)
        best_as_of = max(as_of_candidates) if as_of_candidates else ""
        
        return {
            "indices": indices,
            "source": "Multiple" if len(indices) > 1 else (indices[0].get("source", "Yahoo") if indices else "Yahoo"),
            "region": "Global",
            "as_of": best_as_of,
            "fetched_at": datetime.utcnow().isoformat() + "Z",
        }
    
    return await get_cached(
        "global_indices_summary",
        _fetch,
        ttl=30.0,
        persist=True,
        region="Global"
    )

async def get_global_mini_series(symbol: str, points: int = 20) -> List[float]:
    """
    Fetch mini chart series for a global index with fallback mock data.
    Supports both display names and Yahoo symbols.
    """
    # Realistic mock data for global indices reflecting current market trends
    # Include both display names and Yahoo symbols as keys
    mock_data = {
        "^GSPC": [4450, 4460, 4455, 4470, 4480, 4475, 4490, 4500, 4495, 4510, 4520, 4515, 4530, 4540, 4545, 4555, 4560, 4565, 4567, 4567.89],
        "S&P 500": [4450, 4460, 4455, 4470, 4480, 4475, 4490, 4500, 4495, 4510, 4520, 4515, 4530, 4540, 4545, 4555, 4560, 4565, 4567, 4567.89],
        "^IXIC": [13900, 13920, 13910, 13950, 13970, 13960, 13990, 14010, 14000, 14030, 14050, 14040, 14070, 14100, 14110, 14150, 14180, 14200, 14220, 14234.56],
        "NASDAQ": [13900, 13920, 13910, 13950, 13970, 13960, 13990, 14010, 14000, 14030, 14050, 14040, 14070, 14100, 14110, 14150, 14180, 14200, 14220, 14234.56],
        "^FTSE": [7400, 7410, 7405, 7420, 7430, 7425, 7435, 7445, 7440, 7450, 7460, 7455, 7465, 7475, 7470, 7480, 7490, 7485, 7492, 7496.32],
        "FTSE 100": [7400, 7410, 7405, 7420, 7430, 7425, 7435, 7445, 7440, 7450, 7460, 7455, 7465, 7475, 7470, 7480, 7490, 7485, 7492, 7496.32],
        "LSE (FTSE 100)": [7400, 7410, 7405, 7420, 7430, 7425, 7435, 7445, 7440, 7450, 7460, 7455, 7465, 7475, 7470, 7480, 7490, 7485, 7492, 7496.32],
        "^HSI": [19200, 19150, 19100, 19050, 19020, 18980, 18950, 18920, 18890, 18860, 18840, 18820, 18800, 18780, 18760, 18750, 18740, 18730, 18720, 18710],
        "Hang Seng": [19200, 19150, 19100, 19050, 19020, 18980, 18950, 18920, 18890, 18860, 18840, 18820, 18800, 18780, 18760, 18750, 18740, 18730, 18720, 18710]
    }
    
    async def _fetch():
        # Map display name to Yahoo symbol
        yahoo_symbol = None
        for name, ysym in GLOBAL_SYMBOLS["yahoo"].items():
            if name.lower() in symbol.lower() or symbol == ysym:
                yahoo_symbol = ysym
                break
        
        if not yahoo_symbol:
            yahoo_symbol = symbol
        
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?interval=30m&range=5d"
            async with httpx.AsyncClient(timeout=10) as cx:
                r = await cx.get(url)
                r.raise_for_status()
                j = r.json()
                
                closes = (j.get("chart", {}).get("result", [{}])[0]
                         .get("indicators", {}).get("quote", [{}])[0].get("close", []))
                series = [float(x) for x in closes if isinstance(x, (int, float))]
                
                if series and len(series) > 0:
                    # Return last N points if Yahoo succeeds
                    return series[-points:] if len(series) > points else series
                else:
                    # Use mock data if Yahoo returns empty
                    print(f"Using mock sparkline data for global symbol {yahoo_symbol}")
                    return mock_data.get(yahoo_symbol, [])[-points:]
        except Exception as e:
            print(f"Sparkline fetch failed for global {yahoo_symbol}: {e}, using mock data")
            # Return mock data if fetch fails
            return mock_data.get(yahoo_symbol or symbol, [])[-points:]
    
    return await get_cached(
        f"global_mini_series:{symbol}:{points}",
        _fetch,
        ttl=120.0,
        persist=False,
        region="Global"
    )
