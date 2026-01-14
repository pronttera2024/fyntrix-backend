"""
Market Data Provider - Robust Multi-Source OHLCV Data
Primary: Zerodha Kite Connect (600 req/min), Fallbacks: NSE, Alpha Vantage, Finnhub, Yahoo
With aggressive caching and rate limit handling
"""

import os
import asyncio
import httpx
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import pandas as pd
from pathlib import Path
from .cache_redis import get_cached
from .zerodha_service import ZerodhaService

# Load .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent.parent / '.env'
    load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv not installed

# API Keys
ALPHA_VANTAGE_KEY = os.getenv('ALPHA_VANTAGE_API_KEY', 'demo')
FINNHUB_KEY = os.getenv('FINNHUB_API_KEY', 'demo')

# NSE Symbol mappings (NSE uses .NS suffix for Yahoo, but different for NSE API)
NSE_SYMBOLS = {
    'RELIANCE': 'RELIANCE',
    'TCS': 'TCS',
    'HDFCBANK': 'HDFCBANK',
    'INFY': 'INFY',
    'ICICIBANK': 'ICICIBANK',
    'BHARTIARTL': 'BHARTIARTL',
    'ITC': 'ITC',
    'SBIN': 'SBIN',
    'HINDUNILVR': 'HINDUNILVR',
    'BAJFINANCE': 'BAJFINANCE',
    'LT': 'LT',
    'KOTAKBANK': 'KOTAKBANK',
    'AXISBANK': 'AXISBANK',
    'ASIANPAINT': 'ASIANPAINT',
    'MARUTI': 'MARUTI',
    'TITAN': 'TITAN',
}

# Rate limiting settings
RATE_LIMIT_DELAY = 2.0  # seconds between requests
RETRY_ATTEMPTS = 3
RETRY_DELAY = 5.0  # seconds


class MarketDataProvider:
    """
    Multi-source market data provider with intelligent fallbacks.
    
    Priority:
    1. Zerodha Kite Connect (PRIMARY - 600 requests/minute, best data quality)
    2. NSE Official API (fallback for Indian stocks)
    3. Alpha Vantage (fallback)
    4. Finnhub (fallback)
    5. Yahoo Finance (fallback)
    6. Cached/Demo data (last resort)
    """
    
    def __init__(self):
        self.last_request_time = {}
        self.request_counts = {}
        
        # Initialize Zerodha service
        try:
            self.zerodha = ZerodhaService()
            if self.zerodha.access_token:
                print("  [OK] Zerodha Kite initialized as PRIMARY data source")
            else:
                print("  [WARN] Zerodha available but not authenticated. Will use fallback sources.")
        except Exception as e:
            print(f"  [WARN] Zerodha initialization failed: {e}. Using fallback sources.")
            self.zerodha = None
    
    async def _rate_limit_wait(self, source: str):
        """Implement rate limiting per source"""
        now = datetime.utcnow()
        
        if source in self.last_request_time:
            elapsed = (now - self.last_request_time[source]).total_seconds()
            if elapsed < RATE_LIMIT_DELAY:
                wait_time = RATE_LIMIT_DELAY - elapsed
                await asyncio.sleep(wait_time)
        
        self.last_request_time[source] = datetime.utcnow()
        
        # Track request count
        self.request_counts[source] = self.request_counts.get(source, 0) + 1
    
    async def fetch_ohlcv(
        self,
        symbol: str,
        interval: str = "1d",
        days: int = 365
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV data with intelligent fallbacks.
        
        Args:
            symbol: Stock symbol (e.g., 'RELIANCE', 'TCS')
            interval: Time interval ('1d', '60m', '15m', '1m')
            days: Number of days of history
            
        Returns:
            DataFrame with OHLCV data or None
        """
        # Try cache first (aggressive caching)
        cache_key = f"ohlcv:{symbol}:{interval}:{days}"
        
        async def _fetch_with_fallbacks():
            # Try each source in order (Zerodha FIRST for speed and reliability)
            sources = [
                self._fetch_from_zerodha,
                self._fetch_from_nse,
                self._fetch_from_alpha_vantage,
                self._fetch_from_finnhub,
                self._fetch_from_yahoo,
            ]
            
            for fetch_func in sources:
                try:
                    df = await fetch_func(symbol, interval, days)
                    if df is not None and len(df) > 0:
                        print(f"  ✓ Data from {fetch_func.__name__.replace('_fetch_from_', '')}: {len(df)} bars")
                        return df
                except Exception as e:
                    print(f"  ⚠️  {fetch_func.__name__.replace('_fetch_from_', '')} failed: {str(e)[:50]}")
                    continue
            
            # All sources failed - return demo data
            print(f"  ⚠️  All sources failed for {symbol}, using demo data")
            return self._generate_demo_data(symbol, days)
        
        # Cache TTL based on interval
        if interval == "1d":
            ttl = 3600.0  # 1 hour for daily
        elif interval == "60m":
            ttl = 600.0   # 10 minutes for hourly
        else:
            ttl = 300.0   # 5 minutes for intraday
        
        try:
            return await get_cached(cache_key, _fetch_with_fallbacks, ttl=ttl, persist=True)
        except Exception as e:
            print(f"  ✗ Cache error: {e}")
            return self._generate_demo_data(symbol, days)
    
    async def _fetch_from_zerodha(
        self,
        symbol: str,
        interval: str,
        days: int
    ) -> Optional[pd.DataFrame]:
        """Fetch from Zerodha Kite Connect (PRIMARY SOURCE - 600 requests/minute)"""
        # Skip if Zerodha not available or not authenticated
        if not self.zerodha or not self.zerodha.access_token:
            return None
        
        await self._rate_limit_wait('zerodha')
        
        try:
            # Map interval to Zerodha format
            interval_map = {
                '1d': 'day',
                '60m': '60minute',
                '15m': '15minute',
                '5m': '5minute',
                '1m': 'minute'
            }
            zerodha_interval = interval_map.get(interval, 'day')
            
            # Calculate date range
            from_date = datetime.now() - timedelta(days=days)
            to_date = datetime.now()
            
            # Fetch from Zerodha
            df = await self.zerodha.get_historical_data(
                symbol=symbol,
                from_date=from_date,
                to_date=to_date,
                interval=zerodha_interval
            )
            
            if df is not None and not df.empty:
                print(f"  Zerodha: SUCCESS - {len(df)} candles for {symbol}")
                return df
            
            return None
            
        except Exception as e:
            # Don't print full error, just note Zerodha failed (will try fallbacks)
            print(f"  Zerodha: Skipping ({str(e)[:30]}...)")
            return None
    
    async def _fetch_from_nse(
        self,
        symbol: str,
        interval: str,
        days: int
    ) -> Optional[pd.DataFrame]:
        """Fetch from NSE official API"""
        await self._rate_limit_wait('nse')
        
        # NSE API provides daily data
        if interval != "1d":
            raise ValueError("NSE only supports daily data")
        
        nse_symbol = NSE_SYMBOLS.get(symbol.upper(), symbol.upper())
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://www.nseindia.com/",
            "Accept": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            # Warm up cookies
            await client.get("https://www.nseindia.com/")
            await asyncio.sleep(1)
            
            # Fetch historical data
            to_date = datetime.now()
            from_date = to_date - timedelta(days=days)
            
            url = (
                f"https://www.nseindia.com/api/historical/cm/equity?"
                f"symbol={nse_symbol}&"
                f"series=[%22EQ%22]&"
                f"from={from_date.strftime('%d-%m-%Y')}&"
                f"to={to_date.strftime('%d-%m-%Y')}"
            )
            
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            
            if not data or 'data' not in data:
                return None
            
            # Parse NSE data
            records = []
            for item in data['data']:
                records.append({
                    'date': pd.to_datetime(item['CH_TIMESTAMP']),
                    'open': float(item['CH_OPENING_PRICE']),
                    'high': float(item['CH_TRADE_HIGH_PRICE']),
                    'low': float(item['CH_TRADE_LOW_PRICE']),
                    'close': float(item['CH_CLOSING_PRICE']),
                    'volume': int(item['CH_TOT_TRADED_QTY'])
                })
            
            if not records:
                return None
            
            df = pd.DataFrame(records)
            df.set_index('date', inplace=True)
            df.sort_index(inplace=True)
            
            return df
    
    async def _fetch_from_alpha_vantage(
        self,
        symbol: str,
        interval: str,
        days: int
    ) -> Optional[pd.DataFrame]:
        """Fetch from Alpha Vantage"""
        await self._rate_limit_wait('alpha_vantage')
        
        if ALPHA_VANTAGE_KEY == 'demo':
            raise ValueError("Alpha Vantage API key not configured")
        
        # Map interval
        if interval == "1d":
            function = "TIME_SERIES_DAILY"
            interval_param = None
        elif interval in ["60m", "15m"]:
            function = "TIME_SERIES_INTRADAY"
            interval_param = "60min" if interval == "60m" else "15min"
        else:
            raise ValueError(f"Unsupported interval: {interval}")
        
        # Add .NS for Indian stocks
        av_symbol = f"{symbol}.BSE" if symbol.upper() in NSE_SYMBOLS else symbol
        
        params = {
            "function": function,
            "symbol": av_symbol,
            "apikey": ALPHA_VANTAGE_KEY,
            "outputsize": "full" if days > 100 else "compact"
        }
        
        if interval_param:
            params["interval"] = interval_param
        
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get("https://www.alphavantage.co/query", params=params)
            response.raise_for_status()
            data = response.json()
            
            # Find time series key
            ts_key = None
            for key in data.keys():
                if "Time Series" in key:
                    ts_key = key
                    break
            
            if not ts_key or ts_key not in data:
                return None
            
            # Parse data
            records = []
            for date_str, values in data[ts_key].items():
                records.append({
                    'date': pd.to_datetime(date_str),
                    'open': float(values['1. open']),
                    'high': float(values['2. high']),
                    'low': float(values['3. low']),
                    'close': float(values['4. close']),
                    'volume': int(values['5. volume'])
                })
            
            if not records:
                return None
            
            df = pd.DataFrame(records)
            df.set_index('date', inplace=True)
            df.sort_index(inplace=True)
            
            # Filter by days
            cutoff = datetime.now() - timedelta(days=days)
            df = df[df.index >= cutoff]
            
            return df
    
    async def _fetch_from_finnhub(
        self,
        symbol: str,
        interval: str,
        days: int
    ) -> Optional[pd.DataFrame]:
        """Fetch from Finnhub"""
        await self._rate_limit_wait('finnhub')
        
        if FINNHUB_KEY == 'demo':
            raise ValueError("Finnhub API key not configured")
        
        # Finnhub uses different intervals
        if interval == "1d":
            resolution = "D"
        elif interval == "60m":
            resolution = "60"
        elif interval == "15m":
            resolution = "15"
        else:
            resolution = "D"
        
        # Add .NS for Indian stocks
        fh_symbol = f"NSE:{symbol}" if symbol.upper() in NSE_SYMBOLS else symbol
        
        to_ts = int(datetime.now().timestamp())
        from_ts = int((datetime.now() - timedelta(days=days)).timestamp())
        
        params = {
            "symbol": fh_symbol,
            "resolution": resolution,
            "from": from_ts,
            "to": to_ts,
            "token": FINNHUB_KEY
        }
        
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get("https://finnhub.io/api/v1/stock/candle", params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get('s') != 'ok':
                return None
            
            # Parse data
            records = []
            for i in range(len(data['t'])):
                records.append({
                    'date': pd.to_datetime(data['t'][i], unit='s'),
                    'open': float(data['o'][i]),
                    'high': float(data['h'][i]),
                    'low': float(data['l'][i]),
                    'close': float(data['c'][i]),
                    'volume': int(data['v'][i])
                })
            
            if not records:
                return None
            
            df = pd.DataFrame(records)
            df.set_index('date', inplace=True)
            df.sort_index(inplace=True)
            
            return df
    
    async def _fetch_from_yahoo(
        self,
        symbol: str,
        interval: str,
        days: int
    ) -> Optional[pd.DataFrame]:
        """Fetch from Yahoo Finance (with retry logic)"""
        
        for attempt in range(RETRY_ATTEMPTS):
            try:
                await self._rate_limit_wait('yahoo')
                
                # Add .NS for Indian stocks
                yahoo_symbol = f"{symbol}.NS" if symbol.upper() in NSE_SYMBOLS else symbol
                
                # Map interval
                if interval == "1d":
                    yf_interval = "1d"
                    range_str = f"{days}d"
                elif interval == "60m":
                    yf_interval = "60m"
                    range_str = f"{min(days, 60)}d"
                elif interval == "15m":
                    yf_interval = "15m"
                    range_str = f"{min(days, 30)}d"
                else:
                    yf_interval = "1d"
                    range_str = f"{days}d"
                
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?interval={yf_interval}&range={range_str}"
                
                async with httpx.AsyncClient(timeout=15) as client:
                    response = await client.get(url)
                    
                    if response.status_code == 429:
                        # Rate limited - wait and retry
                        wait_time = RETRY_DELAY * (attempt + 1)
                        print(f"  ⏳ Rate limited, waiting {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    result = data.get('chart', {}).get('result', [{}])[0]
                    timestamps = result.get('timestamp', [])
                    indicators = result.get('indicators', {}).get('quote', [{}])[0]
                    
                    if not timestamps:
                        return None
                    
                    # Parse data
                    records = []
                    for i, ts in enumerate(timestamps):
                        records.append({
                            'date': pd.to_datetime(ts, unit='s'),
                            'open': indicators['open'][i] if indicators.get('open') else None,
                            'high': indicators['high'][i] if indicators.get('high') else None,
                            'low': indicators['low'][i] if indicators.get('low') else None,
                            'close': indicators['close'][i] if indicators.get('close') else None,
                            'volume': indicators['volume'][i] if indicators.get('volume') else 0
                        })
                    
                    # Remove None values
                    records = [r for r in records if r['close'] is not None]
                    
                    if not records:
                        return None
                    
                    df = pd.DataFrame(records)
                    df.set_index('date', inplace=True)
                    df.sort_index(inplace=True)
                    
                    return df
                    
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < RETRY_ATTEMPTS - 1:
                    continue
                else:
                    raise
            except Exception as e:
                if attempt < RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                else:
                    raise
        
        return None
    
    def _generate_demo_data(self, symbol: str, days: int) -> pd.DataFrame:
        """Generate demo/cached data for testing"""
        import numpy as np
        
        # Generate synthetic but realistic-looking data
        dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
        
        # Base price (varies by symbol)
        base_prices = {
            'RELIANCE': 2500,
            'TCS': 3500,
            'HDFCBANK': 1600,
            'INFY': 1450,
            'ICICIBANK': 950,
        }
        base = base_prices.get(symbol.upper(), 1000)
        
        # Generate random walk
        np.random.seed(hash(symbol) % 2**32)
        returns = np.random.normal(0.001, 0.02, days)
        prices = base * np.exp(np.cumsum(returns))
        
        # Generate OHLC
        records = []
        for i, date in enumerate(dates):
            close = prices[i]
            open_price = close * (1 + np.random.normal(0, 0.005))
            high = max(open_price, close) * (1 + abs(np.random.normal(0, 0.01)))
            low = min(open_price, close) * (1 - abs(np.random.normal(0, 0.01)))
            volume = int(np.random.uniform(1e6, 5e6))
            
            records.append({
                'date': date,
                'open': open_price,
                'high': high,
                'low': low,
                'close': close,
                'volume': volume
            })
        
        df = pd.DataFrame(records)
        df.set_index('date', inplace=True)
        
        return df
    
    def get_stats(self) -> Dict[str, Any]:
        """Get provider statistics"""
        return {
            'request_counts': self.request_counts,
            'last_requests': {
                source: time.isoformat()
                for source, time in self.last_request_time.items()
            }
        }


# Global instance
market_data_provider = MarketDataProvider()
