"""
Quick test for OpenAI insights generation
"""

import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import the function
from app.services.intelligent_insights import generate_stock_insights

async def test_insights():
    print("Testing OpenAI Insights Generation...")
    print(f"API Key present: {bool(os.getenv('OPENAI_API_KEY'))}")
    print(f"API Key (first 20 chars): {os.getenv('OPENAI_API_KEY', '')[:20]}...")
    
    # Test data
    scores = {
        "technical": 75,
        "sentiment": 72,
        "options": 70,
        "pattern": 68,
        "global": 65
    }
    
    try:
        insights = await generate_stock_insights(
            symbol="RELIANCE",
            scores=scores,
            blend_score=68.4,
            recommendation="Buy"
        )
        
        print("\n✓ Success!")
        print(f"\nKey Findings:\n{insights['key_findings']}")
        print(f"\nStrategy Rationale:\n{insights['strategy_rationale']}")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_insights())
