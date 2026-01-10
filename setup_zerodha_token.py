"""
Quick script to generate and save Zerodha access token
"""

import os
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv
load_dotenv()

try:
    from kiteconnect import KiteConnect
except ImportError:
    print("ERROR: kiteconnect not installed")
    print("Run: pip install kiteconnect")
    sys.exit(1)

# Your request token (updated for current session)
REQUEST_TOKEN = "m0PZXPzihW76BlTFuDRF1VMLq6T5uwuk"

# API credentials from .env
API_KEY = os.getenv('ZERODHA_API_KEY')
API_SECRET = os.getenv('ZERODHA_API_SECRET')

print("\n" + "="*70)
print("ZERODHA ACCESS TOKEN GENERATION")
print("="*70)

if not API_KEY or not API_SECRET:
    print("\n❌ ERROR: API credentials not found in .env")
    print("Please check ZERODHA_API_KEY and ZERODHA_API_SECRET")
    sys.exit(1)

print(f"\n✓ API Key: {API_KEY}")
print(f"✓ Request Token: {REQUEST_TOKEN}")

try:
    # Initialize KiteConnect
    kite = KiteConnect(api_key=API_KEY)
    
    print("\n⏳ Generating session...")
    
    # Generate session
    data = kite.generate_session(
        request_token=REQUEST_TOKEN,
        api_secret=API_SECRET
    )
    
    access_token = data["access_token"]
    user_id = data.get("user_id", "Unknown")
    user_name = data.get("user_name", "Unknown")
    email = data.get("email", "Unknown")
    
    print("\n" + "="*70)
    print("✅ SUCCESS! Zerodha Authentication Complete")
    print("="*70)
    print(f"\n👤 User ID: {user_id}")
    print(f"📧 Email: {email}")
    print(f"🏷️  Name: {user_name}")
    print(f"\n🔑 Access Token: {access_token}")
    
    # Save to file (main location)
    token_file = backend_dir / "zerodha_access_token.txt"
    with open(token_file, 'w') as f:
        f.write(access_token)
    print(f"\n✓ Token saved to: {token_file}")
    
    # Also save to .zerodha_token (used by service)
    alt_token_file = backend_dir / ".zerodha_token"
    with open(alt_token_file, 'w') as f:
        f.write(access_token)
    print(f"✓ Token saved to: {alt_token_file}")
    
    # Test the token
    print("\n⏳ Testing token...")
    kite.set_access_token(access_token)
    
    # Try to get profile
    profile = kite.profile()
    print(f"✅ Token validated! Connected as: {profile.get('user_name', 'Unknown')}")
    
    # Try to get a quote
    print("\n⏳ Testing market data access...")
    quote = kite.quote(["NSE:RELIANCE"])
    if quote:
        reliance = quote.get("NSE:RELIANCE", {})
        last_price = reliance.get("last_price", 0)
        print(f"✅ Market data working! RELIANCE: ₹{last_price}")
    
    print("\n" + "="*70)
    print("🎉 ZERODHA INTEGRATION COMPLETE!")
    print("="*70)
    print("\n✅ Access token generated and saved")
    print("✅ Token validated successfully")
    print("✅ Market data access confirmed")
    print("\n📋 Next: Restart backend server to load new token")
    print("   Command: python -m app.main")
    print("\n⏰ Note: Token expires at 6:00 AM tomorrow")
    print("="*70 + "\n")
    
except Exception as e:
    print("\n" + "="*70)
    print("❌ ERROR: Failed to generate session")
    print("="*70)
    print(f"\nError: {str(e)}")
    print("\nPossible reasons:")
    print("1. Request token expired (valid for 5 minutes)")
    print("2. Request token already used")
    print("3. Invalid API credentials")
    print("\nSolution: Generate new request token from:")
    print("https://kite.zerodha.com/connect/login?v=3&api_key=" + API_KEY)
    print("="*70 + "\n")
    sys.exit(1)
