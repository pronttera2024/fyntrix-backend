"""
Test if Zerodha is actually authenticated and can fetch data
"""
import asyncio
from datetime import datetime, timedelta

async def main():
    print("\n" + "="*60)
    print("ZERODHA AUTHENTICATION TEST")
    print("="*60)
    
    # Import after setting up path
    from app.services.zerodha_service import zerodha_service
    
    print(f"\n1. Service initialized: {zerodha_service is not None}")
    print(f"2. Has kite: {zerodha_service.kite is not None}")
    print(f"3. Has access_token: {zerodha_service.access_token is not None}")
    
    if zerodha_service.access_token:
        print(f"4. Token (first 30 chars): {zerodha_service.access_token[:30]}...")
    
    # Try to fetch data
    print("\n" + "="*60)
    print("TESTING DATA FETCH")
    print("="*60)
    
    from_date = datetime.now() - timedelta(days=1)
    to_date = datetime.now()
    
    print(f"\nFetching TCS data...")
    print(f"  From: {from_date}")
    print(f"  To: {to_date}")
    print(f"  Interval: 15minute")
    
    try:
        df = await zerodha_service.get_historical_data(
            symbol='TCS',
            from_date=from_date,
            to_date=to_date,
            interval='15minute'
        )
        
        if df is not None and len(df) > 0:
            print(f"\n✅ SUCCESS!")
            print(f"   Got {len(df)} candles")
            print(f"\n   First candle:")
            print(df.iloc[0])
            print(f"\n   Columns: {list(df.columns)}")
        else:
            print(f"\n❌ FAILED - returned None or empty")
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*60)

if __name__ == "__main__":
    asyncio.run(main())
