"""
Zerodha Kite Connect Integration
Live broker connection for ARISE trading platform
"""

import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    from kiteconnect import KiteConnect
    KITE_AVAILABLE = True
except ImportError:
    KITE_AVAILABLE = False
    print("WARNING: kiteconnect not installed. Run: pip install kiteconnect")


class ZerodhaService:
    """
    Zerodha Kite Connect service for live trading and market data.
    
    Capabilities:
    - User authentication
    - Real-time market data (with restrictions)
    - Historical data
    - Order placement
    - Portfolio management
    """
    
    def __init__(self):
        if not KITE_AVAILABLE:
            print("WARNING: kiteconnect not installed. Install with: pip install kiteconnect")
            return
        
        self.api_key = os.getenv('ZERODHA_API_KEY', '')
        self.api_secret = os.getenv('ZERODHA_API_SECRET', '')
        # Public redirect URL used in OAuth/login flows (for tests and UI helpers)
        self.redirect_url = os.getenv(
            'ZERODHA_REDIRECT_URL',
            'https://arise-trading.vercel.app/auth/callback',
        )
        
        if not self.api_key or not self.api_secret:
            print("WARNING: ZERODHA_API_KEY or ZERODHA_API_SECRET not set in environment")
            self.kite = None
            self.access_token = None
            return
        
        self.kite = KiteConnect(api_key=self.api_key)
        self.access_token = None
        self.instruments_cache = {}  # Cache for instrument tokens
        
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
                        print(f"[OK] Zerodha: Loaded saved access token")
                        # Load instruments dynamically
                        self._load_instruments()
                        return
        except Exception as e:
            print(f"Note: Could not load saved token: {e}")
        
        print(f"[OK] Zerodha service initialized (not authenticated yet)")
    
    def get_login_url(self) -> str:
        """
        Generate login URL for user authentication.
        
        Returns:
            Login URL to redirect user to
        """
        if not self.kite:
            raise RuntimeError("KiteConnect not available")
        
        login_url = self.kite.login_url()
        print(f"\n[AUTH] Zerodha Login URL generated")
        print(f"[INFO] Redirect user to: {login_url}")
        return login_url
    
    def generate_session(self, request_token: str) -> Dict[str, Any]:
        """
        Generate session using request token from callback.
        
        Args:
            request_token: Token received in callback URL
            
        Returns:
            Session data with access_token
        """
        if not self.kite:
            raise RuntimeError("KiteConnect not available")
        
        try:
            # Generate session
            data = self.kite.generate_session(
                request_token=request_token,
                api_secret=self.api_secret
            )
            
            # Store access token
            self.access_token = data["access_token"]
            self.kite.set_access_token(self.access_token)
            
            print(f"[OK] Session generated successfully")
            print(f"[USER] User: {data.get('user_name', 'Unknown')}")
            print(f"[EMAIL] Email: {data.get('email', 'Unknown')}")
            
            # Load instruments after authentication
            self._load_instruments()
            
            return data
            
        except Exception as e:
            print(f"[ERROR] Session generation failed: {e}")
            raise
    
    def set_access_token(self, access_token: str):
        """
        Set access token manually (if stored).
        
        Args:
            access_token: Previously generated access token
        """
        if not self.kite:
            raise RuntimeError("KiteConnect not available")
        
        self.access_token = access_token
        self.kite.set_access_token(access_token)
        print(f"[OK] Access token set")
    
    # ==================== Market Data ====================
    
    def get_quote(self, symbols: List[str]) -> Dict[str, Any]:
        """
        Get real-time quote for symbols.
        
        Args:
            symbols: List of symbols (e.g., ["NSE:RELIANCE", "NSE:TCS"])
            
        Returns:
            Quote data with LTP, OHLC, volume
        """
        if not self.kite or not self.access_token:
            raise RuntimeError("Not authenticated. Call generate_session() first")
        
        try:
            quotes = self.kite.quote(symbols)
            print(f"✅ Quotes fetched for {len(symbols)} symbols")
            return quotes
            
        except Exception as e:
            print(f"❌ Quote fetch failed: {e}")
            raise
    
    def get_ltp(self, symbols: List[str]) -> Dict[str, float]:
        """
        Get Last Traded Price (LTP) for symbols.
        
        Args:
            symbols: List of symbols
            
        Returns:
            Dict of symbol: LTP
        """
        if not self.kite or not self.access_token:
            raise RuntimeError("Not authenticated")
        
        try:
            ltp_data = self.kite.ltp(symbols)
            
            # Extract just the LTP values
            result = {}
            for symbol, data in ltp_data.items():
                result[symbol] = data.get('last_price', 0)
            
            print(f"✅ LTP fetched for {len(symbols)} symbols")
            return result
            
        except Exception as e:
            print(f"❌ LTP fetch failed: {e}")
            raise
    
    def _load_instruments(self):
        """
        Load all NSE instruments dynamically from Zerodha.
        This replaces the hardcoded INSTRUMENT_TOKENS mapping.
        """
        if not self.kite or not self.access_token:
            print("  Zerodha: Cannot load instruments - not authenticated")
            return
        
        try:
            import asyncio
            
            # Fetch all NSE instruments
            instruments = self.kite.instruments("NSE")
            
            # Build symbol -> instrument_token mapping
            self.instruments_cache = {}
            for inst in instruments:
                symbol = inst['tradingsymbol']
                self.instruments_cache[symbol] = inst['instrument_token']
            
            print(f"  [OK] Loaded {len(self.instruments_cache)} NSE instruments")
            print(f"  [OK] Zerodha ready for all NSE stocks")
            
        except Exception as e:
            print(f"  [WARN] Failed to load instruments: {e}")
            # Fallback to hardcoded popular symbols if loading fails
            self.instruments_cache = {
                'RELIANCE': 738561,
                'TCS': 2953217,
                'HDFCBANK': 341249,
                'INFY': 408065,
                'ICICIBANK': 1270529,
                'SBIN': 779521,
                'BHARTIARTL': 2714625,
                'ITC': 424961,
                'KOTAKBANK': 492033,
                'LT': 2939649,
                'AXISBANK': 1510401,
                'ASIANPAINT': 60417,
                'MARUTI': 2815745,
                'SUNPHARMA': 857857,
                'TITAN': 897537,
                'ULTRACEMCO': 2952193,
                'BAJFINANCE': 81153,
                'WIPRO': 969473,
                'POWERGRID': 3834113,
                'NTPC': 2977281,
            }
            print(f"  [OK] Using fallback: {len(self.instruments_cache)} hardcoded symbols")
    
    async def get_historical_data(
        self,
        symbol: str,
        from_date: datetime,
        to_date: datetime,
        interval: str = "day"
    ) -> Optional[Any]:
        """
        Get historical OHLC data for a symbol.
        
        Args:
            symbol: Stock symbol (e.g., 'RELIANCE', 'TCS')
            from_date: Start date
            to_date: End date
            interval: "minute", "day", "15minute", "60minute", etc.
            
        Returns:
            DataFrame with time, open, high, low, close, volume
        """
        if not self.kite or not self.access_token:
            print("  Zerodha: Not authenticated")
            return None
        
        # Get instrument token for symbol
        instrument_token = self.instruments_cache.get(symbol.upper())
        if not instrument_token:
            print(f"  Zerodha: Unknown symbol {symbol}")
            if len(self.instruments_cache) < 50:
                print(f"  Available: {', '.join(list(self.instruments_cache.keys())[:10])}...")
            return None
        
        try:
            import asyncio
            import pandas as pd
            
            # Run synchronous kite call in thread pool
            def fetch_sync():
                return self.kite.historical_data(
                    instrument_token=instrument_token,
                    from_date=from_date,
                    to_date=to_date,
                    interval=interval
                )
            
            data = await asyncio.to_thread(fetch_sync)
            
            if not data:
                print(f"  Zerodha: No data returned for {symbol}")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(data)

            # Rename columns to match our format
            df = df.rename(columns={
                'date': 'time'
            })

            # Normalize to timezone-aware IST for Indian markets
            if 'time' in df.columns:
                df['time'] = pd.to_datetime(df['time'])
                if df['time'].dt.tz is None:
                    df['time'] = df['time'].dt.tz_localize('Asia/Kolkata')
                else:
                    df['time'] = df['time'].dt.tz_convert('Asia/Kolkata')

                # For intraday intervals, restrict to NSE/BSE regular trading hours
                intraday_intervals = {"minute", "3minute", "5minute", "10minute", "15minute", "30minute", "60minute"}
                if interval in intraday_intervals:
                    df = df[
                        (df['time'].dt.weekday < 5)
                        & (df['time'].dt.time >= time(9, 0))
                        & (df['time'].dt.time <= time(15, 30))
                    ]

                # Convert IST datetimes to UTC Unix timestamp seconds for downstream consumers
                df['time'] = df['time'].dt.tz_convert('UTC').astype('int64') // 10**9

            print(f"  Zerodha: Fetched {len(df)} candles for {symbol}")
            return df[['time', 'open', 'high', 'low', 'close', 'volume']]
            
        except Exception as e:
            print(f"❌ Historical data fetch failed: {e}")
            raise
    
    # ==================== Order Management ====================
    
    def place_order(
        self,
        symbol: str,
        exchange: str,
        transaction_type: str,
        quantity: int,
        order_type: str = "MARKET",
        product: str = "CNC",
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        validity: str = "DAY"
    ) -> str:
        """
        Place an order.
        
        Args:
            symbol: Trading symbol (e.g., "RELIANCE")
            exchange: "NSE" or "BSE"
            transaction_type: "BUY" or "SELL"
            quantity: Number of shares
            order_type: "MARKET", "LIMIT", "SL", "SL-M"
            product: "CNC" (delivery), "MIS" (intraday), "NRML" (F&O)
            price: Limit price (for LIMIT orders)
            trigger_price: Trigger price (for SL orders)
            validity: "DAY", "IOC"
            
        Returns:
            Order ID
        """
        if not self.kite or not self.access_token:
            raise RuntimeError("Not authenticated")
        
        try:
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=symbol,
                transaction_type=transaction_type,
                quantity=quantity,
                product=product,
                order_type=order_type,
                price=price,
                trigger_price=trigger_price,
                validity=validity
            )
            
            print(f"✅ Order placed successfully")
            print(f"📝 Order ID: {order_id}")
            print(f"📊 {transaction_type} {quantity} {symbol} @ {order_type}")
            
            return order_id
            
        except Exception as e:
            print(f"❌ Order placement failed: {e}")
            raise
    
    def get_orders(self) -> List[Dict[str, Any]]:
        """
        Get all orders for the day.
        
        Returns:
            List of orders
        """
        if not self.kite or not self.access_token:
            raise RuntimeError("Not authenticated")
        
        try:
            orders = self.kite.orders()
            print(f"✅ Orders fetched: {len(orders)} orders")
            return orders
            
        except Exception as e:
            print(f"❌ Order fetch failed: {e}")
            raise
    
    def cancel_order(self, order_id: str, variety: str = "regular") -> str:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID to cancel
            variety: Order variety
            
        Returns:
            Order ID of cancelled order
        """
        if not self.kite or not self.access_token:
            raise RuntimeError("Not authenticated")
        
        try:
            result = self.kite.cancel_order(
                variety=variety,
                order_id=order_id
            )
            
            print(f"✅ Order cancelled: {order_id}")
            return result
            
        except Exception as e:
            print(f"❌ Order cancellation failed: {e}")
            raise
    
    # ==================== Portfolio ====================
    
    def get_positions(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get current positions (open positions).
        
        Returns:
            Dict with 'net' and 'day' positions
        """
        if not self.kite or not self.access_token:
            raise RuntimeError("Not authenticated")
        
        try:
            positions = self.kite.positions()
            print(f"✅ Positions fetched")
            return positions
            
        except Exception as e:
            print(f"❌ Positions fetch failed: {e}")
            raise
    
    def get_holdings(self) -> List[Dict[str, Any]]:
        """
        Get holdings (long-term investments).
        
        Returns:
            List of holdings
        """
        if not self.kite or not self.access_token:
            raise RuntimeError("Not authenticated")
        
        try:
            holdings = self.kite.holdings()
            print(f"✅ Holdings fetched: {len(holdings)} holdings")
            return holdings
            
        except Exception as e:
            print(f"❌ Holdings fetch failed: {e}")
            raise
    
    # ==================== Instruments ====================
    
    def get_instruments(self, exchange: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get list of all instruments.
        
        Args:
            exchange: Optional exchange filter ("NSE", "BSE", etc.)
            
        Returns:
            List of instruments with tokens and details
        """
        if not self.kite:
            raise RuntimeError("KiteConnect not available")
        
        try:
            instruments = self.kite.instruments(exchange)
            print(f"✅ Instruments fetched: {len(instruments)} instruments")
            return instruments
            
        except Exception as e:
            print(f"❌ Instruments fetch failed: {e}")
            raise
    
    def search_instruments(self, query: str, exchange: str = "NSE") -> List[Dict[str, Any]]:
        """
        Search for instruments by name.
        
        Args:
            query: Search query (e.g., "RELIANCE")
            exchange: Exchange to search in
            
        Returns:
            List of matching instruments
        """
        try:
            instruments = self.get_instruments(exchange)
            
            # Filter by query
            query_upper = query.upper()
            results = [
                inst for inst in instruments
                if query_upper in inst.get('tradingsymbol', '').upper()
                or query_upper in inst.get('name', '').upper()
            ]
            
            print(f"✅ Found {len(results)} instruments matching '{query}'")
            return results[:10]  # Return top 10
            
        except Exception as e:
            print(f"❌ Instrument search failed: {e}")
            raise


# Global instance
zerodha_service = ZerodhaService()


# Convenience functions
def get_live_price(symbol: str, exchange: str = "NSE") -> Optional[float]:
    """
    Get live price for a symbol.
    
    Args:
        symbol: Trading symbol
        exchange: Exchange
        
    Returns:
        LTP or None if not available
    """
    try:
        full_symbol = f"{exchange}:{symbol}"
        ltp_data = zerodha_service.get_ltp([full_symbol])
        return ltp_data.get(full_symbol)
    except:
        return None


def place_market_order(
    symbol: str,
    transaction_type: str,
    quantity: int,
    product: str = "CNC"
) -> Optional[str]:
    """
    Place a market order (convenience function).
    
    Args:
        symbol: Trading symbol
        transaction_type: "BUY" or "SELL"
        quantity: Number of shares
        product: "CNC" or "MIS"
        
    Returns:
        Order ID or None
    """
    try:
        order_id = zerodha_service.place_order(
            symbol=symbol,
            exchange="NSE",
            transaction_type=transaction_type,
            quantity=quantity,
            order_type="MARKET",
            product=product
        )
        return order_id
    except:
        return None
