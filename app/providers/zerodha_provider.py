"""
Zerodha (Kite Connect) Data Provider
Provides real-time and historical market data from Zerodha
"""

import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from kiteconnect import KiteConnect
import pandas as pd
from functools import lru_cache
import json

logger = logging.getLogger(__name__)

class ZerodhaProvider:
    """
    Zerodha data provider for real-time and historical market data
    Uses Kite Connect API
    """
    
    def __init__(self):
        self.api_key = os.getenv('ZERODHA_API_KEY')
        self.api_secret = os.getenv('ZERODHA_API_SECRET')
        self.access_token = None
        
        if not self.api_key or not self.api_secret:
            logger.warning("⚠️  Zerodha API credentials not configured")
            self.kite = None
        else:
            self.kite = KiteConnect(api_key=self.api_key)
            
            # Try to load saved access token from file
            try:
                from pathlib import Path
                token_file = Path(__file__).parent.parent.parent / '.zerodha_token'
                if token_file.exists():
                    with open(token_file, 'r') as f:
                        saved_token = f.read().strip()
                        if saved_token:
                            self.access_token = saved_token
                            self.kite.set_access_token(saved_token)
                            logger.info("✅ Zerodha: Loaded saved access token")
                            # Load instruments
                            self.symbol_map = {}
                            self._load_instruments()
                            logger.info("✅ Zerodha Kite connected (authenticated)")
                            return
            except Exception as e:
                logger.debug(f"Note: Could not load saved token: {e}")
            
            logger.info("⚠️  Zerodha available but not authenticated yet")
        
        # Symbol mapping for easier lookups
        self.symbol_map = {}
    
    def _load_instruments(self):
        """Load instrument list for symbol lookups"""
        try:
            if self.kite and self.access_token:
                instruments = self.kite.instruments("NSE")
                self.symbol_map = {inst['tradingsymbol']: inst for inst in instruments}
                logger.info(f"✓ Loaded {len(self.symbol_map)} NSE instruments")
        except Exception as e:
            logger.error(f"Failed to load instruments: {e}")
    
    def generate_login_url(self) -> str:
        """Generate Zerodha login URL for user authentication"""
        if not self.kite:
            raise Exception("Zerodha not configured")
        return self.kite.login_url()
    
    def set_access_token_from_request_token(self, request_token: str) -> str:
        """
        Exchange request token for access token
        Call this after user logs in via the login URL
        """
        if not self.kite:
            raise Exception("Zerodha not configured")
        
        try:
            data = self.kite.generate_session(request_token, api_secret=self.api_secret)
            access_token = data['access_token']
            self.kite.set_access_token(access_token)
            self.access_token = access_token
            
            # Save to environment for persistence
            os.environ['ZERODHA_ACCESS_TOKEN'] = access_token
            
            # Reload instruments now that we're authenticated
            self._load_instruments()
            
            logger.info("✓ Zerodha authentication successful")
            return access_token
        except Exception as e:
            logger.error(f"Zerodha authentication failed: {e}")
            raise
    
    def is_authenticated(self) -> bool:
        """Check if Zerodha is authenticated and ready"""
        return self.kite is not None and self.access_token is not None
    
    def get_instrument_token(self, symbol: str, exchange: str = "NSE") -> Optional[int]:
        """Get instrument token for a symbol"""
        try:
            if symbol in self.symbol_map:
                return self.symbol_map[symbol]['instrument_token']
            
            # Try with exchange prefix
            full_symbol = f"{exchange}:{symbol}"
            if full_symbol in self.symbol_map:
                return self.symbol_map[full_symbol]['instrument_token']
            
            return None
        except Exception as e:
            logger.error(f"Error getting instrument token for {symbol}: {e}")
            return None
    
    def get_quote(self, symbols: List[str], exchange: str = "NSE") -> Dict[str, Any]:
        """
        Get real-time quotes for symbols
        
        Args:
            symbols: List of trading symbols (e.g., ['RELIANCE', 'TCS', 'INFY'])
            exchange: Exchange name (NSE, BSE, etc.)
        
        Returns:
            Dict with symbol quotes
        """
        if not self.is_authenticated():
            raise Exception("Zerodha not authenticated")
        
        try:
            # Format symbols with exchange prefix
            formatted_symbols = [f"{exchange}:{sym}" for sym in symbols]
            quotes = self.kite.quote(formatted_symbols)
            
            # Clean up response
            result = {}
            for key, data in quotes.items():
                symbol = key.split(':')[1] if ':' in key else key
                
                # Extract values
                last_price = data.get('last_price', 0)
                prev_close = data.get('ohlc', {}).get('close', 0)
                
                # Calculate percentage change if not provided or is 0
                change_pct = data.get('change', 0)
                if change_pct == 0 and prev_close and prev_close > 0 and last_price:
                    change_pct = ((last_price - prev_close) / prev_close) * 100
                
                result[symbol] = {
                    'price': last_price,
                    'open': data.get('ohlc', {}).get('open', 0),
                    'high': data.get('ohlc', {}).get('high', 0),
                    'low': data.get('ohlc', {}).get('low', 0),
                    'close': prev_close,
                    'volume': data.get('volume', 0),
                    'change_percent': round(change_pct, 2),
                    'timestamp': data.get('timestamp', datetime.now())
                }
            
            logger.info(f"✓ Fetched quotes for {len(result)} symbols")
            return result
        except Exception as e:
            logger.error(f"Error fetching quotes: {e}")
            raise
    
    def get_historical_data(
        self, 
        symbol: str, 
        from_date: datetime, 
        to_date: datetime,
        interval: str = "day",
        exchange: str = "NSE"
    ) -> Optional[pd.DataFrame]:
        """
        Get historical OHLC data
        
        Args:
            symbol: Trading symbol
            from_date: Start date
            to_date: End date
            interval: Candle interval (minute, day, 3minute, 5minute, 10minute, 15minute, 30minute, 60minute)
            exchange: Exchange name
        
        Returns:
            DataFrame with OHLC data
        """
        if not self.is_authenticated():
            raise Exception("Zerodha not authenticated")
        
        try:
            instrument_token = self.get_instrument_token(symbol, exchange)
            if not instrument_token:
                logger.error(f"Instrument token not found for {symbol}")
                return None
            
            data = self.kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_date,
                to_date=to_date,
                interval=interval
            )
            
            if not data:
                return None
            
            df = pd.DataFrame(data)
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
            
            logger.info(f"✓ Fetched {len(df)} candles for {symbol}")
            return df
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {e}")
            return None
    
    def get_ohlc_latest(self, symbols: List[str], exchange: str = "NSE") -> Dict[str, Any]:
        """
        Get latest OHLC data for symbols
        Useful for technical analysis
        """
        if not self.is_authenticated():
            raise Exception("Zerodha not authenticated")
        
        try:
            formatted_symbols = [f"{exchange}:{sym}" for sym in symbols]
            ohlc_data = self.kite.ohlc(formatted_symbols)
            
            result = {}
            for key, data in ohlc_data.items():
                symbol = key.split(':')[1] if ':' in key else key
                ohlc = data.get('ohlc', {})
                result[symbol] = {
                    'open': ohlc.get('open', 0),
                    'high': ohlc.get('high', 0),
                    'low': ohlc.get('low', 0),
                    'close': ohlc.get('close', 0),
                    'last_price': data.get('last_price', 0),
                    'volume': data.get('volume', 0)
                }
            
            return result
        except Exception as e:
            logger.error(f"Error fetching OHLC data: {e}")
            raise
    
    def get_instruments_by_exchange(self, exchange: str = "NSE") -> List[Dict]:
        """Get all instruments for an exchange"""
        if not self.is_authenticated():
            raise Exception("Zerodha not authenticated")
        
        try:
            instruments = self.kite.instruments(exchange)
            return instruments
        except Exception as e:
            logger.error(f"Error fetching instruments: {e}")
            raise
    
    def get_indices_quote(self) -> Dict[str, Any]:
        """Get quotes for major indices (NIFTY 50, BANK NIFTY, etc.)"""
        indices = [
            "NIFTY 50",
            "NIFTY BANK",
            "NIFTY IT",
            "NIFTY PHARMA",
            "NIFTY AUTO"
        ]
        
        try:
            return self.get_quote(indices, exchange="NSE")
        except:
            return {}
    
    def get_option_chain(self, symbol: str, exchange: str = "NFO") -> List[Dict]:
        """
        Get option chain for a symbol
        
        Args:
            symbol: Underlying symbol (e.g., 'NIFTY', 'BANKNIFTY')
            exchange: Exchange (typically NFO for options)
        
        Returns:
            List of option contracts
        """
        if not self.is_authenticated():
            raise Exception("Zerodha not authenticated")
        
        try:
            instruments = self.kite.instruments(exchange)
            
            # Filter for the specific symbol
            options = [
                inst for inst in instruments 
                if inst['name'] == symbol and inst['instrument_type'] in ['CE', 'PE']
            ]
            
            logger.info(f"✓ Found {len(options)} option contracts for {symbol}")
            return options
        except Exception as e:
            logger.error(f"Error fetching option chain for {symbol}: {e}")
            raise
    
    def get_market_status(self) -> Dict[str, Any]:
        """Get market status and timings (IST-based)."""
        try:
            # Kite doesn't have a direct market status API; derive status from
            # Indian cash market hours using IST (UTC+5:30) so behaviour is
            # independent of server timezone.
            now_ist = datetime.utcnow() + timedelta(hours=5, minutes=30)

            # Check if it's a weekday (Mon-Fri)
            is_weekday = now_ist.weekday() < 5

            # Indian market hours: 9:15 AM - 3:30 PM IST
            market_open_time = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
            market_close_time = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)

            is_trading_hours = market_open_time <= now_ist <= market_close_time
            is_market_open = is_weekday and is_trading_hours

            return {
                'is_open': is_market_open,
                'is_weekday': is_weekday,
                'is_trading_hours': is_trading_hours,
                'current_time': now_ist,
                'market_open_time': market_open_time if is_weekday else None,
                'market_close_time': market_close_time if is_weekday else None
            }
        except Exception as e:
            logger.error(f"Error checking market status: {e}")
            return {'is_open': False}


# Global instance
_zerodha_provider = None

def get_zerodha_provider() -> ZerodhaProvider:
    """Get or create Zerodha provider instance"""
    global _zerodha_provider
    if _zerodha_provider is None:
        _zerodha_provider = ZerodhaProvider()
    return _zerodha_provider
