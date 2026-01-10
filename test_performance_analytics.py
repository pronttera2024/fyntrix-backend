"""
Test script to verify performance analytics logging and scores
"""
import asyncio
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.performance_analytics import PerformanceAnalytics

async def test():
    """Test performance analytics"""
    print("="*60)
    print("Testing Performance Analytics with Logging")
    print("="*60)
    
    analytics = PerformanceAnalytics()
    result = await analytics.get_winning_strategies(lookback_days=7, universe='nifty50')
    
    print("\n" + "="*60)
    print("API Response Summary:")
    print("="*60)
    print(f"Total picks: {len(result.get('recommendations', []))}")
    
    # Check scores
    picks_with_scores = 0
    picks_without_scores = []
    
    for rec in result.get('recommendations', []):
        symbol = rec.get('symbol')
        scores = rec.get('scores', {})
        
        if scores:
            picks_with_scores += 1
        else:
            picks_without_scores.append(symbol)
    
    print(f"Picks with scores: {picks_with_scores}")
    print(f"Picks without scores: {len(picks_without_scores)}")
    
    if picks_without_scores:
        print(f"Symbols missing scores: {picks_without_scores}")
    
    # Show example
    if result.get('recommendations'):
        first = result['recommendations'][0]
        print(f"\nExample: {first['symbol']}")
        print(f"  Has scores: {bool(first.get('scores'))}")
        if first.get('scores'):
            print(f"  Score keys: {list(first['scores'].keys())}")

if __name__ == "__main__":
    asyncio.run(test())
