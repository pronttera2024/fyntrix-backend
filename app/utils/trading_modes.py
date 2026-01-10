"""
Trading Modes System
====================

Manages primary trading mode selection and strategy generation.

Key Concept:
- ONE primary mode per session (Intraday, Delivery, Options, Futures)
- Other modes can be auxiliary (only tweak agent weights)
- Strategy generation focuses on primary mode

This prevents conflicting strategies and provides clear, actionable plans.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class TradingMode(str, Enum):
    """Available trading modes"""
    SCALPING = "Scalping"
    INTRADAY = "Intraday"
    SWING = "Swing"  # Encompasses multi-day to long-term (formerly Delivery/Positional)
    OPTIONS = "Options"
    FUTURES = "Futures"
    COMMODITY = "Commodity"


@dataclass
class ModeConfiguration:
    """Configuration for a trading mode"""
    name: str
    display_name: str
    primary_weights: Dict[str, float]  # Agent weights when this is primary
    auxiliary_boost: Dict[str, float]  # Weight adjustments when auxiliary
    horizon: str  # Time horizon (e.g., "1 day", "1-2 weeks")
    strategy_type: str  # Type of strategy to generate
    risk_multiplier: float  # Risk adjustment factor
    description: str


# Mode Configurations
MODE_CONFIGS = {
    TradingMode.SCALPING: ModeConfiguration(
        name="Scalping",
        display_name="⚡ Scalping",
        primary_weights={
            "scalping": 0.45,          # Increased: Liquidity & spread most critical
            "microstructure": 0.25,    # Increased: Order flow shows immediate direction
            "technical": 0.20,         # Reduced: Only fast momentum indicators
            "market_regime": 0.10      # NEW: Overall trend bias for scalp direction
            # Removed sentiment & pattern - too slow for seconds-to-minutes
        },
        auxiliary_boost={
            "scalping": 0.05,
            "microstructure": 0.03
        },
        horizon="Seconds to minutes",
        strategy_type="ultra_scalp",
        risk_multiplier=1.5,  # Higher risk for ultra-short trades
        description="Ultra-short-term trades (seconds to minutes). Focus on tight spreads, volume spikes, and order flow."
    ),
    
    TradingMode.INTRADAY: ModeConfiguration(
        name="Intraday",
        display_name="Intraday Trading",
        primary_weights={
            "technical": 0.30,              # Core: Support/Resistance, momentum
            "pattern_recognition": 0.20,    # FIXED KEY + Increased: Breakout patterns critical
            "microstructure": 0.20,         # Volume spikes confirm moves
            "market_regime": 0.15,          # NEW: Day's trend direction (range vs trend)
            "sentiment": 0.10,              # Day's news catalysts
            "options": 0.05                 # Reduced: Minor indicator for intraday
            # Removed risk (global weight 0% anyway)
        },
        auxiliary_boost={
            "microstructure": 0.05,
            "pattern": 0.02
        },
        horizon="Same day",
        strategy_type="intraday_scalp",
        risk_multiplier=1.2,  # Higher risk tolerance for intraday
        description="Quick trades within market hours. Focus on technical levels, volume, and momentum."
    ),
    
    TradingMode.SWING: ModeConfiguration(
        name="Swing",
        display_name="🔄 Swing",
        primary_weights={
            # NOTE: These are fallback weights. Primary weights loaded from config/mode_weights.json
            "technical": 0.15,              # Technical for entry timing
            "global": 0.20,                 # Global macro trends critical
            "policy": 0.18,                 # Policy and macro events major drivers
            "pattern_recognition": 0.12,    # Multi-day patterns (H&S, triangles)
            "sentiment": 0.08,              # Long-term sentiment trends
            "market_regime": 0.08,          # Market regime awareness
            "risk": 0.10,                   # Risk assessment important
            "options": 0.10,                # Positioning signals
            "microstructure": 0.02,         # Minimal relevance for long-term
            "watchlist": 0.02               # Quality over momentum
        },
        auxiliary_boost={
            "global": 0.03,
            "policy": 0.02
        },
        horizon="3-7 days",
        strategy_type="swing_trend",
        risk_multiplier=1.0,  # Standard risk
        description="Multi-day to long-term trades. Focus on macro trends, fundamentals, policy, multi-day patterns, and structural trends."
    ),
    
    TradingMode.OPTIONS: ModeConfiguration(
        name="Options",
        display_name="Options Trading",
        primary_weights={
            "options": 0.40,                # Increased: IV, OI, Greeks, 5 advanced strategies
            "pattern_recognition": 0.20,    # FIXED KEY + Increased: Entry/exit timing critical
            "market_regime": 0.15,          # NEW: Directional bias (calls in bull, puts in bear)
            "technical": 0.15,              # Reduced: Support entry timing only
            "sentiment": 0.10               # Event-driven moves
            # Removed microstructure & risk (Options agent handles these)
        },
        auxiliary_boost={
            "options": 0.05,
            "risk": 0.03
        },
        horizon="1-5 days",
        strategy_type="options_greek",
        risk_multiplier=1.5,  # Higher risk for options
        description="Options strategies. Focus on Greeks, IV, OI changes, and volatility."
    ),
    
    TradingMode.FUTURES: ModeConfiguration(
        name="Futures",
        display_name="Futures Trading",
        primary_weights={
            "technical": 0.30,              # Momentum indicators: MACD, RSI
            "market_regime": 0.25,          # NEW: CRITICAL for leverage direction - don't fight trend
            "pattern_recognition": 0.20,    # NEW: Breakout/continuation patterns with leverage
            "microstructure": 0.15,         # Reduced: Still need volume confirmation
            "global": 0.10                  # Global market cues
            # Removed options, risk, sentiment for focused momentum trading
        },
        auxiliary_boost={
            "technical": 0.04,
            "microstructure": 0.03
        },
        horizon="1-7 days",
        strategy_type="futures_momentum",
        risk_multiplier=1.3,  # Higher risk for leverage
        description="Futures trading. Focus on momentum, rollover patterns, and leverage management."
    ),
    
    TradingMode.COMMODITY: ModeConfiguration(
        name="Commodity",
        display_name="Commodity Trading",
        primary_weights={
            "global": 0.25,
            "technical": 0.25,
            "policy": 0.20,
            "sentiment": 0.15,
            "risk": 0.15
        },
        auxiliary_boost={
            "global": 0.04,
            "policy": 0.03
        },
        horizon="1-4 weeks",
        strategy_type="commodity_macro",
        risk_multiplier=1.1,
        description="Commodity trading. Focus on global markets, macro policies, and supply/demand."
    )
}


def get_agent_weights(
    primary_mode: TradingMode,
    auxiliary_modes: Optional[List[TradingMode]] = None,
    risk_profile: str = "Moderate"
) -> Dict[str, float]:
    """
    Calculate agent weights based on primary and auxiliary modes
    
    Args:
        primary_mode: The primary trading mode
        auxiliary_modes: List of auxiliary modes (optional)
        risk_profile: Risk profile (Aggressive, Moderate, Conservative)
    
    Returns:
        Dictionary of agent weights (normalized to sum to 1.0)
    """
    if auxiliary_modes is None:
        auxiliary_modes = []
    
    # Start with primary mode weights
    config = MODE_CONFIGS[primary_mode]
    weights = dict(config.primary_weights)
    
    # Apply risk profile adjustments
    if risk_profile == "Aggressive":
        # Boost technical and microstructure for aggressive
        weights["technical"] = weights.get("technical", 0.2) * 1.2
        weights["microstructure"] = weights.get("microstructure", 0.1) * 1.3
        weights["risk"] = weights.get("risk", 0.1) * 0.8  # Reduce risk weight for aggressive
    elif risk_profile == "Conservative":
        # Boost sentiment, global, policy for conservative
        weights["sentiment"] = weights.get("sentiment", 0.1) * 1.3
        weights["global"] = weights.get("global", 0.1) * 1.2
        weights["policy"] = weights.get("policy", 0.08) * 1.2
        weights["risk"] = weights.get("risk", 0.1) * 1.3  # Increase risk weight for conservative
    
    # Apply auxiliary mode boosts
    for aux_mode in auxiliary_modes:
        if aux_mode != primary_mode and aux_mode in MODE_CONFIGS:
            aux_config = MODE_CONFIGS[aux_mode]
            for agent, boost in aux_config.auxiliary_boost.items():
                weights[agent] = weights.get(agent, 0.0) + boost
    
    # Normalize to sum to 1.0
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}
    
    return weights


def get_strategy_parameters(
    primary_mode: TradingMode,
    score: float,
    current_price: Optional[float] = None
) -> Dict[str, any]:
    """
    Get strategy parameters based on primary mode
    
    Args:
        primary_mode: The primary trading mode
        score: Blend score (0-100)
        current_price: Current stock price
    
    Returns:
        Dictionary with strategy parameters
    """
    config = MODE_CONFIGS[primary_mode]
    
    # Base parameters
    params = {
        "horizon": config.horizon,
        "strategy_type": config.strategy_type,
        "risk_multiplier": config.risk_multiplier,
        "mode": config.name
    }
    
    # Mode-specific parameters
    if primary_mode == TradingMode.SCALPING:
        params.update({
            "target_percent": 0.3 if score >= 70 else 0.2,  # 0.2-0.3% targets
            "stop_percent": 0.15,  # Very tight stops
            "hold_duration": "Seconds to minutes",
            "exit_time": "Immediate on target/stop",
            "focus": ["Tight Spread", "Volume Spikes", "Order Flow", "Tick Movements"],
            "liquidity_requirement": "High - only liquid stocks",
            "execution_speed": "Critical - use limit orders"
        })
    
    elif primary_mode == TradingMode.INTRADAY:
        params.update({
            "target_percent": 1.5 if score >= 70 else 1.0,  # 1-1.5% targets
            "stop_percent": 0.8,  # Tight stops
            "hold_duration": "Same day",
            "exit_time": "3:15 PM",
            "focus": ["Breakouts", "Support/Resistance", "Volume Spikes"]
        })
    
    elif primary_mode == TradingMode.SWING:
        params.update({
            "target_percent": 8.0 if score >= 70 else 5.0,  # 5-8% targets
            "stop_percent": 3.0,  # Wider stops
            "hold_duration": "3-7 days",
            "exit_time": None,
            "focus": ["Macro Trends", "Multi-day Patterns", "Policy Events", "Fundamentals"]
        })
    
    elif primary_mode == TradingMode.OPTIONS:
        params.update({
            "target_percent": 25.0 if score >= 70 else 15.0,  # 15-25% on premium
            "stop_percent": 30.0,  # Options can move quickly
            "hold_duration": "1-5 days",
            "exit_time": "Before expiry",
            "focus": ["IV Changes", "OI Buildup", "Greeks", "Theta Decay"],
            "strategy_hint": "Consider buying ATM/OTM calls/puts based on directional view"
        })
    
    elif primary_mode == TradingMode.FUTURES:
        params.update({
            "target_percent": 4.0 if score >= 70 else 2.5,  # 2.5-4% on margin
            "stop_percent": 1.5,  # Tight stops due to leverage
            "hold_duration": "1-7 days",
            "exit_time": None,
            "focus": ["Momentum", "Rollover Premium", "Leverage Management"],
            "leverage_note": "Use 2-3x leverage max, maintain margin buffer"
        })
    
    elif primary_mode == TradingMode.COMMODITY:
        params.update({
            "target_percent": 6.0 if score >= 70 else 4.0,  # 4-6% targets
            "stop_percent": 2.5,
            "hold_duration": "1-4 weeks",
            "exit_time": None,
            "focus": ["Global Demand", "Policy Changes", "Currency Impact"]
        })
    
    # Calculate actual prices if current_price provided
    if current_price:
        target_pct = params["target_percent"] / 100
        stop_pct = params["stop_percent"] / 100
        
        params["target_price"] = round(current_price * (1 + target_pct), 2)
        params["stop_loss"] = round(current_price * (1 - stop_pct), 2)
        params["risk_reward"] = round(params["target_percent"] / params["stop_percent"], 2)
    
    return params


def get_mode_display_info(mode: TradingMode) -> Dict[str, str]:
    """
    Get display information for a mode
    
    Args:
        mode: Trading mode
    
    Returns:
        Dictionary with display information
    """
    config = MODE_CONFIGS[mode]
    return {
        "name": config.name,
        "display_name": config.display_name,
        "description": config.description,
        "horizon": config.horizon,
        "icon": _get_mode_icon(mode)
    }


def _get_mode_icon(mode: TradingMode) -> str:
    """Get emoji icon for mode"""
    icons = {
        TradingMode.SCALPING: "⚡",
        TradingMode.INTRADAY: "📊",
        TradingMode.SWING: "🔄",
        TradingMode.OPTIONS: "🎯",
        TradingMode.FUTURES: "🚀",
        TradingMode.COMMODITY: "🌍"
    }
    return icons.get(mode, "📊")


def validate_mode_combination(
    primary_mode: TradingMode,
    auxiliary_modes: List[TradingMode]
) -> Tuple[bool, Optional[str]]:
    """
    Validate if mode combination makes sense
    
    Args:
        primary_mode: Primary mode
        auxiliary_modes: List of auxiliary modes
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Can't have primary in auxiliary
    if primary_mode in auxiliary_modes:
        return False, f"{primary_mode} cannot be both primary and auxiliary"
    
    # Some combinations don't make sense
    incompatible = {
        TradingMode.INTRADAY: [TradingMode.COMMODITY],  # Commodities not for intraday
        TradingMode.OPTIONS: [TradingMode.FUTURES],  # Choose one derivative
        TradingMode.FUTURES: [TradingMode.OPTIONS]
    }
    
    if primary_mode in incompatible:
        for aux in auxiliary_modes:
            if aux in incompatible[primary_mode]:
                return False, f"{primary_mode} and {aux} are incompatible"
    
    # Max 2 auxiliary modes
    if len(auxiliary_modes) > 2:
        return False, "Maximum 2 auxiliary modes allowed"
    
    return True, None


def normalize_mode(mode: Optional[str]) -> str:
    """Normalize a raw mode string to a canonical trading mode name."""
    if mode is None:
        return "Swing"

    text = str(mode).strip()
    if not text:
        return "Swing"

    lower = text.lower()
    if lower in ("delivery", "positional"):
        return "Swing"

    # Basic normalization: title case to align with typical mode values
    return text.title()


# Export
__all__ = [
    'TradingMode',
    'ModeConfiguration',
    'MODE_CONFIGS',
    'get_agent_weights',
    'get_strategy_parameters',
    'get_mode_display_info',
    'validate_mode_combination',
    'normalize_mode'
]
