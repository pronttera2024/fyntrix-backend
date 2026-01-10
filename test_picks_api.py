"""
Test picks API with AI insights
"""

import asyncio
import os
from dotenv import load_dotenv

# API key loaded from environment or .env file

# Load dotenv after setting env
load_dotenv(override=True)

from app.services.intelligent_insights import generate_batch_insights

async def test():
    print("Testing batch insights generation...")
    print(f"API Key: {os.getenv('OPENAI_API_KEY')[:20]}...")
    
    picks = [
        {
            "symbol": "RELIANCE",
            "score_blend": 68.4,
            "recommendation": "Buy",
            "scores": {
                "technical": 75,
                "sentiment": 72,
                "options": 70
            }
        }
    ]
    
    try:
        result = await generate_batch_insights(picks)
        print("\n✓ Success!")
        print(f"\nSymbol: {result[0]['symbol']}")
        print(f"\nKey Findings:\n{result[0].get('key_findings', 'N/A')}")
        print(f"\nStrategy Rationale:\n{result[0].get('strategy_rationale', 'N/A')}")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
