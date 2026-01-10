"""
Chart Data Router
Provides OHLCV data and AI signals for chart visualization
Integrates with real data sources: Zerodha, NSE, Yahoo Finance, etc.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime, timedelta
from ..services.chart_data_service import chart_data_service
from ..providers.unified_data_provider import UnifiedDataProvider

router = APIRouter(tags=["chart"])
unified_provider = UnifiedDataProvider()


def generate_mock_candles(symbol: str, timeframe: str = '3M'):
    """
    Generate mock candlestick data for chart
    In production, fetch from Yahoo Finance or your data provider
    """
    
    # Determine number of candles based on timeframe
    days_map = {
        '1M': 30,
        '3M': 90,
        '6M': 180,
        '1Y': 365
    }
    
    days = days_map.get(timeframe, 90)
    
    # Generate realistic candles
    candles = []
    base_price = 2500 if 'NIFTY' in symbol else random.randint(500, 3000)
    current_price = base_price
    
    start_date = datetime.now() - timedelta(days=days)
    
    for i in range(days):
        date = start_date + timedelta(days=i)
        
        # Skip weekends
        if date.weekday() >= 5:
            continue
        
        # Random daily movement
        daily_change = random.uniform(-2, 2) / 100
        open_price = current_price
        close_price = current_price * (1 + daily_change)
        
        high_price = max(open_price, close_price) * random.uniform(1.001, 1.015)
        low_price = min(open_price, close_price) * random.uniform(0.985, 0.999)
        
        volume = random.randint(1000000, 10000000)
        
        candles.append({
            'time': int(date.timestamp()),
            'open': round(open_price, 2),
            'high': round(high_price, 2),
            'low': round(low_price, 2),
            'close': round(close_price, 2),
            'volume': volume
        })
        
        current_price = close_price
    
    return candles, current_price


def generate_ai_signals(symbol: str, candles: list):
    """
    Generate AI-detected signals for chart markers
    In production, these come from your AI agents
    """
    
    signals = []
    
    # Generate 3-5 signals across the timeframe
    num_signals = random.randint(3, 5)
    signal_indices = random.sample(range(len(candles) - 10, len(candles)), num_signals)
    
    signal_types = [
        {'type': 'bullish', 'text': 'MACD Bullish Crossover'},
        {'type': 'bullish', 'text': 'Resistance Breakout'},
        {'type': 'bullish', 'text': 'Support Bounce'},
        {'type': 'bullish', 'text': 'Volume Surge'},
        {'type': 'bearish', 'text': 'Overbought RSI'},
        {'type': 'bearish', 'text': 'Support Breakdown'},
    ]
    
    for idx in sorted(signal_indices):
        signal = random.choice(signal_types)
        signals.append({
            'time': candles[idx]['time'],
            'type': signal['type'],
            'text': signal['text'],
            'price': candles[idx]['close']
        })
    
    return signals


@router.get("/chart/{symbol}")
async def get_chart_data(
    symbol: str,
    timeframe: Optional[str] = '3M'
):
    """
    Get chart data with AI signals from real data sources.
    
    Data Sources (in priority order):
    1. Zerodha Kite API (real-time, requires auth)
    2. NSE India (free, delayed)
    3. Yahoo Finance (global, free)
    4. Alpha Vantage (free tier)
    5. Finnhub (free tier)
    6. Mock data (fallback)
    
    Returns:
    - OHLCV candles
    - AI-detected signals
    - Current price info
    - Data source used
    """
    
    try:
        # Fetch chart data from best available source
        chart_data = await chart_data_service.fetch_chart_data(symbol, timeframe)
        
        if not chart_data or not chart_data.get('candles'):
            raise HTTPException(status_code=404, detail="No chart data available")
        
        return chart_data
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Chart data error: {str(e)}"
        )


@router.get("/chart/{symbol}/pattern")
async def detect_patterns(symbol: str):
    """
    Pattern Recognition Agent - Detect chart patterns
    Coming in Week 4-5 implementation
    """
    
    return {
        'symbol': symbol,
        'patterns': [
            {
                'name': 'Ascending Triangle',
                'probability': 0.72,
                'target': 2650,
                'timeframe': 'forming',
                'status': 'active'
            }
        ],
        'message': 'Pattern Recognition Agent - Coming Soon!'
    }


@router.get("/chart/historical")
async def get_historical_data(
    symbol: str = Query(..., description="Stock symbol (e.g., RELIANCE, TCS, INFY)"),
    days: int = Query(30, ge=1, le=365, description="Number of days of historical data"),
    interval: str = Query("1d", description="Data interval (1m, 5m, 15m, 1h, 1d)")
):
    """
    Get historical OHLC data with intelligent caching
    
    Features:
    - Automatic caching for faster subsequent requests
    - Zerodha PRIMARY source (real-time)
    - Yahoo Finance fallback
    - Smart cache TTL based on interval
    
    Args:
        symbol: Stock symbol
        days: Number of days (1-365)
        interval: Data interval (1m, 5m, 15m, 1h, 1d)
        
    Returns:
        Historical OHLC data with metadata
    """
    try:
        # Calculate date range
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days)
        
        # Fetch data (with caching)
        df = unified_provider.get_historical_data(
            symbol=symbol,
            from_date=from_date,
            to_date=to_date,
            interval=interval,
            use_cache=True
        )
        
        if df is None or df.empty:
            return {
                "status": "no_data",
                "symbol": symbol,
                "message": "No historical data available",
                "data": []
            }
        
        # Convert DataFrame to list of dicts
        data = []
        for idx, row in df.iterrows():
            # Handle timestamp
            if 'time' in df.columns:
                time_val = row['time']
            else:
                time_val = idx
            
            # Convert to ISO format
            if hasattr(time_val, 'isoformat'):
                time_str = time_val.isoformat()
            else:
                time_str = str(time_val)
            
            data.append({
                "time": time_str,
                "open": float(row.get('open', row.get('Open', 0))),
                "high": float(row.get('high', row.get('High', 0))),
                "low": float(row.get('low', row.get('Low', 0))),
                "close": float(row.get('close', row.get('Close', 0))),
                "volume": int(row.get('volume', row.get('Volume', 0)))
            })
        
        return {
            "status": "success",
            "symbol": symbol,
            "interval": interval,
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "data_points": len(data),
            "data": data,
            "cached": True  # Will be from cache on subsequent calls
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching historical data: {str(e)}"
        )


@router.get("/chart/market-regime")
async def get_market_regime():
    """
    Market Regime Agent - Detect bull/bear/sideways market
    Coming in Week 4-5 implementation
    """
    
    import random
    regimes = ['bull', 'bear', 'sideways', 'high-volatility']
    current_regime = random.choice(regimes)
    
    return {
        'regime': current_regime,
        'confidence': random.uniform(0.6, 0.9),
        'characteristics': {
            'trend': 'upward' if current_regime == 'bull' else 'downward',
            'volatility': 'high' if current_regime == 'high-volatility' else 'moderate',
            'volume': 'above_average'
        },
        'recommendation': 'Adapt position sizing and strategy based on regime',
        'message': 'Market Regime Agent - Coming Soon!'
    }
