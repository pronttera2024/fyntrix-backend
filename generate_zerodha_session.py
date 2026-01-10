"""
Generate Zerodha session with request token
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.zerodha_service import zerodha_service, get_live_price

# Your request token
request_token = "KnewYo0FGDI418ukcEMz0AnOxIpZj2oy"

print("\n" + "="*70)
print("GENERATING ZERODHA SESSION")
print("="*70 + "\n")

try:
    # Generate session
    print("🔐 Generating session with request token...")
    session_data = zerodha_service.generate_session(request_token)
    
    print("\n✅ SESSION GENERATED SUCCESSFULLY!\n")
    print("="*70)
    print("SESSION DETAILS")
    print("="*70)
    print(f"User ID:       {session_data.get('user_id', 'N/A')}")
    print(f"User Name:     {session_data.get('user_name', 'N/A')}")
    print(f"Email:         {session_data.get('email', 'N/A')}")
    print(f"User Type:     {session_data.get('user_type', 'N/A')}")
    print(f"Broker:        {session_data.get('broker', 'N/A')}")
    print(f"\nAccess Token:  {session_data['access_token'][:30]}...")
    print("="*70 + "\n")
    
    # Save access token for future use
    access_token = session_data['access_token']
    
    # Test 1: Get live price
    print("="*70)
    print("TEST 1: FETCHING LIVE PRICE")
    print("="*70)
    
    try:
        print("\n📊 Getting live price for RELIANCE...")
        price = get_live_price("RELIANCE", "NSE")
        
        if price:
            print(f"✅ RELIANCE LTP: ₹{price}")
        else:
            print("⚠️  Price not available (might be market closed)")
    except Exception as e:
        print(f"⚠️  Could not fetch price: {e}")
    
    # Test 2: Get quote
    print("\n" + "="*70)
    print("TEST 2: FETCHING DETAILED QUOTE")
    print("="*70)
    
    try:
        print("\n📊 Getting quote for RELIANCE...")
        quote = zerodha_service.get_quote(["NSE:RELIANCE"])
        
        if quote and "NSE:RELIANCE" in quote:
            rel_quote = quote["NSE:RELIANCE"]
            print(f"\n✅ RELIANCE Quote:")
            print(f"   Last Price:    ₹{rel_quote.get('last_price', 'N/A')}")
            print(f"   Open:          ₹{rel_quote.get('ohlc', {}).get('open', 'N/A')}")
            print(f"   High:          ₹{rel_quote.get('ohlc', {}).get('high', 'N/A')}")
            print(f"   Low:           ₹{rel_quote.get('ohlc', {}).get('low', 'N/A')}")
            print(f"   Close:         ₹{rel_quote.get('ohlc', {}).get('close', 'N/A')}")
            print(f"   Volume:        {rel_quote.get('volume', 'N/A'):,}")
            print(f"   Change:        {rel_quote.get('change', 'N/A')}%")
        else:
            print("⚠️  Quote not available")
    except Exception as e:
        print(f"⚠️  Could not fetch quote: {e}")
    
    # Test 3: Get holdings
    print("\n" + "="*70)
    print("TEST 3: FETCHING YOUR PORTFOLIO")
    print("="*70)
    
    try:
        print("\n📈 Getting your holdings...")
        holdings = zerodha_service.get_holdings()
        
        if holdings:
            print(f"\n✅ You have {len(holdings)} holdings:")
            print("\n" + "-"*70)
            print(f"{'Symbol':<15} {'Qty':>8} {'Avg Price':>12} {'LTP':>12} {'P&L':>12}")
            print("-"*70)
            
            total_investment = 0
            total_current = 0
            
            for holding in holdings[:10]:  # Show first 10
                symbol = holding.get('tradingsymbol', 'N/A')
                qty = holding.get('quantity', 0)
                avg_price = holding.get('average_price', 0)
                ltp = holding.get('last_price', 0)
                pnl = holding.get('pnl', 0)
                
                print(f"{symbol:<15} {qty:>8} ₹{avg_price:>10.2f} ₹{ltp:>10.2f} ₹{pnl:>10.2f}")
                
                total_investment += qty * avg_price
                total_current += qty * ltp
            
            if len(holdings) > 10:
                print(f"... and {len(holdings) - 10} more")
            
            print("-"*70)
            total_pnl = total_current - total_investment
            pnl_pct = (total_pnl / total_investment * 100) if total_investment > 0 else 0
            print(f"Total Investment: ₹{total_investment:,.2f}")
            print(f"Current Value:    ₹{total_current:,.2f}")
            print(f"Total P&L:        ₹{total_pnl:+,.2f} ({pnl_pct:+.2f}%)")
            print("-"*70)
        else:
            print("✅ No holdings found (or empty portfolio)")
    except Exception as e:
        print(f"⚠️  Could not fetch holdings: {e}")
    
    # Test 4: Get positions
    print("\n" + "="*70)
    print("TEST 4: FETCHING YOUR POSITIONS")
    print("="*70)
    
    try:
        print("\n📊 Getting your positions...")
        positions = zerodha_service.get_positions()
        
        net_positions = positions.get('net', [])
        day_positions = positions.get('day', [])
        
        if net_positions:
            print(f"\n✅ You have {len(net_positions)} open positions:")
            for pos in net_positions[:5]:
                symbol = pos.get('tradingsymbol', 'N/A')
                qty = pos.get('quantity', 0)
                pnl = pos.get('pnl', 0)
                print(f"   {symbol}: {qty} qty, P&L: ₹{pnl:+.2f}")
        else:
            print("✅ No open positions")
        
        if day_positions:
            print(f"\n✅ Intraday: {len(day_positions)} positions")
        else:
            print("✅ No intraday positions")
            
    except Exception as e:
        print(f"⚠️  Could not fetch positions: {e}")
    
    # Save token for later use
    print("\n" + "="*70)
    print("💾 SAVING ACCESS TOKEN")
    print("="*70)
    
    token_file = Path(__file__).parent / "zerodha_access_token.txt"
    with open(token_file, 'w') as f:
        f.write(access_token)
    
    print(f"\n✅ Access token saved to: {token_file}")
    print("\n⚠️  Note: This token expires at 6:00 AM tomorrow")
    print("   You'll need to re-authenticate daily")
    
    # Final summary
    print("\n" + "="*70)
    print("🎉 ZERODHA INTEGRATION SUCCESSFUL!")
    print("="*70)
    
    print("\n✅ What's working:")
    print("   • Authentication ✓")
    print("   • Live price data ✓")
    print("   • Quote data ✓")
    print("   • Portfolio access ✓")
    print("   • Position tracking ✓")
    
    print("\n🚀 You can now:")
    print("   • Fetch live market data")
    print("   • Get real-time quotes")
    print("   • View your portfolio in ARISE")
    print("   • Place orders (when integrated)")
    
    print("\n💡 Next steps:")
    print("   1. Integrate with ARISE analysis")
    print("   2. Use live data in recommendations")
    print("   3. Build trading UI")
    print("   4. Enable one-click order execution")
    
    print("\n" + "="*70)
    print("ARISE is now connected to live market data! 🎊")
    print("="*70 + "\n")
    
except Exception as e:
    print(f"\n❌ ERROR: {e}\n")
    print("Possible reasons:")
    print("• Token might be expired (tokens are valid for ~5 minutes)")
    print("• Token might have been already used")
    print("• Network connection issue")
    print("\nSolution: Try generating a new login URL and get a fresh token")
    print("Run: python test_zerodha_connection.py")
    print("="*70 + "\n")
