from __future__ import annotations
import os
from typing import Any, Dict, List
from datetime import datetime, timedelta
import asyncio
import httpx
from .cache import get_cached
from ..providers import get_data_provider

Y_SYMBOLS = {
    "NIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "GOLD": "GC=F",
    "USDINR": "USDINR=X",
}

FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")
ALPHA_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY", "")

# Cache helper moved to cache.py module

# ---------- Providers ----------
async def yahoo_chart_series(symbol: str, interval: str = "30m", range_: str = "5d") -> List[float]:
    async def _fetch():
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={range_}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://finance.yahoo.com/",
        }
        async with httpx.AsyncClient(timeout=10, headers=headers, follow_redirects=True) as cx:
            r = await cx.get(url)
            r.raise_for_status()
            j = r.json() or {}
            result = (j.get("chart", {}).get("result") or [])
            if not result:
                return []
            node = result[0] or {}
            closes = (node.get("indicators", {}).get("quote", [{}])[0].get("close") or [])
            series = [float(x) for x in closes if isinstance(x, (int, float))]
            if series:
                return series[-40:]
            meta = node.get("meta") or {}
            last = (
                meta.get("regularMarketPrice")
                or meta.get("previousClose")
                or meta.get("chartPreviousClose")
            )
            if last is None:
                return []
            return [float(last)] * 40
    return await get_cached(f"ychart:{symbol}:{interval}:{range_}", _fetch, ttl=120.0, persist=False)


async def yahoo_chart_quote(symbol: str, interval: str = "1m", range_: str = "1d") -> Dict[str, Any]:
    """Fetch a near-real-time quote using the Yahoo chart endpoint.

    Returns:
      {
        "price": float|None,
        "chg_pct": float|None,
        "as_of": "<iso>Z"|"",
        "source": "Yahoo"
      }
    """

    async def _fetch():
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={range_}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://finance.yahoo.com/",
        }
        async with httpx.AsyncClient(timeout=10, headers=headers, follow_redirects=True) as cx:
            r = await cx.get(url)
            r.raise_for_status()
            j = r.json() or {}
            result = (j.get("chart", {}).get("result") or [])
            if not result:
                return {"price": None, "chg_pct": None, "as_of": "", "source": "Yahoo"}

            node = result[0] or {}
            meta = node.get("meta") or {}

            price = meta.get("regularMarketPrice")
            prev_close = (
                meta.get("previousClose")
                or meta.get("chartPreviousClose")
                or meta.get("regularMarketPreviousClose")
            )
            market_time = meta.get("regularMarketTime")

            as_of = ""
            try:
                if isinstance(market_time, (int, float)):
                    as_of = datetime.utcfromtimestamp(float(market_time)).isoformat() + "Z"
            except Exception:
                as_of = ""

            chg = None
            try:
                if isinstance(price, (int, float)) and isinstance(prev_close, (int, float)) and prev_close:
                    chg = ((float(price) - float(prev_close)) / float(prev_close)) * 100.0
            except Exception:
                chg = None

            return {
                "price": float(price) if isinstance(price, (int, float)) else None,
                "chg_pct": round(float(chg), 2) if isinstance(chg, (int, float)) else None,
                "as_of": as_of,
                "source": "Yahoo",
            }

    # Tight TTL: this is used for "live" dashboard display.
    return await get_cached(f"yquote:{symbol}:{interval}:{range_}", _fetch, ttl=30.0, persist=False)

async def nse_session_headers() -> dict:
    """Return headers for NSE requests"""
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://www.nseindia.com/",
        "Accept": "application/json, text/plain, */*",
    }

async def provider_nse_indices() -> Dict[str, Any]:
    """Fetch indices from NSE API"""
    headers = await nse_session_headers()
    async with httpx.AsyncClient(timeout=15, headers=headers) as cx:
        # Warm up cookies
        try:
            await cx.get("https://www.nseindia.com/")
        except Exception:
            pass
        
        # Get indices
        r = await cx.get("https://www.nseindia.com/api/allIndices")
        r.raise_for_status()
        j = r.json()
        data = j.get("data", [])
        
        def pick(key: str, match: str):
            for it in data:
                index_name = str(it.get("index", "")).lower()
                if match.lower() in index_name:
                    price = it.get("last", None)
                    chg_pct = it.get("percentChange", None)
                    return {"name": it.get("index", key), "price": price, "chg_pct": chg_pct, "source": "NSE"}
            return None
        
        n50 = pick("NIFTY 50", "NIFTY 50")
        nbk = pick("NIFTY BANK", "NIFTY BANK")
        
        # Return valid indices
        indices = [x for x in [n50, nbk] if x]
        if not indices:
            raise RuntimeError("No NSE indices found")
        
        return {"indices": indices, "source": "NSE"}

async def provider_finnhub_indices() -> Dict[str, Any]:
    if not FINNHUB_KEY:
        raise RuntimeError("FINNHUB_API_KEY missing")
    # Finnhub symbols for indices may require premium. Skip detailed mapping and raise to fallback when missing.
    raise RuntimeError("Finnhub mapping not configured")

async def provider_alpha_indices() -> Dict[str, Any]:
    if not ALPHA_KEY:
        raise RuntimeError("ALPHA_VANTAGE_API_KEY missing")
    # Placeholder: not implemented yet
    raise RuntimeError("Alpha mapping not configured")

# ---------- High-level indices with fallbacks ----------
async def indices_summary() -> Dict[str, Any]:
    """
    Get market indices with the following priority:
    1. PRIMARY: Zerodha (fast, granular, real-time)
    2. FALLBACK: Yahoo Finance
    3. LAST RESORT: NSE direct API
    """
    def _parse_ts(raw: Any) -> datetime | None:
        try:
            if isinstance(raw, datetime):
                return raw
            if isinstance(raw, (int, float)):
                return datetime.utcfromtimestamp(float(raw))
            if isinstance(raw, str) and raw:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return None
        return None

    # PRIMARY: Try Unified Provider (Zerodha first, auto-falls to Yahoo)
    try:
        provider = get_data_provider()
        data_source = provider.get_data_source()
        print(f"✓ PRIMARY SOURCE: {data_source} for indices data")
        
        indices_data = provider.get_indices_quote()
        
        if indices_data and len(indices_data) > 0:
            inds = []
            ts_candidates: List[datetime] = []
            for name, quote in indices_data.items():
                qt = _parse_ts(quote.get('timestamp') if isinstance(quote, dict) else None)
                if qt is not None:
                    ts_candidates.append(qt)
                inds.append({
                    "name": name,
                    "price": quote.get('price'),
                    "chg_pct": quote.get('change_percent'),
                    "source": data_source
                })

            # Ensure GOLD and USD/INR are present using Yahoo FX/commodity data
            try:
                have_gold = any((i.get("name") or "").upper().startswith("GOLD") for i in inds)
                if not have_gold:
                    gq = await yahoo_chart_quote(Y_SYMBOLS["GOLD"], interval="1m", range_="1d")
                    price = gq.get("price")
                    chg = gq.get("chg_pct")
                    gt = _parse_ts(gq.get("as_of"))
                    if gt is not None:
                        ts_candidates.append(gt)
                    inds.append({
                        "name": "GOLD",
                        "price": price,
                        "chg_pct": chg,
                        "source": "Yahoo",
                    })

                have_fx = any(
                    "USD/INR" in str(i.get("name") or "").upper()
                    or "USDINR" in str(i.get("name") or "").upper()
                    for i in inds
                )
                if not have_fx:
                    fxq = await yahoo_chart_quote(Y_SYMBOLS["USDINR"], interval="1m", range_="1d")
                    price = fxq.get("price")
                    chg = fxq.get("chg_pct")
                    ft = _parse_ts(fxq.get("as_of"))
                    if ft is not None:
                        ts_candidates.append(ft)
                    inds.append({
                        "name": "USD/INR",
                        "price": price,
                        "chg_pct": chg,
                        "source": "Yahoo",
                    })
            except Exception as e:
                print(f"Failed to enrich indices with GOLD/USDINR: {e}")
                names = [str(i.get("name") or "").upper() for i in inds]
                if "GOLD" not in names:
                    inds.append({"name": "GOLD", "price": None, "chg_pct": None, "source": "Yahoo"})
                if "USD/INR" not in names and "USDINR" not in names:
                    inds.append({"name": "USD/INR", "price": None, "chg_pct": None, "source": "Yahoo"})
            
            print(f"✓ Successfully fetched {len(inds)} indices from {data_source}")

            as_of_dt = max(ts_candidates) if ts_candidates else None
            as_of = as_of_dt.isoformat() + "Z" if as_of_dt else ""
            return {
                "indices": inds,
                "source": data_source,
                "as_of": as_of,
                "fetched_at": datetime.utcnow().isoformat() + "Z",
            }
        else:
            print(f"⚠️  {data_source} returned no data, trying fallback")
    except Exception as e:
        print(f"⚠️  Unified provider error: {e}, trying fallback")
    
    # LAST RESORT: NSE Direct API (slower, limited)
    print("→ Falling back to NSE Direct API")
    try:
        base = await provider_nse_indices()
        inds = base.get("indices", [])
        
        # Add GOLD via Yahoo
        try:
            g_series = await yahoo_chart_series(Y_SYMBOLS["GOLD"], interval="60m", range_="5d")
            price = g_series[-1] if g_series else None
            chg = None
            if len(g_series) >= 2 and g_series[-2]:
                prev = g_series[-2]
                chg = ((g_series[-1] - prev) / prev * 100.0) if prev else None
            inds.append({"name": "GOLD", "price": price, "chg_pct": round(chg, 2) if chg is not None else None, "source": "Yahoo"})
        except Exception as e:
            print(f"Gold fetch failed: {e}")
            inds.append({"name": "GOLD", "price": None, "chg_pct": None, "source": "N/A"})

        # Add USD/INR via Yahoo
        try:
            fx_series = await yahoo_chart_series(Y_SYMBOLS["USDINR"], interval="60m", range_="5d")
            price = fx_series[-1] if fx_series else None
            chg = None
            if len(fx_series) >= 2 and fx_series[-2]:
                prev = fx_series[-2]
                chg = ((fx_series[-1] - prev) / prev * 100.0) if prev else None
            inds.append({"name": "USD/INR", "price": price, "chg_pct": round(chg, 2) if chg is not None else None, "source": "Yahoo"})
        except Exception as e:
            print(f"USD/INR fetch failed: {e}")
            inds.append({"name": "USD/INR", "price": None, "chg_pct": None, "source": "N/A"})
        
        return {"indices": inds, "source": base.get("source", "NSE")}
    except Exception as e:
        print(f"NSE indices fetch failed: {e}")
        pass
    # Yahoo fallback
    try:
        async def _one(name: str, ys: str):
            s = await yahoo_chart_series(ys, interval="60m", range_="5d")
            price = s[-1] if s else None
            chg = None
            if len(s) >= 2 and s[-2] and s[-1]:
                prev = s[-2]
                chg = ((s[-1] - prev) / prev) * 100.0 if prev else None
            return {"name": name, "price": price, "chg_pct": round(chg, 2) if chg is not None else None, "source": "Yahoo"}

        n50 = await _one("NIFTY 50", Y_SYMBOLS["NIFTY"])
        nbk = await _one("NIFTY BANK", Y_SYMBOLS["BANKNIFTY"])
        gold = await _one("GOLD", Y_SYMBOLS["GOLD"])
        usdinr = await _one("USD/INR", Y_SYMBOLS["USDINR"])
        return {"indices": [n50, nbk, gold, usdinr], "source": "Yahoo"}
    except Exception:
        # Final fallback with mock data (for testing/demo when all APIs fail)
        return {
            "indices": [
                {"name": "NIFTY 50", "price": 19450.75, "chg_pct": 0.35, "source": "Demo"},
                {"name": "NIFTY BANK", "price": 44350.25, "chg_pct": 0.52, "source": "Demo"},
                {"name": "GOLD", "price": 62500.00, "chg_pct": -0.15, "source": "Demo"}
            ],
            "source": "Fallback"
        }

async def mini_series(symbols_csv: str, points: int = 20) -> Dict[str, List[float]]:
    """Get mini chart series for symbols (sparklines)"""
    # Realistic mock data with gradual trends when Yahoo fails
    mock_data = {
        "NIFTY": [25200, 25180, 25220, 25250, 25240, 25280, 25300, 25290, 25320, 25340, 25360, 25380, 25400, 25420, 25450, 25480, 25500, 25530, 25560, 25580],
        "BANKNIFTY": [57500, 57480, 57520, 57560, 57540, 57580, 57600, 57590, 57620, 57650, 57680, 57700, 57730, 57760, 57800, 57840, 57880, 57920, 57960, 58000],
        "GOLD": [62400, 62420, 62410, 62450, 62460, 62440, 62470, 62490, 62480, 62500, 62520, 62510, 62540, 62560, 62550, 62570, 62590, 62600, 62610, 62620],
        "USDINR": [83.10, 83.12, 83.11, 83.15, 83.17, 83.14, 83.18, 83.20, 83.19, 83.22, 83.24, 83.23, 83.26, 83.28, 83.27, 83.30, 83.32, 83.31, 83.34, 83.35]
    }
    
    out: Dict[str, List[float]] = {}
    provider = get_data_provider()
    use_zerodha_for_indices = provider.get_data_source() == "Zerodha"

    for raw in symbols_csv.split(','):
        k = raw.strip().upper()
        if not k:
            continue

        # Prefer Zerodha historical data for key indices when available
        if use_zerodha_for_indices and k in ("NIFTY", "BANKNIFTY"):
            try:
                index_symbol = "NIFTY 50" if k == "NIFTY" else "NIFTY BANK"
                to_date = datetime.utcnow()
                from_date = to_date - timedelta(days=5)

                def _fetch_hist():
                    return provider.get_historical_data(
                        index_symbol,
                        from_date,
                        to_date,
                        interval="30m",
                        use_cache=True,
                    )

                df = await asyncio.to_thread(_fetch_hist)
                if df is not None and not df.empty:
                    closes = df["close"].tolist()
                    out[k] = closes[-points:] if len(closes) > points else closes
                    continue
            except Exception as e:
                print(f"Zerodha mini_series failed for {k}: {e}")

        ys = Y_SYMBOLS.get(k, k)
        try:
            s = await yahoo_chart_series(ys, interval="60m", range_="5d")
            if s and len(s) > 0:
                out[k] = s[-points:]
            else:
                # For GOLD and USDINR, avoid stale mock data – only use live Yahoo series
                if k in ("GOLD", "USDINR"):
                    print(f"Yahoo sparkline empty for {k}, skipping mock data to avoid stale FX/commodity values")
                    out[k] = []
                else:
                    # Use mock data if Yahoo returns empty for other symbols
                    print(f"Using mock sparkline data for {k}")
                    out[k] = mock_data.get(k, [])[-points:]
        except Exception as e:
            print(f"Sparkline fetch failed for {k}: {e}")
            # For GOLD and USDINR, do not fall back to demo data
            if k in ("GOLD", "USDINR"):
                out[k] = []
            else:
                # Return mock data if fetch fails for other symbols
                print(f"Using mock sparkline data for {k} after failure")
                out[k] = mock_data.get(k, [])[-points:]
    return out

# ---------- Flows (FII/DII) ----------
async def nse_flows() -> Dict[str, float]:
    """Fetch FII/DII flows from NSE"""
    headers = await nse_session_headers()
    async with httpx.AsyncClient(timeout=15, headers=headers) as cx:
        # Warm up
        try:
            await cx.get("https://www.nseindia.com/")
        except Exception:
            pass
        
        r = await cx.get("https://www.nseindia.com/api/fiidiiTradeReact")
        r.raise_for_status()
        j = r.json() or {}
        # API returns arrays; pick latest row
        data = j.get("data") or j.get("FiiDii") or []
        latest = data[-1] if data else {}
        fii = latest.get("FII_net") or latest.get("FII"); dii = latest.get("DII_net") or latest.get("DII")
        def parse_num(x):
            try:
                return float(str(x).replace(",", ""))
            except Exception:
                return None
        return {"fii_cr": parse_num(fii), "dii_cr": parse_num(dii)}

async def flows_fallback() -> Dict[str, float]:
    # placeholder fallbacks (could add other providers)
    return {"fii_cr": 0.0, "dii_cr": 0.0}

async def flows_live() -> Dict[str, float]:
    try:
        return await get_cached("flows:nse", nse_flows, ttl=120.0, persist=False)
    except Exception:
        return await flows_fallback()

# ---------- News ----------
async def news_fallback(category: str = "general", limit: int = 8, symbol: str | None = None) -> Dict[str, Any]:
    items = [
        {"title": "Markets edge higher on positive global cues", "source": "NSE"},
        {"title": "Banking stocks mixed amid rate uncertainty", "source": "Yahoo"},
        {"title": "Gold steady as dollar softens", "source": "AlphaV"},
        {"title": "FII flows turn positive; DII book profits", "source": "Finnhub"},
    ][:limit]
    return {"category": category, "symbol": symbol, "items": items, "source": "Fallback"}
