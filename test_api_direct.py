"""Test API calls directly to debug issues"""
import asyncio
from app.services.data import provider_nse_indices, indices_summary

async def test_provider():
    print("=== Testing provider_nse_indices ===")
    try:
        result = await provider_nse_indices()
        print(f"Success: {result}")
    except Exception as e:
        print(f"Error: {e}")
    
    print("\n=== Testing indices_summary ===")
    try:
        result = await indices_summary()
        print(f"Success: {result}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_provider())
