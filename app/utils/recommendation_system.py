"""
Enhanced Recommendation System for ARISE
==========================================

Provides consistent, actionable trade recommendations across all features.

Recommendation Categories:
--------------------------
1. Strong Buy: Score ≥70 + Highly favorable risk/reward
2. Buy:        Score 55-69 + Acceptable risk/reward  
3. Neutral:    Score 45-54 + Unclear signals (NOT shown in Top Picks)
4. Sell:       Score <45 + Bearish outlook (F&O stocks only)

Key Principles:
--------------
- Top Five Picks = ONLY actionable (Strong Buy, Buy, Sell)
- No "Hold" or "Neutral" in Top Picks
- Consistent scoring across all agents and features
- Risk/reward combines risk agent + technical analysis
"""

from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass
from enum import Enum


class Recommendation(str, Enum):
    """Recommendation categories"""
    STRONG_BUY = "Strong Buy"
    BUY = "Buy"
    NEUTRAL = "Neutral"
    SELL = "Sell"
    STRONG_SELL = "Strong Sell"


@dataclass
class RecommendationResult:
    """Complete recommendation with metadata"""
    recommendation: Recommendation
    score: float
    confidence: str
    color_scheme: Dict[str, str]
    risk_reward_ratio: Optional[float] = None
    is_actionable: bool = True
    note: Optional[str] = None


# Color schemes for consistent UI display
RECOMMENDATION_COLORS = {
    Recommendation.STRONG_BUY: {
        "text": "#166534",
        "background": "#dcfce7",
        "border": "#86efac",
        "badge": "bg-green-100 text-green-800 border-green-300"
    },
    Recommendation.BUY: {
        "text": "#15803d",
        "background": "#f0fdf4",
        "border": "#bbf7d0",
        "badge": "bg-green-50 text-green-700 border-green-200"
    },
    Recommendation.NEUTRAL: {
        "text": "#64748b",
        "background": "#f1f5f9",
        "border": "#cbd5e1",
        "badge": "bg-gray-100 text-gray-700 border-gray-300"
    },
    Recommendation.SELL: {
        "text": "#991b1b",
        "background": "#fee2e2",
        "border": "#fecaca",
        "badge": "bg-red-100 text-red-800 border-red-300"
    },
    Recommendation.STRONG_SELL: {
        "text": "#7f1d1d",
        "background": "#fee2e2",
        "border": "#b91c1c",
        "badge": "bg-red-200 text-red-900 border-red-400"
    }
}


def calculate_risk_reward_ratio(
    entry_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    target_price: Optional[float] = None,
    risk_agent_score: Optional[float] = None
) -> Optional[float]:
    """
    Calculate risk/reward ratio combining technical levels + risk agent
    
    Formula:
    - Technical R/R = (Target - Entry) / (Entry - Stop)
    - Risk Agent Factor = risk_score / 100
    - Combined R/R = Technical R/R * Risk Agent Factor
    
    Args:
        entry_price: Proposed entry price
        stop_loss: Stop loss level
        target_price: Target price level
        risk_agent_score: Risk agent score (0-100)
    
    Returns:
        Combined risk/reward ratio or None if cannot calculate
    """
    technical_rr = None
    
    # Calculate technical risk/reward if levels available
    if entry_price and stop_loss and target_price:
        risk = abs(entry_price - stop_loss)
        reward = abs(target_price - entry_price)
        
        if risk > 0:
            technical_rr = reward / risk
    
    # If no risk agent score, return technical R/R
    if risk_agent_score is None:
        return technical_rr
    
    # Combine with risk agent (normalized to 0-1 scale)
    risk_factor = risk_agent_score / 100.0
    
    if technical_rr is not None:
        # Both available - combine them
        # Higher risk score = better risk management = improves effective R/R
        # Formula: technical_rr * (0.8 + risk_factor * 0.4)
        # This gives: risk_score 100 → 1.2x multiplier, risk_score 50 → 1.0x, risk_score 0 → 0.8x
        return technical_rr * (0.8 + risk_factor * 0.4)
    else:
        # Only risk agent available - estimate R/R from risk score
        # Risk score 100 = ~3:1 R/R, Risk score 50 = ~1.5:1 R/R
        return 1.0 + (risk_factor * 2.0)


def assess_risk_reward_favorability(risk_reward_ratio: Optional[float]) -> str:
    """
    Assess if risk/reward is favorable, acceptable, or poor
    
    Args:
        risk_reward_ratio: Calculated R/R ratio
    
    Returns:
        "highly_favorable", "acceptable", or "poor"
    """
    if risk_reward_ratio is None:
        return "acceptable"  # Neutral if unknown
    
    if risk_reward_ratio >= 2.5:
        return "highly_favorable"  # 2.5:1 or better
    elif risk_reward_ratio >= 1.5:
        return "acceptable"  # 1.5:1 to 2.5:1
    else:
        return "poor"  # Less than 1.5:1


def get_recommendation(
    score: float,
    confidence: str = "Medium",
    risk_reward_ratio: Optional[float] = None,
    entry_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    target_price: Optional[float] = None,
    risk_agent_score: Optional[float] = None,
    agent_signals: Optional[List[Dict]] = None
) -> RecommendationResult:
    """
    Get recommendation based on score and risk/reward analysis
    
    Logic:
    ------
    1. Calculate risk/reward if not provided
    2. Determine base recommendation from score
    3. Adjust based on risk/reward favorability
    4. Check for contradictory agent signals (for Neutral)
    5. Return complete recommendation with metadata
    
    Args:
        score: Blend score (0-100)
        confidence: Confidence level (High/Medium/Low)
        risk_reward_ratio: Pre-calculated R/R ratio
        entry_price: Entry price for R/R calculation
        stop_loss: Stop loss for R/R calculation
        target_price: Target for R/R calculation
        risk_agent_score: Risk agent score
        agent_signals: List of agent signals for contradiction check
    
    Returns:
        RecommendationResult with recommendation and metadata
    """
    # Calculate risk/reward if not provided
    if risk_reward_ratio is None:
        risk_reward_ratio = calculate_risk_reward_ratio(
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_price=target_price,
            risk_agent_score=risk_agent_score
        )
    
    # Assess risk/reward favorability
    rr_favorability = assess_risk_reward_favorability(risk_reward_ratio)
    
    # Check for contradictory signals (for Neutral classification)
    has_contradictions = False
    if agent_signals:
        bullish_count = sum(1 for s in agent_signals if s.get('signal') in ['Bullish', 'Buy', 'Positive'])
        bearish_count = sum(1 for s in agent_signals if s.get('signal') in ['Bearish', 'Sell', 'Negative'])
        total_signals = len(agent_signals)
        
        if total_signals >= 3:  # Only check if we have enough signals
            # Contradictory if signals are split (within 30% of each other)
            if abs(bullish_count - bearish_count) <= total_signals * 0.3:
                has_contradictions = True
    
    # Determine recommendation based on score and risk/reward
    recommendation: Recommendation
    note: Optional[str] = None

    if score >= 70:
        # Strong Buy band
        if rr_favorability == "highly_favorable":
            recommendation = Recommendation.STRONG_BUY
        elif rr_favorability == "acceptable":
            recommendation = Recommendation.BUY
            note = "High score with acceptable risk/reward. Consider active management of position size."
        else:
            recommendation = Recommendation.BUY
            note = "High score but poor risk/reward. Wait for better entry or reduce position size."

    elif score >= 60:
        # Buy band
        if rr_favorability in ["highly_favorable", "acceptable"]:
            recommendation = Recommendation.BUY
        else:
            recommendation = Recommendation.NEUTRAL
            note = "Moderate positive score but unattractive risk/reward. Wait for better opportunity."

    elif score >= 45:
        # Neutral band
        recommendation = Recommendation.NEUTRAL
        if has_contradictions:
            note = "Mixed signals from agents. No clear directional bias."
        else:
            note = "Score in neutral zone. Monitor for clearer bullish or bearish setup."

    elif score >= 35:
        # Sell band
        if rr_favorability in ["highly_favorable", "acceptable"]:
            recommendation = Recommendation.SELL
            note = "Bearish outlook with acceptable risk/reward (typically for F&O stocks)."
        else:
            recommendation = Recommendation.NEUTRAL
            note = "Bearish tilt but poor risk/reward. Avoid taking fresh short positions."

    else:
        # Strong Sell band
        if rr_favorability in ["highly_favorable", "acceptable"] and not has_contradictions:
            recommendation = Recommendation.STRONG_SELL
            note = "Strongly bearish outlook with favorable risk/reward (primarily for F&O instruments)."
        else:
            recommendation = Recommendation.SELL
            note = "Very weak score but either mixed signals or poor risk/reward. Treat as Sell, not Strong Sell."
    
    # Get color scheme
    color_scheme = RECOMMENDATION_COLORS[recommendation]
    
    # Determine if actionable (not Neutral)
    is_actionable = recommendation != Recommendation.NEUTRAL
    
    return RecommendationResult(
        recommendation=recommendation,
        score=score,
        confidence=confidence,
        color_scheme=color_scheme,
        risk_reward_ratio=risk_reward_ratio,
        is_actionable=is_actionable,
        note=note
    )


def filter_actionable_picks(picks: List[Dict]) -> Tuple[List[Dict], int, int]:
    """
    Filter picks to only include actionable recommendations
    
    Args:
        picks: List of pick dictionaries with 'recommendation' field
    
    Returns:
        Tuple of (actionable_picks, actionable_count, total_count)
    """
    actionable = [
        pick for pick in picks 
        if pick.get('recommendation') not in [Recommendation.NEUTRAL, "Neutral", "Hold"]
    ]
    
    return actionable, len(actionable), len(picks)


def get_recommendation_display_text(recommendation: Recommendation, count: int, total: int) -> str:
    """
    Get display text for top picks section
    
    Args:
        recommendation: Type of recommendations
        count: Number of actionable picks
        total: Total stocks analyzed
    
    Returns:
        Display text for UI
    """
    if count == 0:
        return "No strong opportunities today. Market conditions unclear."
    elif count < 5:
        return f"Only {count} actionable opportunit{'y' if count == 1 else 'ies'} today"
    else:
        return f"Top {count} Trading Opportunities"


def format_pick_for_api(
    pick: Dict,
    rank: int,
    include_recommendation_details: bool = True
) -> Dict:
    """
    Format a pick for API response with consistent recommendation details
    
    Args:
        pick: Pick dictionary with analysis results
        rank: Rank in the list
        include_recommendation_details: Include color scheme and notes
    
    Returns:
        Formatted pick dictionary
    """
    # Get recommendation details
    rec_result = get_recommendation(
        score=pick.get('blend_score', pick.get('score', 50)),
        confidence=pick.get('confidence', 'Medium'),
        risk_reward_ratio=pick.get('risk_reward_ratio'),
        risk_agent_score=pick.get('risk_score'),
        agent_signals=pick.get('key_signals', [])
    )
    
    formatted = {
        **pick,
        'rank': rank,
        'recommendation': rec_result.recommendation.value,
        'is_actionable': rec_result.is_actionable
    }
    
    if include_recommendation_details:
        formatted.update({
            'recommendation_note': rec_result.note,
            'color_scheme': rec_result.color_scheme,
            'risk_reward_ratio': rec_result.risk_reward_ratio
        })
    
    return formatted


# Utility functions for agent scoring
def get_agent_recommendation(agent_score: float, agent_confidence: str = "Medium") -> str:
    """
    Get recommendation for individual agent score
    Uses same thresholds as main recommendation system
    
    Args:
        agent_score: Agent's score (0-100)
        agent_confidence: Agent's confidence level
    
    Returns:
        Recommendation string
    """
    result = get_recommendation(agent_score, agent_confidence)
    return result.recommendation.value


def get_agent_color(agent_score: float) -> Dict[str, str]:
    """
    Get color scheme for agent score display
    
    Args:
        agent_score: Agent's score (0-100)
    
    Returns:
        Color scheme dictionary
    """
    result = get_recommendation(agent_score)
    return result.color_scheme


# Export main functions
__all__ = [
    'Recommendation',
    'RecommendationResult',
    'get_recommendation',
    'filter_actionable_picks',
    'get_recommendation_display_text',
    'format_pick_for_api',
    'calculate_risk_reward_ratio',
    'get_agent_recommendation',
    'get_agent_color',
    'RECOMMENDATION_COLORS'
]
