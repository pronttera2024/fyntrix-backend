"""
Zerodha Market Data Router
Real-time and historical market data endpoints
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List
from datetime import datetime, timedelta
from ..services.zerodha_service import zerodha_service

router = APIRouter()


@router.get("/zerodha/test")
async def test_zerodha_connection():
    """
    Test Zerodha API connection and credentials.
    
    Returns:
        Connection status and configuration
    """
    try:
        # Check if kiteconnect is available
        if not zerodha_service.kite:
            return {
                "status": "error",
                "message": "KiteConnect library not initialized",
                "authenticated": False
            }
        
        # Check authentication status
        is_authenticated = zerodha_service.access_token is not None
        
        return {
            "status": "success",
            "message": "Zerodha API configured successfully",
            "authenticated": is_authenticated,
            "api_key_present": bool(zerodha_service.api_key),
            "api_secret_present": bool(zerodha_service.api_secret),
            "kite_initialized": zerodha_service.kite is not None,
            "next_step": "Call /v1/zerodha/login-url to authenticate" if not is_authenticated else "Ready to fetch market data"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test failed: {str(e)}")


@router.get("/zerodha/quote")
async def get_quote(symbols: str = Query(..., description="Comma-separated symbols (e.g., NSE:RELIANCE,NSE:TCS)")):
    """
    Get real-time quotes for symbols.
    
    Args:
        symbols: Comma-separated list of symbols with exchange (NSE:SYMBOL)
        
    Returns:
        Quote data with LTP, OHLC, volume
    """
    if not zerodha_service.access_token:
        raise HTTPException(status_code=401, detail="Not authenticated. Call /zerodha/login-url first")
    
    try:
        symbol_list = [s.strip() for s in symbols.split(',')]
        quotes = zerodha_service.get_quote(symbol_list)
        
        return {
            "status": "success",
            "data": quotes
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quote fetch failed: {str(e)}")


@router.get("/zerodha/ltp")
async def get_ltp(symbols: str = Query(..., description="Comma-separated symbols (e.g., NSE:RELIANCE,NSE:TCS)")):
    """
    Get Last Traded Price (LTP) for symbols.
    
    Args:
        symbols: Comma-separated list of symbols with exchange
        
    Returns:
        Dict of symbol: LTP
    """
    if not zerodha_service.access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        symbol_list = [s.strip() for s in symbols.split(',')]
        ltp_data = zerodha_service.get_ltp(symbol_list)
        
        return {
            "status": "success",
            "data": ltp_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LTP fetch failed: {str(e)}")


@router.get("/zerodha/historical")
async def get_historical_data(
    symbol: str = Query(..., description="Symbol (e.g., RELIANCE)"),
    days: int = Query(30, description="Number of days of history"),
    interval: str = Query("day", description="Interval: minute, day, 15minute, 60minute")
):
    """
    Get historical OHLC data for a symbol.
    
    Args:
        symbol: Trading symbol (without exchange)
        days: Number of days of historical data
        interval: Candle interval
        
    Returns:
        Historical OHLCV data
    """
    if not zerodha_service.access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days)
        
        df = await zerodha_service.get_historical_data(
            symbol=symbol,
            from_date=from_date,
            to_date=to_date,
            interval=interval
        )
        
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"No data found for {symbol}")
        
        # Convert DataFrame to list of dicts
        data = df.to_dict('records')
        
        return {
            "status": "success",
            "symbol": symbol,
            "interval": interval,
            "from": from_date.strftime("%Y-%m-%d"),
            "to": to_date.strftime("%Y-%m-%d"),
            "candles": len(data),
            "data": data
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Historical data fetch failed: {str(e)}")


@router.get("/zerodha/holdings")
async def get_holdings():
    """
    Get user's holdings (long-term investments).
    
    Returns:
        List of holdings with P&L
    """
    if not zerodha_service.access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        holdings = zerodha_service.get_holdings()
        
        return {
            "status": "success",
            "count": len(holdings),
            "data": holdings
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Holdings fetch failed: {str(e)}")


@router.get("/zerodha/positions")
async def get_positions():
    """
    Get user's current positions (open trades).
    
    Returns:
        Current positions with P&L
    """
    if not zerodha_service.access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        positions = zerodha_service.get_positions()
        
        return {
            "status": "success",
            "data": positions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Positions fetch failed: {str(e)}")


@router.get("/zerodha/orders")
async def get_orders():
    """
    Get all orders for the day.
    
    Returns:
        List of orders
    """
    if not zerodha_service.access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        orders = zerodha_service.get_orders()
        
        return {
            "status": "success",
            "count": len(orders),
            "data": orders
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Orders fetch failed: {str(e)}")
