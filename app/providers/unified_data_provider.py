"""
Unified Data Provider
Uses Zerodha for real-time data with Yahoo Finance as fallback
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, timezone
import httpx
import yfinance as yf
import pandas as pd

from .zerodha_provider import get_zerodha_provider
from ..services.historical_cache import get_historical_cache
from ..core.market_hours import now_ist, now_utc, to_iso_utc

logger = logging.getLogger(__name__)

class UnifiedDataProvider:
    """
    Unified data provider that uses Zerodha first, then falls back to Yahoo Finance
    WITH intelligent caching for historical data
    """
    
    def __init__(self):
        self.zerodha = get_zerodha_provider()
        # Start with whatever the provider reports, but allow upgrading to
        # Zerodha dynamically at runtime once authentication is available.
        self.use_zerodha = self.zerodha.is_authenticated()
        self.cache = get_historical_cache()
        
        # Re-check Zerodha authentication at call time so that if the
        # access token is set AFTER this provider is constructed, we
        # still start using Zerodha without needing an app restart.
        if not self.use_zerodha and self.zerodha.is_authenticated():
            self.use_zerodha = True
            logger.info("✓ UnifiedDataProvider: Zerodha authenticated at runtime, switching to Zerodha as primary source")

        if self.use_zerodha:
            logger.info("✓ Using Zerodha for real-time data")
        else:
            logger.info("⚠️  Using Yahoo Finance (Zerodha not authenticated)")
        
        logger.info("✓ Historical data caching enabled")
    
    def get_quote(self, symbols: List[str]) -> Dict[str, Any]:
        """
        Get real-time quotes for symbols
        Tries Zerodha first, falls back to Yahoo Finance
        """
        # If Zerodha was previously disabled due to an auth failure, allow it to
        # be re-enabled automatically once a new token is set.
        try:
            if not self.use_zerodha and self.zerodha.is_authenticated():
                self.use_zerodha = True
                logger.info("✓ UnifiedDataProvider: Zerodha authenticated at runtime, enabling Zerodha quotes")
        except Exception:
            pass

        def _looks_like_nfo_symbol(sym: Any) -> bool:
            try:
                s = str(sym or "").upper().strip()
            except Exception:
                return False
            if not s:
                return False
            if not any(c.isdigit() for c in s):
                return False
            if s.endswith("CE") or s.endswith("PE") or s.endswith("FUT"):
                return True
            return False

        nfo_symbols: List[str] = []
        nse_symbols: List[str] = []
        for sym in symbols or []:
            if _looks_like_nfo_symbol(sym):
                nfo_symbols.append(str(sym))
            else:
                nse_symbols.append(str(sym))

        # Try Zerodha first
        if self.use_zerodha:
            try:
                merged: Dict[str, Any] = {}

                if nse_symbols:
                    res_nse = self.zerodha.get_quote(nse_symbols, exchange="NSE")
                    if isinstance(res_nse, dict) and res_nse:
                        merged.update(res_nse)

                if nfo_symbols:
                    res_nfo = self.zerodha.get_quote(nfo_symbols, exchange="NFO")
                    if isinstance(res_nfo, dict) and res_nfo:
                        merged.update(res_nfo)

                if merged and len(merged) > 0:
                    logger.info(
                        f"✓ Zerodha: Fetched quotes for {len(merged)} symbols "
                        f"(NSE={len(nse_symbols)}, NFO={len(nfo_symbols)})"
                    )
                    return merged
            except Exception as e:
                error_msg = str(e)
                if "api_key" in error_msg or "access_token" in error_msg:
                    logger.warning(f"⚠️  Zerodha authentication expired. Re-authenticate via /v1/zerodha/login-url")
                    self.use_zerodha = False
                else:
                    logger.warning(f"Zerodha quote failed: {e}")
                logger.info("→ Falling back to Yahoo Finance")

        # Fallback to Yahoo Finance
        out: Dict[str, Any] = {}
        if nse_symbols:
            try:
                out.update(self._get_quote_yahoo(nse_symbols))
            except Exception:
                pass

        # Yahoo cannot quote derivatives. Return safe defaults for NFO symbols.
        if nfo_symbols:
            ts = to_iso_utc(now_utc())
            for sym in nfo_symbols:
                out.setdefault(
                    sym,
                    {
                        "price": 0,
                        "open": 0,
                        "high": 0,
                        "low": 0,
                        "close": 0,
                        "volume": 0,
                        "oi": 0,
                        "change_percent": 0,
                        "timestamp": ts,
                    },
                )

        return out
    
    def _get_quote_yahoo(self, symbols: List[str]) -> Dict[str, Any]:
        """Get quotes from Yahoo Finance"""
        result = {}
        
        for symbol in symbols:
            try:
                # Add .NS suffix for Indian stocks
                yahoo_symbol = f"{symbol}.NS" if not symbol.endswith(('.NS', '.BO')) else symbol
                ticker = yf.Ticker(yahoo_symbol)
                info = ticker.info
                hist = ticker.history(period='1d')
                
                if not hist.empty:
                    result[symbol] = {
                        'price': hist['Close'].iloc[-1],
                        'open': hist['Open'].iloc[-1],
                        'high': hist['High'].iloc[-1],
                        'low': hist['Low'].iloc[-1],
                        'close': hist['Close'].iloc[-1],
                        'volume': hist['Volume'].iloc[-1],
                        'change_percent': ((hist['Close'].iloc[-1] - hist['Open'].iloc[-1]) / hist['Open'].iloc[-1]) * 100,
                        'timestamp': to_iso_utc(now_utc())
                    }
            except Exception as e:
                logger.error(f"Error fetching Yahoo quote for {symbol}: {e}")
                # Return default values
                result[symbol] = {
                    'price': 0,
                    'open': 0,
                    'high': 0,
                    'low': 0,
                    'close': 0,
                    'volume': 0,
                    'change_percent': 0,
                    'timestamp': to_iso_utc(now_utc())
                }
        
        return result
    
    def get_historical_data(
        self, 
        symbol: str, 
        from_date: datetime, 
        to_date: datetime,
        interval: str = "1d",
        use_cache: bool = True
    ) -> Optional[pd.DataFrame]:
        """
        Get historical OHLC data with intelligent caching
        Tries cache first, then Zerodha, then Yahoo Finance
        
        Args:
            symbol: Stock symbol
            from_date: Start date
            to_date: End date
            interval: Data interval (1m, 5m, 15m, 1h, 1d)
            use_cache: Whether to use cache (default: True)
            
        Returns:
            DataFrame with OHLC data
        """
        # Ensure we are using Zerodha when it becomes available
        if not self.use_zerodha and self.zerodha.is_authenticated():
            self.use_zerodha = True
            logger.info("✓ UnifiedDataProvider: Zerodha authenticated at runtime, enabling Zerodha for historical data")

        # Check cache first
        if use_cache:
            cached_data = self.cache.get(symbol, from_date, to_date, interval)
            if cached_data is not None:
                logger.info(f"✓ Cache HIT: {symbol} {interval} ({len(cached_data)} rows)")
                return cached_data
        
        # Cache miss - fetch from data source
        data = None
        source = "yahoo"
        
        # Try Zerodha first
        if self.use_zerodha:
            try:
                zerodha_interval = self._map_interval_to_zerodha(interval)
                data = self.zerodha.get_historical_data(symbol, from_date, to_date, zerodha_interval)
                source = "zerodha"
                logger.info(f"✓ Zerodha: Fetched {symbol} historical data")
            except Exception as e:
                logger.warning(f"Zerodha historical data failed: {e}")
        
        # Fallback to Yahoo Finance
        if data is None or (isinstance(data, pd.DataFrame) and data.empty):
            data = self._get_historical_yahoo(symbol, from_date, to_date, interval)
            source = "yahoo"
            if data is not None:
                logger.info(f"✓ Yahoo: Fetched {symbol} historical data ({len(data)} rows)")
        
        # Cache the fetched data
        if data is not None and not data.empty and use_cache:
            self.cache.set(symbol, from_date, to_date, interval, data, source)
        
        return data
    
    def _get_historical_yahoo(
        self, 
        symbol: str, 
        from_date: datetime, 
        to_date: datetime,
        interval: str = "1d"
    ) -> Optional[pd.DataFrame]:
        """Get historical data from Yahoo Finance"""
        try:
            yahoo_symbol = f"{symbol}.NS" if not symbol.endswith(('.NS', '.BO')) else symbol
            ticker = yf.Ticker(yahoo_symbol)
            df = ticker.history(start=from_date, end=to_date, interval=interval)
            
            if df.empty:
                return None
            
            # Standardize column names
            df = df.rename(columns={
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            })
            
            return df[['open', 'high', 'low', 'close', 'volume']]
        except Exception as e:
            logger.error(f"Error fetching Yahoo historical data for {symbol}: {e}")
            return None
    
    def _map_interval_to_zerodha(self, interval: str) -> str:
        """Map standard interval to Zerodha format"""
        mapping = {
            '1m': 'minute',
            '3m': '3minute',
            '5m': '5minute',
            '10m': '10minute',
            '15m': '15minute',
            '30m': '30minute',
            '1h': '60minute',
            '1d': 'day'
        }
        return mapping.get(interval, 'day')
    
    def get_ohlc_latest(self, symbols: List[str]) -> Dict[str, Any]:
        """
        Get latest OHLC data for symbols
        """
        if not self.use_zerodha and self.zerodha.is_authenticated():
            self.use_zerodha = True
            logger.info("✓ UnifiedDataProvider: Zerodha authenticated at runtime, enabling Zerodha OHLC")

        if self.use_zerodha:
            try:
                return self.zerodha.get_ohlc_latest(symbols)
            except Exception as e:
                logger.warning(f"Zerodha OHLC failed, falling back to Yahoo: {e}")
        
        # Fallback to Yahoo
        result = {}
        for symbol in symbols:
            try:
                yahoo_symbol = f"{symbol}.NS"
                ticker = yf.Ticker(yahoo_symbol)
                hist = ticker.history(period='5d')
                
                if not hist.empty:
                    latest = hist.iloc[-1]
                    result[symbol] = {
                        'open': latest['Open'],
                        'high': latest['High'],
                        'low': latest['Low'],
                        'close': latest['Close'],
                        'last_price': latest['Close'],
                        'volume': latest['Volume']
                    }
            except Exception as e:
                logger.error(f"Error fetching Yahoo OHLC for {symbol}: {e}")
        
        return result
    
    def get_indices_quote(self) -> Dict[str, Any]:
        """Get quotes for major indices"""
        if not self.use_zerodha and self.zerodha.is_authenticated():
            self.use_zerodha = True
            logger.info("✓ UnifiedDataProvider: Zerodha authenticated at runtime, enabling Zerodha indices")

        if self.use_zerodha:
            try:
                result = self.zerodha.get_indices_quote()
                if result and len(result) > 0:
                    logger.info(f"✓ Zerodha: Fetched {len(result)} indices")
                    return result
                else:
                    logger.warning("Zerodha returned no data, falling back to Yahoo")
            except Exception as e:
                error_msg = str(e)
                if "api_key" in error_msg or "access_token" in error_msg:
                    logger.warning(f"⚠️  Zerodha authentication expired/invalid. Please re-authenticate via /v1/zerodha/login-url")
                    # Disable Zerodha for subsequent calls in this session
                    self.use_zerodha = False
                else:
                    logger.warning(f"Zerodha indices failed: {e}")
                logger.info("→ Falling back to Yahoo Finance")
        
        # Fallback to Yahoo (near-real-time) using the chart endpoint (1m interval).
        # This avoids the stale `yfinance.history(period='1d')` behaviour.
        indices_map = {
            'NIFTY 50': '^NSEI',
            'NIFTY BANK': '^NSEBANK',
            'SENSEX': '^BSESN'
        }

        try:
            return self._get_indices_quote_yahoo_chart(indices_map)
        except Exception as e:
            logger.warning(f"Yahoo chart indices fallback failed, trying yfinance: {e}")

        # Last resort (may be stale depending on Yahoo/yfinance caching)
        result: Dict[str, Any] = {}
        for name, yahoo_symbol in indices_map.items():
            try:
                ticker = yf.Ticker(yahoo_symbol)
                hist = ticker.history(period='1d')

                if not hist.empty:
                    open_px = float(hist['Open'].iloc[-1]) if 'Open' in hist else 0.0
                    close_px = float(hist['Close'].iloc[-1]) if 'Close' in hist else 0.0
                    result[name] = {
                        'price': close_px,
                        'open': open_px,
                        'high': float(hist['High'].iloc[-1]) if 'High' in hist else 0.0,
                        'low': float(hist['Low'].iloc[-1]) if 'Low' in hist else 0.0,
                        'close': close_px,
                        'volume': float(hist['Volume'].iloc[-1]) if 'Volume' in hist else 0.0,
                        'change_percent': ((close_px - open_px) / open_px) * 100 if open_px else 0.0,
                        'timestamp': to_iso_utc(now_utc())
                    }
            except Exception as err:
                logger.error(f"Error fetching Yahoo index {name}: {err}")

        return result

    def _get_indices_quote_yahoo_chart(self, indices_map: Dict[str, str]) -> Dict[str, Any]:
        """Fetch index quotes via Yahoo chart API (near-real-time).

        Returns values consistent with Zerodha quote output.
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://finance.yahoo.com/",
        }

        out: Dict[str, Any] = {}
        with httpx.Client(timeout=10, headers=headers, follow_redirects=True) as cx:
            for name, yahoo_symbol in indices_map.items():
                try:
                    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
                    r = cx.get(url, params={"interval": "1m", "range": "1d"})
                    r.raise_for_status()
                    j = r.json() or {}
                    result = (j.get("chart", {}).get("result") or [])
                    if not result:
                        continue
                    node = result[0] or {}
                    meta = node.get("meta") or {}

                    price = meta.get("regularMarketPrice")
                    prev_close = (
                        meta.get("previousClose")
                        or meta.get("chartPreviousClose")
                        or meta.get("regularMarketPreviousClose")
                    )
                    market_time = meta.get("regularMarketTime")

                    ts = None
                    try:
                        if isinstance(market_time, (int, float)):
                            ts = to_iso_utc(datetime.fromtimestamp(float(market_time), tz=timezone.utc))
                    except Exception:
                        ts = None

                    change_percent = None
                    try:
                        if isinstance(price, (int, float)) and isinstance(prev_close, (int, float)) and prev_close:
                            change_percent = ((float(price) - float(prev_close)) / float(prev_close)) * 100.0
                    except Exception:
                        change_percent = None

                    out[name] = {
                        'price': float(price) if isinstance(price, (int, float)) else None,
                        'open': meta.get('regularMarketOpen'),
                        'high': meta.get('regularMarketDayHigh'),
                        'low': meta.get('regularMarketDayLow'),
                        'close': float(prev_close) if isinstance(prev_close, (int, float)) else None,
                        'volume': meta.get('regularMarketVolume'),
                        'change_percent': round(float(change_percent), 2) if isinstance(change_percent, (int, float)) else None,
                        'timestamp': ts or to_iso_utc(now_utc()),
                    }
                except Exception as e:
                    logger.debug(f"Yahoo chart quote failed for {name}: {e}")
                    continue

        return out
    
    def get_market_status(self) -> Dict[str, Any]:
        """Get market status"""
        if self.use_zerodha:
            try:
                return self.zerodha.get_market_status()
            except:
                pass
        
        # Default market status check
        now = now_ist()
        is_weekday = now.weekday() < 5
        market_open_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
        is_trading_hours = market_open_time <= now <= market_close_time
        
        return {
            'is_open': is_weekday and is_trading_hours,
            'is_weekday': is_weekday,
            'is_trading_hours': is_trading_hours,
            'current_time': now
        }
    
    def get_data_source(self) -> str:
        """Get current data source being used"""
        return "Zerodha" if self.use_zerodha else "Yahoo Finance"


# Global instance
_unified_provider = None

def get_data_provider() -> UnifiedDataProvider:
    """Get or create unified data provider instance"""
    global _unified_provider
    if _unified_provider is None:
        _unified_provider = UnifiedDataProvider()
    return _unified_provider
