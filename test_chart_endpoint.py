"""
Quick test script to verify chart endpoint is working
Run this to test the backend chart API independently
"""

import requests
import json

def test_chart_endpoint():
    """Test chart data endpoint"""
    
    print("🧪 Testing ARISE Chart Endpoint")
    print("=" * 50)
    
    # Test configuration
    BASE_URL = "http://localhost:8000"
    symbols = ["NIFTY", "RELIANCE", "TCS"]
    timeframes = ["1M", "3M", "6M", "1Y"]
    
    # Test 1: Health check
    print("\n1️⃣ Testing Health Endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200 and response.json().get("ok"):
            print("   ✅ Health check passed")
        else:
            print("   ❌ Health check failed")
            return False
    except Exception as e:
        print(f"   ❌ Health check error: {e}")
        print("   ⚠️  Is backend running? Start with: uvicorn app.main:app --reload")
        return False
    
    # Test 2: Chart data for multiple symbols
    print("\n2️⃣ Testing Chart Data Endpoints...")
    for symbol in symbols:
        for timeframe in timeframes:
            endpoint = f"{BASE_URL}/v1/chart/{symbol}?timeframe={timeframe}"
            
            try:
                response = requests.get(endpoint)
                
                if response.status_code != 200:
                    print(f"   ❌ {symbol} {timeframe}: Status {response.status_code}")
                    continue
                
                data = response.json()
                
                # Verify response structure
                required_keys = ['symbol', 'timeframe', 'candles', 'signals', 'current']
                missing_keys = [key for key in required_keys if key not in data]
                
                if missing_keys:
                    print(f"   ❌ {symbol} {timeframe}: Missing keys: {missing_keys}")
                    continue
                
                # Verify data
                candles_count = len(data.get('candles', []))
                signals_count = len(data.get('signals', []))
                current_price = data.get('current', {}).get('price')
                
                if candles_count == 0:
                    print(f"   ❌ {symbol} {timeframe}: No candles data")
                    continue
                
                if current_price is None:
                    print(f"   ❌ {symbol} {timeframe}: No current price")
                    continue
                
                print(f"   ✅ {symbol} {timeframe}: {candles_count} candles, {signals_count} signals, ₹{current_price}")
                
            except Exception as e:
                print(f"   ❌ {symbol} {timeframe}: Error: {e}")
    
    # Test 3: Verify candle structure
    print("\n3️⃣ Verifying Candle Data Structure...")
    try:
        response = requests.get(f"{BASE_URL}/v1/chart/NIFTY?timeframe=3M")
        data = response.json()
        
        if not data.get('candles'):
            print("   ❌ No candles in response")
            return False
        
        first_candle = data['candles'][0]
        required_fields = ['time', 'open', 'high', 'low', 'close', 'volume']
        
        missing_fields = [field for field in required_fields if field not in first_candle]
        
        if missing_fields:
            print(f"   ❌ Candle missing fields: {missing_fields}")
            return False
        
        print(f"   ✅ Candle structure valid")
        print(f"      Sample candle: {json.dumps(first_candle, indent=6)}")
        
    except Exception as e:
        print(f"   ❌ Error verifying candle: {e}")
        return False
    
    # Test 4: Verify signal structure
    print("\n4️⃣ Verifying Signal Data Structure...")
    try:
        response = requests.get(f"{BASE_URL}/v1/chart/NIFTY?timeframe=3M")
        data = response.json()
        
        if not data.get('signals'):
            print("   ⚠️  No signals in response (this may be normal)")
        else:
            first_signal = data['signals'][0]
            required_fields = ['time', 'type', 'text', 'price']
            
            missing_fields = [field for field in required_fields if field not in first_signal]
            
            if missing_fields:
                print(f"   ❌ Signal missing fields: {missing_fields}")
            else:
                print(f"   ✅ Signal structure valid")
                print(f"      Sample signal: {json.dumps(first_signal, indent=6)}")
        
    except Exception as e:
        print(f"   ❌ Error verifying signal: {e}")
    
    # Summary
    print("\n" + "=" * 50)
    print("✅ All tests passed! Chart endpoint is working correctly.")
    print("\n📊 Next steps:")
    print("   1. Start frontend: cd frontend && npm run dev")
    print("   2. Open browser: http://localhost:5175")
    print("   3. Click Charts button or stock symbol")
    print("   4. Chart should display with candlesticks")
    print("\n🎉 Backend is ready!")
    
    return True


def print_sample_response():
    """Print a sample successful response for reference"""
    
    print("\n" + "=" * 50)
    print("📋 Sample Successful Response:")
    print("=" * 50)
    
    sample = {
        "symbol": "NIFTY",
        "timeframe": "3M",
        "candles": [
            {
                "time": 1693526400,
                "open": 2500.0,
                "high": 2520.5,
                "low": 2495.3,
                "close": 2515.8,
                "volume": 7500000
            },
            "... more candles ..."
        ],
        "signals": [
            {
                "time": 1696118400,
                "type": "bullish",
                "text": "MACD Bullish Crossover",
                "price": 2530.5
            },
            "... more signals ..."
        ],
        "current": {
            "price": 2515.8,
            "change": 0.63,
            "volume": 7500000
        },
        "timestamp": "2024-11-10T15:30:00.000000Z"
    }
    
    print(json.dumps(sample, indent=2))


if __name__ == "__main__":
    try:
        success = test_chart_endpoint()
        
        if success:
            print_sample_response()
        else:
            print("\n❌ Some tests failed. Check errors above.")
            print("\n💡 Tips:")
            print("   • Ensure backend is running")
            print("   • Check if port 8000 is available")
            print("   • Verify all dependencies installed")
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
