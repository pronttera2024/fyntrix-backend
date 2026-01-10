"""
Test Zerodha service directly
"""
import asyncio
from datetime import datetime, timedelta
from app.services.zerodha_service import zerodha_service

async def test_zerodha():
    print("\n" + "="*60)
    print("Testing Zerodha Service Directly")
    print("="*60)
    
    # Check authentication
    print(f"\nAuthenticated: {zerodha_service.access_token is not None}")
    if zerodha_service.access_token:
        print(f"Token: {zerodha_service.access_token[:30]}...")
    
    # Try to fetch data
    print("\nFetching TCS historical data (15-minute interval)...")
    
    from_date = datetime.now() - timedelta(days=1)
    to_date = datetime.now()
    
    try:
        df = await zerodha_service.get_historical_data(
            symbol='TCS',
            from_date=from_date,
            to_date=to_date,
            interval='15minute'
        )
        
        if df is not None:
            print(f"\n✅ SUCCESS! Got {len(df)} candles")
            print(f"\nFirst 5 candles:")
            print(df.head())
            print(f"\nColumns: {list(df.columns)}")
        else:
            print("\n❌ Got None from Zerodha")
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_zerodha())
