#!/usr/bin/env python3
"""
Test Yahoo Finance integration
"""

import yfinance as yf
import pandas as pd

print("Testing yfinance library...")
print("="*60)

# Test RELIANCE
symbol = "RELIANCE.NS"
print(f"\nFetching {symbol}...")

try:
    ticker = yf.Ticker(symbol)
    df = ticker.history(period='3mo', interval='1d')
    
    print(f"✅ Success! Retrieved {len(df)} rows")
    print(f"\nFirst 5 rows:")
    print(df.head())
    
    print(f"\nLast 5 rows:")
    print(df.tail())
    
    print(f"\nColumns: {list(df.columns)}")
    print(f"Date range: {df.index.min()} to {df.index.max()}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# Test NIFTY
print("\n" + "="*60)
symbol = "^NSEI"
print(f"\nFetching {symbol}...")

try:
    ticker = yf.Ticker(symbol)
    df = ticker.history(period='1mo', interval='1d')
    
    print(f"✅ Success! Retrieved {len(df)} rows")
    print(f"\nFirst 3 rows:")
    print(df.head(3))
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
print("Test complete!")
