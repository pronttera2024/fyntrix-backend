"""
Test Zerodha Integration
Comprehensive test of Zerodha data provider and unified data flow
"""

import os
import asyncio
from datetime import datetime, timedelta

# Set environment variables for testing
os.environ['ZERODHA_API_KEY'] = 'wialyvtiwscm10th'
os.environ['ZERODHA_API_SECRET'] = '2f1k69xaf2ju3aksepmt5fzdfrvy9mi1'

from app.providers import get_data_provider, get_zerodha_provider

def test_zerodha_configuration():
    """Test Zerodha configuration and credentials"""
    print("\n" + "="*60)
    print("TEST 1: Zerodha Configuration")
    print("="*60)
    
    zerodha = get_zerodha_provider()
    
    print(f"✓ API Key Present: {bool(zerodha.api_key)}")
    print(f"✓ API Secret Present: {bool(zerodha.api_secret)}")
    print(f"✓ Kite Client Initialized: {zerodha.kite is not None}")
    print(f"⚠️  Authenticated: {zerodha.is_authenticated()}")
    
    if not zerodha.is_authenticated():
        print("\n📝 NOTE: Zerodha requires user authentication")
        print("   To authenticate:")
        print("   1. Generate login URL: zerodha.generate_login_url()")
        print("   2. User logs in and authorizes the app")
        print("   3. Exchange request token for access token")
        print("   4. Store access token for future use")
        print("\n   Without authentication, system will use Yahoo Finance fallback")
    
    return True

def test_unified_provider():
    """Test unified data provider"""
    print("\n" + "="*60)
    print("TEST 2: Unified Data Provider")
    print("="*60)
    
    provider = get_data_provider()
    
    data_source = provider.get_data_source()
    print(f"✓ Active Data Source: {data_source}")
    print(f"✓ Zerodha Available: {provider.zerodha.kite is not None}")
    print(f"✓ Zerodha Authenticated: {provider.use_zerodha}")
    
    if not provider.use_zerodha:
        print("  → Using Yahoo Finance as fallback (Zerodha not authenticated)")
    
    return True

def test_market_data():
    """Test fetching real market data"""
    print("\n" + "="*60)
    print("TEST 3: Market Data Fetching")
    print("="*60)
    
    provider = get_data_provider()
    
    try:
        # Test index quotes
        print("\n📊 Fetching Index Quotes...")
        indices = provider.get_indices_quote()
        
        for name, data in indices.items():
            price = data.get('price', 'N/A')
            change = data.get('change_percent', 'N/A')
            print(f"  {name}: ₹{price} ({change:+.2f}%)" if isinstance(price, (int, float)) else f"  {name}: {price}")
        
        print(f"\n✓ Successfully fetched {len(indices)} indices")
        return True
    except Exception as e:
        print(f"✗ Error fetching market data: {e}")
        return False

def test_quote_fetching():
    """Test fetching quotes for specific symbols"""
    print("\n" + "="*60)
    print("TEST 4: Symbol Quote Fetching")
    print("="*60)
    
    provider = get_data_provider()
    symbols = ['RELIANCE', 'TCS', 'INFY']
    
    try:
        print(f"\n📈 Fetching quotes for: {', '.join(symbols)}")
        quotes = provider.get_quote(symbols)
        
        for symbol, data in quotes.items():
            price = data.get('price', 0)
            change = data.get('change_percent', 0)
            print(f"  {symbol}: ₹{price:.2f} ({change:+.2f}%)")
        
        print(f"\n✓ Successfully fetched {len(quotes)} quotes")
        return True
    except Exception as e:
        print(f"✗ Error fetching quotes: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_market_status():
    """Test market status check"""
    print("\n" + "="*60)
    print("TEST 5: Market Status")
    print("="*60)
    
    provider = get_data_provider()
    
    try:
        status = provider.get_market_status()
        
        print(f"  Market Open: {status.get('is_open')}")
        print(f"  Weekday: {status.get('is_weekday')}")
        print(f"  Trading Hours: {status.get('is_trading_hours')}")
        print(f"  Current Time: {status.get('current_time')}")
        
        if status.get('market_open_time'):
            print(f"  Market Hours: {status['market_open_time'].strftime('%H:%M')} - {status['market_close_time'].strftime('%H:%M')}")
        
        print("\n✓ Market status retrieved")
        return True
    except Exception as e:
        print(f"✗ Error checking market status: {e}")
        return False

def run_all_tests():
    """Run all integration tests"""
    print("\n" + "="*70)
    print("  ZERODHA INTEGRATION TEST SUITE")
    print("="*70)
    
    tests = [
        ("Configuration", test_zerodha_configuration),
        ("Unified Provider", test_unified_provider),
        ("Market Data", test_market_data),
        ("Quote Fetching", test_quote_fetching),
        ("Market Status", test_market_status)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ Test '{name}' failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "="*70)
    print("  TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"  {status}: {name}")
    
    print(f"\n  Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n  🎉 ALL TESTS PASSED!")
    else:
        print(f"\n  ⚠️  {total - passed} test(s) failed")
    
    print("="*70)

if __name__ == "__main__":
    run_all_tests()
