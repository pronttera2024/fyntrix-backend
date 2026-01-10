#!/usr/bin/env python3
"""
Test ChartDataService
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from app.services.chart_data_service import ChartDataService

async def main():
    print("Testing ChartDataService...")
    print("="*80)
    
    service = ChartDataService()
    
    # Test with RELIANCE
    symbol = "RELIANCE"
    timeframe = "1M"
    
    print(f"\nFetching {symbol} / {timeframe}...")
    print("-"*80)
    
    try:
        result = await service.fetch_chart_data(symbol, timeframe)
        
        print(f"\nSUCCESS!")
        print(f"Data Source: {result.get('data_source')}")
        print(f"Candles: {len(result.get('candles', []))}")
        print(f"Signals: {len(result.get('signals', []))}")
        print(f"Current Price: {result.get('current', {}).get('price')}")
        
        if result.get('candles'):
            first_candle = result['candles'][0]
            last_candle = result['candles'][-1]
            print(f"\nFirst Candle: time={first_candle.get('time')}, close={first_candle.get('close')}")
            print(f"Last Candle: time={last_candle.get('time')}, close={last_candle.get('close')}")
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*80)
    print("Test complete!")

if __name__ == '__main__':
    asyncio.run(main())
