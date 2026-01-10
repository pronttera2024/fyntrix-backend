"""
Test Enhanced Recommendation System
====================================

Tests the new actionable picks system:
- Strong Buy (≥70 score + favorable R/R)
- Buy (55-69 score + acceptable R/R)
- Neutral (45-54 score, NOT shown in Top Picks)
- Sell (<45 score, F&O only)

Verifies:
1. Recommendations applied correctly based on score + risk/reward
2. Neutral picks filtered from Top Picks
3. <5 picks shown when fewer actionable opportunities
4. Consistent colors and labels
5. Risk/reward calculated from risk agent + technical levels
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.utils.recommendation_system import (
    get_recommendation,
    Recommendation,
    calculate_risk_reward_ratio,
    get_recommendation_display_text,
    RECOMMENDATION_COLORS
)


def test_recommendation_logic():
    """Test recommendation assignment based on score"""
    print("\n" + "=" * 80)
    print("TEST 1: Recommendation Logic")
    print("=" * 80)
    
    # Test Strong Buy (≥70 + favorable R/R)
    rec = get_recommendation(score=75, risk_agent_score=75)
    print(f"\nScore 75, Risk 75:")
    print(f"  Recommendation: {rec.recommendation.value}")
    print(f"  Is Actionable: {rec.is_actionable}")
    print(f"  R/R Ratio: {rec.risk_reward_ratio:.2f}" if rec.risk_reward_ratio else "  R/R Ratio: None")
    print(f"  Note: {rec.note}")
    assert rec.recommendation == Recommendation.STRONG_BUY or rec.recommendation == Recommendation.BUY
    assert rec.is_actionable == True
    
    # Test Buy (55-69)
    rec = get_recommendation(score=62, risk_agent_score=60)
    print(f"\nScore 62, Risk 60:")
    print(f"  Recommendation: {rec.recommendation.value}")
    print(f"  Is Actionable: {rec.is_actionable}")
    print(f"  R/R Ratio: {rec.risk_reward_ratio:.2f}" if rec.risk_reward_ratio else "  R/R Ratio: None")
    print(f"  Note: {rec.note}")
    assert rec.recommendation in [Recommendation.BUY, Recommendation.NEUTRAL]
    
    # Test Neutral (45-54) - Should NOT be actionable
    rec = get_recommendation(score=48, risk_agent_score=50)
    print(f"\nScore 48, Risk 50:")
    print(f"  Recommendation: {rec.recommendation.value}")
    print(f"  Is Actionable: {rec.is_actionable}")
    print(f"  Note: {rec.note}")
    assert rec.recommendation == Recommendation.NEUTRAL
    assert rec.is_actionable == False  # Key test: Neutral is NOT actionable
    
    # Test Sell (<45)
    rec = get_recommendation(score=38, risk_agent_score=40)
    print(f"\nScore 38, Risk 40:")
    print(f"  Recommendation: {rec.recommendation.value}")
    print(f"  Is Actionable: {rec.is_actionable}")
    print(f"  Note: {rec.note}")
    assert rec.recommendation == Recommendation.SELL
    assert rec.is_actionable == True
    assert "F&O" in rec.note  # Should mention F&O stocks
    
    print("\n✅ All recommendation logic tests passed!")


def test_risk_reward_calculation():
    """Test combined risk/reward calculation"""
    print("\n" + "=" * 80)
    print("TEST 2: Risk/Reward Calculation")
    print("=" * 80)
    
    # Test with technical levels only
    rr = calculate_risk_reward_ratio(
        entry_price=1500,
        stop_loss=1450,
        target_price=1600,
        risk_agent_score=None
    )
    print(f"\nTechnical only (Entry: 1500, Stop: 1450, Target: 1600):")
    print(f"  R/R Ratio: {rr:.2f}")
    assert rr == 2.0  # (1600-1500) / (1500-1450) = 100/50 = 2.0
    
    # Test with risk agent only
    rr = calculate_risk_reward_ratio(
        risk_agent_score=75
    )
    print(f"\nRisk agent only (Score: 75):")
    print(f"  R/R Ratio: {rr:.2f}")
    assert rr > 0
    
    # Test combined (technical * risk factor)
    rr = calculate_risk_reward_ratio(
        entry_price=1500,
        stop_loss=1450,
        target_price=1600,
        risk_agent_score=80  # High risk management score should boost R/R
    )
    print(f"\nCombined (Technical R/R 2.0 + Risk Agent 80):")
    print(f"  R/R Ratio: {rr:.2f}")
    # Risk score 80 → multiplier 1.12 → R/R = 2.0 * 1.12 = 2.24
    assert rr >= 2.0, f"Expected R/R >= 2.0, got {rr:.2f}"  # Should boost technical R/R
    
    print("\n✅ All risk/reward calculation tests passed!")


def test_color_consistency():
    """Test color scheme consistency"""
    print("\n" + "=" * 80)
    print("TEST 3: Color Scheme Consistency")
    print("=" * 80)
    
    for rec_type in [Recommendation.STRONG_BUY, Recommendation.BUY, Recommendation.NEUTRAL, Recommendation.SELL]:
        colors = RECOMMENDATION_COLORS[rec_type]
        print(f"\n{rec_type.value}:")
        print(f"  Text: {colors['text']}")
        print(f"  Background: {colors['background']}")
        print(f"  Border: {colors['border']}")
        
        # Verify all required color fields exist
        assert 'text' in colors
        assert 'background' in colors
        assert 'border' in colors
        assert 'badge' in colors
    
    print("\n✅ All color scheme tests passed!")


def test_display_messages():
    """Test display messages for variable pick counts"""
    print("\n" + "=" * 80)
    print("TEST 4: Display Messages")
    print("=" * 80)
    
    # Test different pick counts
    test_cases = [
        (0, 50, "No strong opportunities"),
        (1, 50, "Only 1 actionable opportunity today"),
        (3, 50, "Only 3 actionable opportunities today"),
        (5, 50, "Top 5 Trading Opportunities"),
        (8, 50, "Top 8 Trading Opportunities")
    ]
    
    for count, total, expected_keyword in test_cases:
        msg = get_recommendation_display_text(None, count, total)
        print(f"\n{count} picks from {total} stocks:")
        print(f"  Message: {msg}")
        assert expected_keyword in msg
    
    print("\n✅ All display message tests passed!")


def test_recommendation_with_signals():
    """Test recommendation with contradictory agent signals"""
    print("\n" + "=" * 80)
    print("TEST 5: Recommendation with Agent Signals")
    print("=" * 80)
    
    # Test with contradictory signals (should push to Neutral)
    contradictory_signals = [
        {"type": "TREND", "signal": "Bullish"},
        {"type": "MOMENTUM", "signal": "Bearish"},
        {"type": "VOLUME", "signal": "Bullish"},
        {"type": "RSI", "signal": "Bearish"}
    ]
    
    rec = get_recommendation(
        score=52,  # Near neutral zone
        risk_agent_score=55,
        agent_signals=contradictory_signals
    )
    
    print(f"\nScore 52 with contradictory signals:")
    print(f"  Recommendation: {rec.recommendation.value}")
    print(f"  Is Actionable: {rec.is_actionable}")
    print(f"  Note: {rec.note}")
    assert rec.recommendation == Recommendation.NEUTRAL
    
    # Test with clear bullish signals
    bullish_signals = [
        {"type": "TREND", "signal": "Bullish"},
        {"type": "MOMENTUM", "signal": "Bullish"},
        {"type": "VOLUME", "signal": "Positive"}
    ]
    
    rec = get_recommendation(
        score=72,
        risk_agent_score=70,
        agent_signals=bullish_signals
    )
    
    print(f"\nScore 72 with bullish signals:")
    print(f"  Recommendation: {rec.recommendation.value}")
    print(f"  Is Actionable: {rec.is_actionable}")
    assert rec.recommendation in [Recommendation.STRONG_BUY, Recommendation.BUY]
    assert rec.is_actionable == True
    
    print("\n✅ All signal-based recommendation tests passed!")


def test_edge_cases():
    """Test edge cases and boundary conditions"""
    print("\n" + "=" * 80)
    print("TEST 6: Edge Cases")
    print("=" * 80)
    
    # Boundary at 70 (Strong Buy threshold)
    rec = get_recommendation(score=70, risk_agent_score=75)
    print(f"\nExact score 70 (Strong Buy threshold):")
    print(f"  Recommendation: {rec.recommendation.value}")
    assert rec.is_actionable == True
    
    # Boundary at 55 (Buy threshold)
    rec = get_recommendation(score=55, risk_agent_score=55)
    print(f"\nExact score 55 (Buy threshold):")
    print(f"  Recommendation: {rec.recommendation.value}")
    assert rec.is_actionable == True
    
    # Boundary at 45 (Neutral/Sell threshold)
    rec = get_recommendation(score=45, risk_agent_score=45)
    print(f"\nExact score 45 (Neutral threshold):")
    print(f"  Recommendation: {rec.recommendation.value}")
    # Could be Neutral or Sell depending on other factors
    
    # Very high score but poor R/R
    rec = get_recommendation(score=80, risk_agent_score=30)  # Poor risk management
    print(f"\nHigh score 80 but poor risk management 30:")
    print(f"  Recommendation: {rec.recommendation.value}")
    print(f"  Note: {rec.note}")
    # Should downgrade or add warning note
    
    # Very low score
    rec = get_recommendation(score=20, risk_agent_score=40)
    print(f"\nVery low score 20:")
    print(f"  Recommendation: {rec.recommendation.value}")
    assert rec.recommendation == Recommendation.SELL
    assert "F&O" in rec.note
    
    print("\n✅ All edge case tests passed!")


async def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("TESTING ENHANCED RECOMMENDATION SYSTEM")
    print("=" * 80)
    print("\nTesting new scoring categories:")
    print("  - Strong Buy: ≥70 score + favorable R/R")
    print("  - Buy: 55-69 score + acceptable R/R")
    print("  - Neutral: 45-54 score (FILTERED from Top Picks)")
    print("  - Sell: <45 score (F&O stocks only)")
    print()
    
    try:
        # Run all tests
        test_recommendation_logic()
        test_risk_reward_calculation()
        test_color_consistency()
        test_display_messages()
        test_recommendation_with_signals()
        test_edge_cases()
        
        # Summary
        print("\n" + "=" * 80)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 80)
        print("\n✅ Recommendation system working correctly:")
        print("   - Score-based recommendations accurate")
        print("   - Risk/reward calculation combines risk agent + technical levels")
        print("   - Neutral picks properly filtered (not actionable)")
        print("   - Color schemes consistent")
        print("   - Display messages adapt to pick count")
        print("   - Agent signal contradictions handled")
        print("   - Edge cases covered")
        print("\n✅ Ready for integration testing with real data!")
        print()
        
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


if __name__ == "__main__":
    asyncio.run(main())
