import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.zerodha_service import zerodha_service

# Set access token
access_token = "owicslLzvKf8dCHx2gmraMNF66Ks8DVl"
zerodha_service.set_access_token(access_token)

print("\n" + "="*70)
print("ZERODHA CONNECTION TEST")
print("="*70 + "\n")

# Test 1: Profile
print("TEST 1: Profile")
print("-"*70)
try:
    profile = zerodha_service.kite.profile()
    print(f"User: {profile.get('user_name', 'N/A')}")
    print(f"Email: {profile.get('email', 'N/A')}")
    print(f"Broker: {profile.get('broker', 'N/A')}")
    print("Status: CONNECTED")
except Exception as e:
    print(f"Error: {e}")

# Test 2: Holdings
print("\n" + "="*70)
print("TEST 2: Holdings")
print("-"*70)
try:
    holdings = zerodha_service.get_holdings()
    print(f"Total Holdings: {len(holdings)}")
    
    active_holdings = [h for h in holdings if h.get('quantity', 0) > 0]
    if active_holdings:
        print(f"\nActive Holdings: {len(active_holdings)}\n")
        for h in active_holdings[:10]:
            symbol = h.get('tradingsymbol', 'N/A')
            qty = h.get('quantity', 0)
            avg_price = h.get('average_price', 0)
            ltp = h.get('last_price', 0)
            pnl = h.get('pnl', 0)
            print(f"  {symbol:<12} Qty: {qty:>6}  Avg: Rs.{avg_price:>8.2f}  LTP: Rs.{ltp:>8.2f}  P&L: Rs.{pnl:>8.2f}")
    else:
        print("No active holdings")
except Exception as e:
    print(f"Error: {e}")

# Test 3: Positions
print("\n" + "="*70)
print("TEST 3: Positions")
print("-"*70)
try:
    positions = zerodha_service.get_positions()
    net_pos = positions.get('net', [])
    active_pos = [p for p in net_pos if p.get('quantity', 0) != 0]
    
    if active_pos:
        print(f"Open Positions: {len(active_pos)}\n")
        for p in active_pos[:10]:
            symbol = p.get('tradingsymbol', 'N/A')
            qty = p.get('quantity', 0)
            pnl = p.get('pnl', 0)
            print(f"  {symbol:<12} Qty: {qty:>6}  P&L: Rs.{pnl:>8.2f}")
    else:
        print("No open positions")
except Exception as e:
    print(f"Error: {e}")

# Test 4: Quote (check permissions)
print("\n" + "="*70)
print("TEST 4: Market Quote (Permission Check)")
print("-"*70)
try:
    quote = zerodha_service.get_quote(["NSE:SBIN"])
    if quote and "NSE:SBIN" in quote:
        sbin = quote["NSE:SBIN"]
        print(f"SBIN LTP: Rs.{sbin.get('last_price', 0):.2f}")
        print("Market data: AVAILABLE")
    else:
        print("No quote data")
except Exception as e:
    print(f"Error: {e}")
    if "Insufficient permission" in str(e):
        print("\nNote: Market data requires additional permissions.")
        print("Check API settings in Zerodha developer console.")

# Save token
print("\n" + "="*70)
print("SAVING TOKEN")
print("-"*70)
token_file = Path(__file__).parent / "zerodha_access_token.txt"
with open(token_file, 'w') as f:
    f.write(access_token)
print(f"Token saved to: {token_file.name}")
print("Valid until: 6:00 AM tomorrow")

print("\n" + "="*70)
print("CONNECTION TEST COMPLETE")
print("="*70 + "\n")
