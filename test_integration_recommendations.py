"""
Integration Test: Recommendation System with Simulated Agent Data
==================================================================

Tests the complete flow with simulated agent analysis results
to verify that recommendations are properly applied and Neutral
picks are filtered from Top Picks.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.utils.recommendation_system import get_recommendation, filter_actionable_picks


def test_integration_flow():
    """Test complete flow from agent results to filtered picks"""
    
    print("\n" + "=" * 80)
    print("INTEGRATION TEST: Simulated Agent Analysis → Filtered Top Picks")
    print("=" * 80)
    
    # Simulate 10 stocks with varying scores
    simulated_results = [
        {"symbol": "RELIANCE", "score": 78, "risk_score": 75},  # Strong Buy
        {"symbol": "TCS", "score": 68, "risk_score": 65},       # Buy
        {"symbol": "HDFC", "score": 52, "risk_score": 50},      # Neutral
        {"symbol": "INFY", "score": 62, "risk_score": 60},      # Buy
        {"symbol": "ICICI", "score": 48, "risk_score": 45},     # Neutral
        {"symbol": "SBIN", "score": 72, "risk_score": 70},      # Strong Buy
        {"symbol": "AXIS", "score": 44, "risk_score": 40},      # Neutral
        {"symbol": "KOTAK", "score": 58, "risk_score": 55},     # Buy
        {"symbol": "WIPRO", "score": 35, "risk_score": 30},     # Sell
        {"symbol": "LT", "score": 75, "risk_score": 72},        # Strong Buy
    ]
    
    # Apply recommendations
    print("\n" + "-" * 80)
    print("STEP 1: Apply Recommendations")
    print("-" * 80)
    
    results_with_recs = []
    for result in simulated_results:
        rec = get_recommendation(
            score=result["score"],
            confidence="Medium",
            risk_agent_score=result["risk_score"]
        )
        
        result_with_rec = {
            **result,
            "recommendation": rec.recommendation.value,
            "is_actionable": rec.is_actionable,
            "risk_reward_ratio": rec.risk_reward_ratio,
            "note": rec.note
        }
        results_with_recs.append(result_with_rec)
        
        print(f"{result['symbol']:12} Score: {result['score']:3} → {rec.recommendation.value:12} (Actionable: {rec.is_actionable})")
    
    # Sort by score
    results_with_recs.sort(key=lambda x: x["score"], reverse=True)
    
    # Filter to actionable only
    print("\n" + "-" * 80)
    print("STEP 2: Filter to Actionable Picks Only")
    print("-" * 80)
    
    actionable_picks, actionable_count, total_count = filter_actionable_picks(results_with_recs)
    
    print(f"\nTotal analyzed: {total_count} stocks")
    print(f"Actionable: {actionable_count} stocks")
    print(f"Neutral (filtered out): {total_count - actionable_count} stocks")
    
    # Show top 5 actionable
    print("\n" + "-" * 80)
    print("STEP 3: Top 5 Actionable Picks")
    print("-" * 80)
    
    top_5 = actionable_picks[:5]
    
    if len(top_5) < 5:
        print(f"\n⚠️  Only {len(top_5)} actionable opportunities today (requested 5)")
    else:
        print(f"\n✅ Top 5 Trading Opportunities:")
    
    print()
    for rank, pick in enumerate(top_5, 1):
        r_r = f"{pick['risk_reward_ratio']:.2f}" if pick['risk_reward_ratio'] else "N/A"
        print(f"  {rank}. {pick['symbol']:12} Score: {pick['score']:3} → {pick['recommendation']:12} (R/R: {r_r})")
        if pick['note']:
            print(f"     Note: {pick['note']}")
    
    # Show what was filtered out
    print("\n" + "-" * 80)
    print("STEP 4: Neutral Picks (NOT Shown in Top Picks)")
    print("-" * 80)
    
    neutral_picks = [p for p in results_with_recs if not p['is_actionable']]
    
    if neutral_picks:
        print(f"\n{len(neutral_picks)} stocks filtered out as Neutral:")
        for pick in neutral_picks:
            print(f"  - {pick['symbol']:12} Score: {pick['score']:3} → {pick['recommendation']} (Hidden)")
            if pick['note']:
                print(f"    Reason: {pick['note']}")
    else:
        print("\nNo Neutral picks - all stocks are actionable")
    
    # Verification
    print("\n" + "=" * 80)
    print("VERIFICATION")
    print("=" * 80)
    
    # Check that Neutral picks are not in actionable list
    neutral_symbols = {p['symbol'] for p in neutral_picks}
    actionable_symbols = {p['symbol'] for p in actionable_picks}
    
    assert not (neutral_symbols & actionable_symbols), "ERROR: Neutral picks found in actionable list!"
    print("✅ No Neutral picks in actionable list")
    
    # Check that all actionable have correct flag
    for pick in actionable_picks:
        assert pick['is_actionable'] == True, f"ERROR: {pick['symbol']} marked actionable but flag is False!"
    print("✅ All actionable picks have is_actionable=True")
    
    # Check that top 5 are sorted by score
    for i in range(len(top_5) - 1):
        assert top_5[i]['score'] >= top_5[i+1]['score'], "ERROR: Top picks not sorted by score!"
    print("✅ Top picks properly sorted by score")
    
    # Check recommendations match scores
    for pick in results_with_recs:
        score = pick['score']
        rec = pick['recommendation']
        
        if score >= 70:
            assert rec in ['Strong Buy', 'Buy'], f"ERROR: Score {score} should be Strong Buy/Buy, got {rec}"
        elif score >= 55:
            assert rec in ['Buy', 'Neutral'], f"ERROR: Score {score} should be Buy/Neutral, got {rec}"
        elif score >= 45:
            assert rec == 'Neutral', f"ERROR: Score {score} should be Neutral, got {rec}"
        else:
            assert rec in ['Sell', 'Neutral'], f"ERROR: Score {score} should be Sell/Neutral, got {rec}"
    print("✅ All recommendations match score thresholds")
    
    print("\n" + "=" * 80)
    print("🎉 INTEGRATION TEST PASSED!")
    print("=" * 80)
    print("\n✅ Complete flow working:")
    print("   1. Recommendations applied based on score + risk/reward")
    print("   2. Neutral picks properly filtered")
    print("   3. Top 5 shows only actionable opportunities")
    print("   4. Variable count handling (< 5 picks if needed)")
    print("   5. Sorting and ranking correct")
    print()


if __name__ == "__main__":
    try:
        test_integration_flow()
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
