"""
Quick Zerodha Authentication - Paste token and GO!
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.zerodha_service import zerodha_service, get_live_price

print("\n" + "="*70)
print("⚡ QUICK ZERODHA AUTHENTICATION")
print("="*70 + "\n")

# Generate login URL
login_url = zerodha_service.get_login_url()

print("STEP 1: Login to Zerodha")
print("-"*70)
print("\n🔗 Copy this URL and paste in browser:\n")
print(login_url)
print("\n")

print("STEP 2: Get Request Token")
print("-"*70)
print("\n1. Login with your Zerodha credentials")
print("2. Click 'Authorize'")
print("3. You'll see a 404 page - THAT'S OK!")
print("4. Look at the URL in browser address bar")
print("5. Copy ONLY the token part (between request_token= and &status)")
print("\nExample URL:")
print("https://arise-trading.vercel.app/auth/callback?request_token=ABC123XYZ&status=success")
print("                                                              ^^^^^^^^^ ")
print("                                                         Copy this part!\n")

print("="*70)
print("STEP 3: Paste Token Below")
print("="*70)

# Get token from user
request_token = input("\n📋 Paste your request_token here: ").strip()

if not request_token:
    print("\n❌ No token provided. Exiting.")
    sys.exit(1)

print(f"\n🔐 Using token: {request_token[:20]}...")

try:
    print("\n⏳ Generating session...")
    session_data = zerodha_service.generate_session(request_token)
    
    print("\n" + "="*70)
    print("✅ AUTHENTICATION SUCCESSFUL!")
    print("="*70)
    print(f"\nUser: {session_data.get('user_name', 'N/A')}")
    print(f"Email: {session_data.get('email', 'N/A')}")
    print(f"Access Token: {session_data['access_token'][:30]}...")
    
    # Save token
    token_file = Path(__file__).parent / "zerodha_access_token.txt"
    with open(token_file, 'w') as f:
        f.write(session_data['access_token'])
    print(f"\n💾 Token saved to: {token_file.name}")
    
    # Test live price
    print("\n" + "="*70)
    print("📊 TESTING LIVE DATA")
    print("="*70)
    
    try:
        print("\n⏳ Fetching RELIANCE price...")
        price = get_live_price("RELIANCE", "NSE")
        if price:
            print(f"✅ RELIANCE: ₹{price}")
        else:
            print("⚠️  Market might be closed")
    except Exception as e:
        print(f"⚠️  {e}")
    
    print("\n" + "="*70)
    print("🎉 YOU'RE CONNECTED TO ZERODHA!")
    print("="*70)
    print("\nYou can now use live market data in ARISE!\n")
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    print("\nToken might be expired. They only last ~5 minutes!")
    print("Please run this script again and paste the token IMMEDIATELY after getting it.\n")
    sys.exit(1)
