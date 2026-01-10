"""
Chart Data Service - Real-time OHLC Data Integration
Integrates with multiple data sources in priority order:
1. Zerodha Kite API (real-time, requires auth)
2. NSE India (free, delayed)
3. Yahoo Finance (global, free)
4. Alpha Vantage (free tier)
5. Finnhub (free tier)
6. Mock data (fallback)
"""

import os
import asyncio
import httpx
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta, time
from pathlib import Path

# Load environment
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent.parent / '.env'
    load_dotenv(env_path)
except ImportError:
    pass

# API Keys
ALPHA_VANTAGE_KEY = os.getenv('ALPHA_VANTAGE_API_KEY', '')
FINNHUB_KEY = os.getenv('FINNHUB_API_KEY', '')
ZERODHA_ACCESS_TOKEN = os.getenv('ZERODHA_ACCESS_TOKEN', '')

# Try to import Zerodha
try:
    from .zerodha_service import zerodha_service, KITE_AVAILABLE
except ImportError:
    KITE_AVAILABLE = False
    zerodha_service = None


class ChartDataService:
    """
    Multi-source chart data provider with intelligent fallbacks.
    """
    
    def __init__(self):
        # Use the global zerodha_service instance that was authenticated via API
        self.zerodha = zerodha_service if KITE_AVAILABLE else None
        if self.zerodha and self.zerodha.access_token:
            print("[OK] Zerodha Kite connected (authenticated)")
        elif self.zerodha:
            print("[WARN] Zerodha available but not authenticated yet")
    
    async def fetch_chart_data(
        self,
        symbol: str,
        timeframe: str = '3M'
    ) -> Dict[str, Any]:
        """
        Fetch chart data from best available source.
        
        Args:
            symbol: Stock symbol (e.g., 'RELIANCE', 'TCS', 'NIFTY')
            timeframe: '1M', '3M', '6M', '1Y'
            
        Returns:
            Dict with candles, signals, current price
        """
        
        print(f"\n{'='*60}")
        print(f"Fetching chart data: {symbol} / {timeframe}")
        print(f"{'='*60}")
        
        # Try sources in priority order.
        # To keep latency low for chart view, we currently:
        #  - Prefer Zerodha (when authenticated) for Indian markets.
        #  - Fall back to Yahoo Finance.
        #  - Skip Alpha Vantage / Finnhub here to avoid slow extra network hops.

        if self.zerodha and self.zerodha.access_token:
            sources = [
                ('Zerodha Kite', self._fetch_from_zerodha),
                ('Yahoo Finance', self._fetch_from_yahoo),
            ]
        else:
            sources = [
                ('Yahoo Finance', self._fetch_from_yahoo),
            ]
        
        for source_name, fetch_func in sources:
            try:
                print(f"\nTrying {source_name}...")
                df = await fetch_func(symbol, timeframe)
                if df is not None and len(df) > 0:
                    print(f"SUCCESS: {source_name} returned {len(df)} candles")
                    return self._format_chart_response(symbol, timeframe, df, source_name)
                else:
                    print(f"  {source_name} returned no data")
            except Exception as e:
                print(f"  {source_name} EXCEPTION: {str(e)[:150]}")
                import traceback
                traceback.print_exc()
                continue
        
        # Fallback to mock data
        print(f"\nAll sources failed - using mock data for {symbol}")
        df = self._generate_mock_data(symbol, timeframe)
        return self._format_chart_response(symbol, timeframe, df, "Mock Data")
    
    # ==================== Data Source Fetchers ====================
    
    async def _fetch_from_zerodha(
        self,
        symbol: str,
        timeframe: str
    ) -> Optional[pd.DataFrame]:
        """Fetch intraday data from Zerodha Kite API"""
        if not self.zerodha:
            print("  Zerodha: Service not available")
            return None
        
        try:
            # Check if authenticated (check dynamically, not at init)
            if not self.zerodha.access_token or not self.zerodha.kite:
                print("  Zerodha: Not authenticated - no access token")
                print("  Hint: Call /v1/zerodha/login-url to authenticate")
                return None
            
            print(f"  Zerodha: Authenticated as {self.zerodha.access_token[:20]}...")
            
            # Map timeframe to interval for charts (as per user requirements)
            # 1D: 5-minute candles for cleaner intraday view (last 3 trading days)
            # 1W & 1M: Hourly candles for swing trading view
            # 1Y: Daily candles for long-term trend
            interval_map = {
                '1D': '5minute',     # 5-min candles for 1-day intraday view (3-day window)
                '1W': '60minute',    # Hourly candles for 1-week view
                '1M': '60minute',    # Hourly candles for 1-month view
                '1Y': 'day'          # Daily candles for 1-year long-term view
            }
            interval = interval_map.get(timeframe, 'day')
            
            # Calculate date range (1D shows last 3 trading days)
            days_map = {'1D': 3, '1W': 7, '1M': 30, '1Y': 365}
            days = days_map.get(timeframe, 30)
            
            from_date = datetime.now() - timedelta(days=days)
            to_date = datetime.now()
            
            print(f"  Zerodha: Requesting {symbol} with {interval} interval")
            
            # Get historical data from Zerodha service
            df = await self.zerodha.get_historical_data(
                symbol=symbol,
                from_date=from_date,
                to_date=to_date,
                interval=interval
            )
            
            if df is not None and len(df) > 0:
                print(f"  Zerodha: SUCCESS - {len(df)} candles")
                return df
            else:
                print("  Zerodha: No data returned")
                return None
                
        except Exception as e:
            print(f"  Zerodha: ERROR - {str(e)[:150]}")
            import traceback
            traceback.print_exc()
            return None
    
    async def _fetch_from_nse(
        self,
        symbol: str,
        timeframe: str
    ) -> Optional[pd.DataFrame]:
        """Fetch from NSE India"""
        # NSE provides limited historical data via their website
        # This would require scraping or using unofficial APIs
        return None
    
    async def _fetch_from_yahoo(
        self,
        symbol: str,
        timeframe: str
    ) -> Optional[pd.DataFrame]:
        """Fetch from Yahoo Finance using yfinance library.

        For 1D timeframe we use intraday candles (5-minute) so that
        the chart has multiple candles instead of a single daily bar.
        """
        try:
            import yfinance as yf
            import asyncio
            
            # Map timeframe to period
            period_map = {'1D': '5d', '1W': '1mo', '1M': '3mo', '1Y': '1y'}
            period = period_map.get(timeframe, '3mo')

            # Decide interval per timeframe so charts have sufficient candles
            if timeframe == '1D':
                interval = '5m'     # 5-minute candles for cleaner intraday view
            elif timeframe in ['1W', '1M']:
                interval = '60m'    # Hourly candles for 1-week / 1-month trends
            else:
                interval = '1d'     # Daily candles for 1-year and others
            
            # Convert symbol to Yahoo format (add .NS for NSE stocks)
            if symbol in ['NIFTY', 'NIFTY50']:
                yahoo_symbol = '^NSEI'
            elif symbol == 'BANKNIFTY':
                yahoo_symbol = '^NSEBANK'
            else:
                yahoo_symbol = f"{symbol}.NS"
            
            print(f"  Fetching {yahoo_symbol} for period {period} interval {interval}...")
            
            # Fetch data using yfinance (run in executor since it's blocking)
            def fetch_sync():
                ticker = yf.Ticker(yahoo_symbol)
                return ticker.history(period=period, interval=interval)
            
            df = await asyncio.to_thread(fetch_sync)
            
            if df is None or len(df) == 0:
                print(f"  Yahoo returned empty data for {yahoo_symbol}")
                return None
            
            # Reset index to get Datetime/Date as a column
            df = df.reset_index()

            # Determine the datetime column name returned by yfinance
            datetime_col = 'Datetime' if 'Datetime' in df.columns else 'Date'

            # Rename columns to standard format
            df = df.rename(columns={
                datetime_col: 'date',
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            })

            # Normalize dates to timezone-aware IST for Indian markets
            df['date'] = pd.to_datetime(df['date'])
            if df['date'].dt.tz is None:
                df['date'] = df['date'].dt.tz_localize('Asia/Kolkata')
            else:
                df['date'] = df['date'].dt.tz_convert('Asia/Kolkata')

            # Filter for requested timeframe days based on IST calendar (1D uses last 3 days)
            days_map = {'1D': 3, '1W': 7, '1M': 30, '1Y': 365}
            days = days_map.get(timeframe, 30)
            cutoff = pd.Timestamp.now(tz='Asia/Kolkata') - pd.Timedelta(days=days)
            df = df[df['date'] >= cutoff]

            # Restrict to NSE/BSE regular trading hours: weekdays 09:00–15:30 IST
            df = df[
                (df['date'].dt.weekday < 5)
                & (df['date'].dt.time >= time(9, 0))
                & (df['date'].dt.time <= time(15, 30))
            ]

            if len(df) == 0:
                print(f"  Yahoo Finance returned no in-session data for {yahoo_symbol}")
                return None

            # Convert IST datetimes to UTC timestamps (seconds) for the frontend
            df['time'] = df['date'].dt.tz_convert('UTC').astype('int64') // 10**9

            print(f"  Yahoo Finance SUCCESS: {len(df)} candles for {yahoo_symbol}")
            return df[['time', 'open', 'high', 'low', 'close', 'volume']]
                
        except Exception as e:
            print(f"  Yahoo Finance FAILED: {str(e)[:150]}")
            import traceback
            traceback.print_exc()
            return None
    
    async def _fetch_from_alpha_vantage(
        self,
        symbol: str,
        timeframe: str
    ) -> Optional[pd.DataFrame]:
        """Fetch from Alpha Vantage"""
        if not ALPHA_VANTAGE_KEY or ALPHA_VANTAGE_KEY == 'demo':
            return None
        
        try:
            # Alpha Vantage uses different symbols for Indian stocks
            # Would need proper symbol mapping
            url = "https://www.alphavantage.co/query"
            params = {
                'function': 'TIME_SERIES_DAILY',
                'symbol': f"{symbol}.BSE",  # BSE format
                'apikey': ALPHA_VANTAGE_KEY,
                'outputsize': 'full'
            }
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if 'Time Series (Daily)' in data:
                        series = data['Time Series (Daily)']
                        
                        # Convert to DataFrame
                        rows = []
                        for date_str, values in series.items():
                            rows.append({
                                'date': date_str,
                                'open': float(values['1. open']),
                                'high': float(values['2. high']),
                                'low': float(values['3. low']),
                                'close': float(values['4. close']),
                                'volume': int(values['5. volume'])
                            })
                        
                        df = pd.DataFrame(rows)
                        df['time'] = pd.to_datetime(df['date']).astype(int) // 10**9
                        
                        return df[['time', 'open', 'high', 'low', 'close', 'volume']]
                
        except Exception as e:
            print(f"Alpha Vantage error: {e}")
            return None
    
    async def _fetch_from_finnhub(
        self,
        symbol: str,
        timeframe: str
    ) -> Optional[pd.DataFrame]:
        """Fetch from Finnhub"""
        if not FINNHUB_KEY or FINNHUB_KEY == 'demo':
            return None
        
        try:
            # Finnhub requires specific symbol formats
            # Would need symbol mapping for Indian stocks
            return None
            
        except Exception as e:
            print(f"Finnhub error: {e}")
            return None
    
    # ==================== Mock Data Generator ====================
    
    def _generate_mock_data(
        self,
        symbol: str,
        timeframe: str
    ) -> pd.DataFrame:
        """Generate realistic mock data"""
        days_map = {'1D': 3, '1W': 7, '1M': 30, '1Y': 365}
        days = days_map.get(timeframe, 30)
        
        # Base price
        if 'NIFTY' in symbol:
            base_price = 21000
        elif symbol == 'RELIANCE':
            base_price = 2500
        elif symbol == 'TCS':
            base_price = 3500
        else:
            base_price = np.random.randint(500, 3000)
        
        # Generate dates
        end_date = datetime.now()
        dates = pd.date_range(end=end_date, periods=days, freq='D')
        
        # Filter out weekends
        dates = dates[dates.weekday < 5]
        
        # Generate price movement (random walk with drift)
        returns = np.random.normal(0.001, 0.02, len(dates))  # Slight upward drift
        prices = base_price * np.exp(np.cumsum(returns))
        
        # Generate OHLC
        data = []
        for i, date in enumerate(dates):
            open_price = prices[i]
            close_price = prices[i] * (1 + np.random.normal(0, 0.01))
            high_price = max(open_price, close_price) * (1 + abs(np.random.normal(0, 0.01)))
            low_price = min(open_price, close_price) * (1 - abs(np.random.normal(0, 0.01)))
            volume = int(np.random.uniform(1e6, 10e6))
            
            data.append({
                'time': int(date.timestamp()),
                'open': round(open_price, 2),
                'high': round(high_price, 2),
                'low': round(low_price, 2),
                'close': round(close_price, 2),
                'volume': volume
            })
        
        return pd.DataFrame(data)
    
    # ==================== Signal Generation ====================
    
    def _generate_signals(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Generate AI trading signals from price data"""
        if len(df) < 20:
            return []
        
        signals = []
        
        # Calculate indicators
        df = df.copy()
        df['sma_20'] = df['close'].rolling(20).mean()
        df['sma_50'] = df['close'].rolling(50).mean() if len(df) >= 50 else df['close']
        
        # Recent signals only (last 20% of data)
        recent_start = int(len(df) * 0.8)
        recent_df = df.iloc[recent_start:]
        
        for idx in range(1, len(recent_df)):
            row = recent_df.iloc[idx]
            prev_row = recent_df.iloc[idx - 1]
            
            # MACD Crossover (simplified)
            if prev_row['close'] < prev_row['sma_20'] and row['close'] > row['sma_20']:
                signals.append({
                    'time': int(row['time']),
                    'type': 'bullish',
                    'text': 'MACD Bullish Crossover',
                    'price': round(row['close'], 2)
                })
            
            # Resistance Breakout
            if row['high'] > recent_df['high'].rolling(10).max().iloc[idx]:
                signals.append({
                    'time': int(row['time']),
                    'type': 'bullish',
                    'text': 'Resistance Breakout',
                    'price': round(row['close'], 2)
                })
            
            # Support Breakdown
            if row['low'] < recent_df['low'].rolling(10).min().iloc[idx]:
                signals.append({
                    'time': int(row['time']),
                    'type': 'bearish',
                    'text': 'Support Breakdown',
                    'price': round(row['close'], 2)
                })
            
            # Volume Spike
            avg_volume = recent_df['volume'].rolling(10).mean().iloc[idx]
            if row['volume'] > avg_volume * 1.5:
                signals.append({
                    'time': int(row['time']),
                    'type': 'bullish',
                    'text': 'Volume Surge',
                    'price': round(row['close'], 2)
                })
        
        # Return max 5 most recent signals
        return signals[-5:]
    
    # ==================== Response Formatter ====================
    
    def _format_chart_response(
        self,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame,
        source: str
    ) -> Dict[str, Any]:
        """Format chart data response"""
        
        # Ensure we only have the required columns
        required_cols = ['time', 'open', 'high', 'low', 'close', 'volume']
        df = df[required_cols].copy()
        
        # Convert to proper numeric types and handle any NaN values
        for col in ['open', 'high', 'low', 'close']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0).astype(int)
        df['time'] = df['time'].astype(int)
        
        # Drop any rows with NaN values
        df = df.dropna()
        
        # Generate signals
        signals = self._generate_signals(df)
        
        # Get current/latest candle
        latest = df.iloc[-1]
        first = df.iloc[0]
        
        # Calculate change
        change_pct = ((latest['close'] - first['open']) / first['open']) * 100
        
        # Convert DataFrame to list of dicts with explicit float conversion
        # Round prices to 2 decimal places for clarity
        candles = []
        for _, row in df.iterrows():
            candles.append({
                'time': int(row['time']),
                'open': round(float(row['open']), 2),
                'high': round(float(row['high']), 2),
                'low': round(float(row['low']), 2),
                'close': round(float(row['close']), 2),
                'volume': int(row['volume'])
            })
        
        return {
            'symbol': symbol,
            'timeframe': timeframe,
            'candles': candles,
            'signals': signals,
            'current': {
                'price': round(float(latest['close']), 2),
                'change': round(float(change_pct), 2),
                'volume': int(latest['volume'])
            },
            'data_source': source,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }


# Global instance
chart_data_service = ChartDataService()
