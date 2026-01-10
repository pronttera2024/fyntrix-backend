"""
Real-time price data service using Zerodha
Fetches current prices and intraday movements for stocks
"""

import logging
from typing import Dict, List, Optional
from ..providers import get_data_provider

logger = logging.getLogger(__name__)


async def enrich_picks_with_realtime_data(picks: List[Dict]) -> List[Dict]:
    """
    Enrich picks with real-time price data from Zerodha
    
    Adds:
    - last_price: Current trading price
    - prev_close: Previous day's close
    - intraday_change_pct: Today's % change
    - open: Today's open price
    - high: Today's high
    - low: Today's low
    - volume: Trading volume
    
    Args:
        picks: List of pick dictionaries with 'symbol' field
        
    Returns:
        Same picks enriched with realtime data
    """
    if not picks:
        return picks
    
    try:
        # Get symbols
        symbols = [p.get('symbol') for p in picks if p.get('symbol')]
        if not symbols:
            return picks
        
        logger.info(f"🔄 Fetching real-time data for {len(symbols)} symbols...")
        
        # Get unified provider (Zerodha first, Yahoo fallback)
        provider = get_data_provider()
        
        # Fetch quotes
        quotes = provider.get_quote(symbols)
        
        logger.info(f"✅ Fetched real-time data for {len(quotes)} symbols")
        
        # Enrich picks
        enriched_count = 0
        for pick in picks:
            symbol = pick.get('symbol')
            if symbol and symbol in quotes:
                quote = quotes[symbol]
                
                # Extract data
                last_price = quote.get('price', 0)
                prev_close = quote.get('close', 0)
                open_price = quote.get('open', 0)
                high_price = quote.get('high', 0)
                low_price = quote.get('low', 0)
                volume = quote.get('volume', 0)

                # Calculate intraday change.
                # Prefer provider's own change_percent (which is already
                # correctly computed for both Zerodha and Yahoo), and only
                # fall back to last_price vs prev_close when that is
                # unavailable. This avoids the Yahoo-specific bug where
                # price == close and we were always returning 0.0%.
                change_pct = quote.get('change_percent')
                intraday_change_pct = 0.0
                try:
                    if isinstance(change_pct, (int, float)):
                        intraday_change_pct = float(change_pct)
                    elif prev_close and prev_close > 0 and last_price:
                        intraday_change_pct = ((last_price - prev_close) / prev_close) * 100
                except Exception:
                    intraday_change_pct = 0.0
                
                # Add to pick
                pick['last_price'] = round(last_price, 2)
                pick['current_price'] = round(last_price, 2)
                pick['prev_close'] = round(prev_close, 2)
                pick['intraday_change_pct'] = round(intraday_change_pct, 2)
                pick['open'] = round(open_price, 2)
                pick['high'] = round(high_price, 2)
                pick['low'] = round(low_price, 2)
                pick['volume'] = volume

                # Normalise data source label (Zerodha vs Yahoo Finance)
                try:
                    src = str(provider.get_data_source()).lower()
                except Exception:
                    src = ''
                pick['price_data_source'] = 'Zerodha' if 'zerodha' in src else 'Yahoo Finance'
                
                enriched_count += 1
                
                logger.debug(f"  {symbol}: ₹{last_price} ({intraday_change_pct:+.2f}%)")
        
        logger.info(f"✅ Enriched {enriched_count}/{len(picks)} picks with real-time data")
        
    except Exception as e:
        logger.error(f"❌ Failed to enrich picks with realtime data: {e}")
        # Don't fail the whole operation - return picks as-is
    
    return picks


async def get_indices_realtime() -> Dict[str, Dict]:
    """
    Get real-time data for major indices
    
    Returns dict with:
    - NIFTY 50
    - NIFTY BANK
    - USD/INR
    - GOLD
    """
    indices_map = {
        'NIFTY50': 'NIFTY 50',
        'BANKNIFTY': 'NIFTY BANK',
    }
    
    try:
        provider = get_data_provider()
        
        # For Zerodha, use index symbols
        if provider.get_data_source() == 'zerodha':
            # Zerodha uses special instrument tokens for indices
            # This would need to be implemented in zerodha_provider
            pass
        
        # For now, return basic structure
        # Full implementation would fetch from Zerodha or Yahoo
        return {}
        
    except Exception as e:
        logger.error(f"Failed to get indices realtime: {e}")
        return {}


def get_price_summary(pick: Dict) -> str:
    """
    Get human-readable price summary for a pick
    
    Args:
        pick: Pick dictionary with price fields
        
    Returns:
        String like "₹1,245.30 ↑ 2.15% (from ₹1,219.10)"
    """
    try:
        last_price = pick.get('last_price', 0)
        intraday_change_pct = pick.get('intraday_change_pct', 0)
        prev_close = pick.get('prev_close', 0)
        
        arrow = "↑" if intraday_change_pct >= 0 else "↓"
        sign = "+" if intraday_change_pct >= 0 else ""
        
        return f"₹{last_price:,.2f} {arrow} {sign}{intraday_change_pct:.2f}% (from ₹{prev_close:,.2f})"
    except:
        return "Price data unavailable"
