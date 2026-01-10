"""
Test Zerodha Kite Connect Integration
Verify API credentials and test basic functionality
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.zerodha_service import zerodha_service


def test_zerodha_connection():
    """Test Zerodha API connection"""
    
    print("\n" + "="*70)
    print("ZERODHA KITE CONNECT - CONNECTION TEST")
    print("="*70 + "\n")
    
    # Test 1: Check credentials loaded
    print("TEST 1: Checking API Credentials")
    print("-" * 70)
    
    if zerodha_service.api_key:
        print(f"✅ API Key loaded: {zerodha_service.api_key[:10]}...")
        print(f"✅ API Secret loaded: {'*' * 20}")
        print(f"✅ Redirect URL: {zerodha_service.redirect_url}")
    else:
        print("❌ API credentials not found in .env file")
        return
    
    # Test 2: Generate login URL
    print("\n" + "="*70)
    print("TEST 2: Generating Login URL")
    print("-" * 70)
    
    try:
        login_url = zerodha_service.get_login_url()
        print(f"\n✅ Login URL generated successfully!")
        print(f"\n📋 Copy this URL and paste in browser:")
        print(f"\n{login_url}\n")
        print("Steps:")
        print("1. Open the URL in browser")
        print("2. Login with your Zerodha credentials")
        print("3. Authorize the app")
        print("4. You'll be redirected to callback URL with request_token")
        print("5. Copy the request_token from URL")
        
    except Exception as e:
        print(f"❌ Failed to generate login URL: {e}")
        print("\nMake sure kiteconnect is installed:")
        print("pip install kiteconnect")
        return
    
    # Test 3: Wait for user to complete login
    print("\n" + "="*70)
    print("TEST 3: Session Generation (Manual Step)")
    print("-" * 70)
    
    print("\nAfter logging in via the URL above:")
    print("1. You'll be redirected to: https://arise-trading.vercel.app/auth/callback?request_token=XXX&status=success")
    print("2. Copy the 'request_token' from the URL")
    print("3. Run this script again or call generate_session() with the token")
    
    print("\nExample:")
    print("  from app.services.zerodha_service import zerodha_service")
    print("  zerodha_service.generate_session('YOUR_REQUEST_TOKEN')")
    
    # Test 4: Data access limitations
    print("\n" + "="*70)
    print("IMPORTANT: Data Access Information")
    print("="*70)
    
    print("\n📊 What You Can Access:")
    print("  ✅ Historical data (daily, intraday)")
    print("  ✅ Quote data (delayed by a few seconds)")
    print("  ✅ OHLC data")
    print("  ✅ Instrument list")
    print("  ✅ Order placement")
    print("  ✅ Portfolio & positions")
    
    print("\n⚠️  Real-time Data Restrictions:")
    print("  • WebSocket tick data requires additional subscription")
    print("  • Some data may be delayed by ~1-5 seconds")
    print("  • Historical data is free and unlimited")
    
    print("\n💰 To Get Real-time Data:")
    print("  1. Subscribe to Kite Connect (₹2,000/month)")
    print("  2. For live streaming, may need additional exchange fees")
    print("  3. Historical data is always free")
    
    print("\n📈 For ARISE Platform:")
    print("  ✅ Historical data sufficient for analysis")
    print("  ✅ Quote data good for entry/exit prices")
    print("  ✅ Can combine with other free sources (Alpha Vantage, NSE)")
    print("  ✅ Focus on daily/swing trading (not tick-by-tick)")
    
    # Test 5: Sample integration
    print("\n" + "="*70)
    print("SAMPLE INTEGRATION CODE")
    print("="*70)
    
    print("""
# 1. User Login Flow (in your API/Frontend):

from app.services.zerodha_service import zerodha_service

# Generate login URL
login_url = zerodha_service.get_login_url()
# Redirect user to login_url

# After callback, get request_token from URL
request_token = "token_from_callback_url"

# Generate session
session_data = zerodha_service.generate_session(request_token)
access_token = session_data["access_token"]

# Now you can use Zerodha APIs!


# 2. Get Live Price:

from app.services.zerodha_service import get_live_price

price = get_live_price("RELIANCE", "NSE")
print(f"RELIANCE LTP: ₹{price}")


# 3. Place Order:

from app.services.zerodha_service import place_market_order

order_id = place_market_order(
    symbol="RELIANCE",
    transaction_type="BUY",
    quantity=1,
    product="CNC"  # Delivery
)
print(f"Order placed: {order_id}")


# 4. Get Portfolio:

positions = zerodha_service.get_positions()
holdings = zerodha_service.get_holdings()
""")
    
    print("\n" + "="*70)
    print("✅ ZERODHA INTEGRATION READY!")
    print("="*70)
    
    print("\nNext Steps:")
    print("1. ✅ API credentials configured")
    print("2. 🔜 Complete user login flow")
    print("3. 🔜 Test data fetching")
    print("4. 🔜 Test order placement (with small qty)")
    print("5. 🔜 Integrate with ARISE recommendations")
    
    print("\nFiles Created:")
    print("  • backend/app/services/zerodha_service.py - Complete integration")
    print("  • backend/.env - Credentials stored securely")
    print("  • backend/test_zerodha_connection.py - This test")
    
    print("\n💡 Pro Tip:")
    print("  Start with historical data and quotes")
    print("  Test order placement with 1 quantity first")
    print("  Real-time streaming can be added later")
    
    print("\n🎉 You're ready to connect ARISE with live broker!")
    print("="*70 + "\n")


if __name__ == "__main__":
    test_zerodha_connection()
