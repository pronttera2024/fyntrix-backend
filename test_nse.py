import httpx
import asyncio
import json

async def test_nse_indices():
    """Test NSE indices API"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://www.nseindia.com/",
        "Accept": "application/json"
    }
    
    async with httpx.AsyncClient(timeout=15, headers=headers) as cx:
        # Warm up
        await cx.get("https://www.nseindia.com/")
        
        # Get indices
        r = await cx.get("https://www.nseindia.com/api/allIndices")
        data = r.json()
        
        print("=== NSE INDICES ===")
        for item in data.get("data", [])[:5]:
            print(f"{item.get('index')}: {item.get('last')} ({item.get('percentChange')}%)")
        print()

async def test_nse_news():
    """Test NSE corporate announcements API"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://www.nseindia.com/",
        "Accept": "application/json"
    }
    
    async with httpx.AsyncClient(timeout=15, headers=headers) as cx:
        # Warm up
        await cx.get("https://www.nseindia.com/")
        
        # Get announcements
        r = await cx.get("https://www.nseindia.com/api/corporate-announcements?index=equities")
        data = r.json()
        
        print("=== NSE ANNOUNCEMENTS ===")
        print(f"Total items: {len(data)}")
        for item in data[:5]:
            print(f"- {item.get('subject', 'NO SUBJECT')} ({item.get('symbol', 'N/A')})")
            print(f"  Date: {item.get('an_dt', 'N/A')}")
        print()

async def test_fmp_news():
    """Test FMP news API"""
    api_key = "1oFKhKppawnk4ndt7wvCqNGXKNPllw1n"
    url = f"https://financialmodelingprep.com/api/v3/fmp/articles?page=0&size=5&apikey={api_key}"
    
    async with httpx.AsyncClient(timeout=10) as cx:
        r = await cx.get(url)
        print("=== FMP NEWS ===")
        print(f"Status: {r.status_code}")
        data = r.json()
        if isinstance(data, dict):
            content = data.get("content", [])
            print(f"Items: {len(content)}")
            for item in content[:3]:
                print(f"- {item.get('title', 'NO TITLE')}")
        else:
            print(f"Items: {len(data)}")
            for item in data[:3]:
                print(f"- {item.get('title', 'NO TITLE')}")
        print()

if __name__ == "__main__":
    asyncio.run(test_nse_indices())
    asyncio.run(test_nse_news())
    asyncio.run(test_fmp_news())
