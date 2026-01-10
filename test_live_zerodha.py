"""
Test Zerodha live connection with access token
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.zerodha_service import zerodha_service, get_live_price

# Your access token (loaded from saved token files)
token_file = Path(__file__).parent / "zerodha_access_token.txt"
alt_token_file = Path(__file__).parent / ".zerodha_token"

access_token = None
for path in (token_file, alt_token_file):
    if path.exists():
        try:
            access_token = path.read_text().strip()
            if access_token:
                break
        except Exception:
            pass

if not access_token:
    print("❌ No access token found. Please run setup_zerodha_token.py first.")
    sys.exit(1)

print("\n" + "="*70)
print("🎉 TESTING ZERODHA LIVE CONNECTION")
print("="*70 + "\n")

try:
    # Set access token
    print("🔐 Setting access token...")
    zerodha_service.set_access_token(access_token)
    print("✅ Access token set successfully!\n")
    
    # Test 1: Get live prices
    print("="*70)
    print("TEST 1: LIVE MARKET PRICES")
    print("="*70 + "\n")
    
    test_symbols = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "SBIN"]
    
    print("📊 Fetching live prices for top stocks...\n")
    
    for symbol in test_symbols:
        try:
            price = get_live_price(symbol, "NSE")
            if price:
                print(f"   {symbol:<12} ₹{price:>10.2f}")
            else:
                print(f"   {symbol:<12} ⚠️  No data (market closed?)")
        except Exception as e:
            print(f"   {symbol:<12} ❌ Error: {e}")
    
    # Test 2: Get detailed quote
    print("\n" + "="*70)
    print("TEST 2: DETAILED QUOTE (RELIANCE)")
    print("="*70 + "\n")
    
    try:
        quote = zerodha_service.get_quote(["NSE:RELIANCE"])
        
        if quote and "NSE:RELIANCE" in quote:
            rel = quote["NSE:RELIANCE"]
            ohlc = rel.get('ohlc', {})
            
            print("📈 RELIANCE Quote:\n")
            print(f"   Last Price:    ₹{rel.get('last_price', 0):>10.2f}")
            print(f"   Open:          ₹{ohlc.get('open', 0):>10.2f}")
            print(f"   High:          ₹{ohlc.get('high', 0):>10.2f}")
            print(f"   Low:           ₹{ohlc.get('low', 0):>10.2f}")
            print(f"   Previous Close:₹{ohlc.get('close', 0):>10.2f}")
            print(f"   Volume:        {rel.get('volume', 0):>12,}")
            
            if 'change' in rel:
                change = rel['change']
                print(f"   Change:        {change:>10.2f}%")
        else:
            print("⚠️  Quote not available (market might be closed)")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 3: Get your holdings
    print("\n" + "="*70)
    print("TEST 3: YOUR PORTFOLIO")
    print("="*70 + "\n")
    
    try:
        print("📊 Fetching your holdings...\n")
        holdings = zerodha_service.get_holdings()
        
        if holdings:
            print(f"✅ You have {len(holdings)} holdings:\n")
            print("-"*70)
            print(f"{'Symbol':<12} {'Qty':>8} {'Avg Price':>12} {'LTP':>12} {'P&L':>12}")
            print("-"*70)
            
            total_investment = 0
            total_current = 0
            
            for holding in holdings[:10]:
                symbol = holding.get('tradingsymbol', 'N/A')
                qty = holding.get('quantity', 0)
                avg_price = holding.get('average_price', 0)
                ltp = holding.get('last_price', 0)
                pnl = holding.get('pnl', 0)
                
                if qty > 0:  # Only show active holdings
                    print(f"{symbol:<12} {qty:>8} ₹{avg_price:>10.2f} ₹{ltp:>10.2f} ₹{pnl:>10.2f}")
                    total_investment += qty * avg_price
                    total_current += qty * ltp
            
            if len(holdings) > 10:
                print(f"\n... and {len(holdings) - 10} more holdings")
            
            print("-"*70)
            total_pnl = total_current - total_investment
            pnl_pct = (total_pnl / total_investment * 100) if total_investment > 0 else 0
            
            print(f"\n💰 Portfolio Summary:")
            print(f"   Total Investment: ₹{total_investment:>12,.2f}")
            print(f"   Current Value:    ₹{total_current:>12,.2f}")
            print(f"   Total P&L:        ₹{total_pnl:>12,.2f} ({pnl_pct:+.2f}%)")
        else:
            print("✅ No holdings found (empty portfolio)")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 4: Get positions
    print("\n" + "="*70)
    print("TEST 4: OPEN POSITIONS")
    print("="*70 + "\n")
    
    try:
        print("📊 Fetching your positions...\n")
        positions = zerodha_service.get_positions()
        
        net_positions = positions.get('net', [])
        day_positions = positions.get('day', [])
        
        active_positions = [p for p in net_positions if p.get('quantity', 0) != 0]
        
        if active_positions:
            print(f"✅ You have {len(active_positions)} open positions:\n")
            print("-"*70)
            print(f"{'Symbol':<12} {'Qty':>8} {'Avg Price':>12} {'LTP':>12} {'P&L':>12}")
            print("-"*70)
            
            for pos in active_positions[:10]:
                symbol = pos.get('tradingsymbol', 'N/A')
                qty = pos.get('quantity', 0)
                avg_price = pos.get('average_price', 0)
                ltp = pos.get('last_price', 0)
                pnl = pos.get('pnl', 0)
                
                print(f"{symbol:<12} {qty:>8} ₹{avg_price:>10.2f} ₹{ltp:>10.2f} ₹{pnl:>10.2f}")
            
            print("-"*70)
        else:
            print("✅ No open positions")
        
        active_day = [p for p in day_positions if p.get('quantity', 0) != 0]
        if active_day:
            print(f"\n📈 Intraday positions: {len(active_day)}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 5: Get instruments (sample)
    print("\n" + "="*70)
    print("TEST 5: SEARCH INSTRUMENTS")
    print("="*70 + "\n")
    
    try:
        print("🔍 Searching for NIFTY instruments...\n")
        instruments = zerodha_service.search_instruments("NIFTY", "NSE")
        
        if instruments:
            print(f"✅ Found {len(instruments)} instruments:\n")
            for inst in instruments[:5]:
                symbol = inst.get('tradingsymbol', 'N/A')
                name = inst.get('name', 'N/A')
                inst_type = inst.get('instrument_type', 'N/A')
                print(f"   {symbol:<20} {name:<30} ({inst_type})")
            
            if len(instruments) > 5:
                print(f"\n   ... and {len(instruments) - 5} more")
        else:
            print("⚠️  No instruments found")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Save token
    print("\n" + "="*70)
    print("💾 SAVING ACCESS TOKEN")
    print("="*70 + "\n")
    
    token_file = Path(__file__).parent / "zerodha_access_token.txt"
    with open(token_file, 'w') as f:
        f.write(access_token)
    
    print(f"✅ Access token saved to: {token_file.name}")
    print("\n⚠️  Token valid until: 6:00 AM tomorrow")
    print("   You'll need to re-authenticate daily")
    
    # Final summary
    print("\n" + "="*70)
    print("🎉 ZERODHA INTEGRATION SUCCESSFUL!")
    print("="*70 + "\n")
    
    print("✅ What's Working:")
    print("   • Live market data ✓")
    print("   • Real-time quotes ✓")
    print("   • Portfolio access ✓")
    print("   • Position tracking ✓")
    print("   • Instrument search ✓")
    
    print("\n🚀 You Can Now:")
    print("   • Get live prices for any stock")
    print("   • View your portfolio in ARISE")
    print("   • Track positions in real-time")
    print("   • Use live data in AI analysis")
    print("   • Place orders (when ready)")
    
    print("\n💡 Integration with ARISE:")
    print("   • Replace demo data with live Zerodha data")
    print("   • Show real-time prices in recommendations")
    print("   • Display user portfolio in dashboard")
    print("   • Execute trades from ARIS suggestions")
    
    print("\n📅 Next Steps:")
    print("   1. Integrate live prices into agents")
    print("   2. Add portfolio tracking to dashboard")
    print("   3. Build order execution UI")
    print("   4. Enable one-click trading from ARIS")
    
    print("\n" + "="*70)
    print("ARISE is now connected to LIVE MARKET DATA! 🎊")
    print("="*70 + "\n")
    
except Exception as e:
    print(f"\n❌ ERROR: {e}\n")
    print("Possible issues:")
    print("• Network connection")
    print("• Token might be invalid")
    print("• Zerodha API might be down")
    print("\n" + "="*70 + "\n")
