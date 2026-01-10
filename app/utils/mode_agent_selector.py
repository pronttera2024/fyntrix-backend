"""
Mode-Specific Agent Selection

Optimizes performance by selecting only relevant agents for each trading mode.
This reduces analysis time while maintaining accuracy.
"""

from typing import List, Dict, Any
from enum import Enum

from .trading_modes import normalize_mode


class TradingMode(str, Enum):
    """Trading modes supported by ARISE"""
    SCALPING = "Scalping"
    INTRADAY = "Intraday"
    SWING = "Swing"
    OPTIONS = "Options"
    FUTURES = "Futures"
    COMMODITIES = "Commodities"


# Agent Selection Matrix
# Each mode has specific agents that matter most for that timeframe/style
MODE_AGENT_MAP: Dict[str, List[str]] = {
    # SCALPING & INTRADAY: Fast-moving, focus on technical + microstructure
    "Scalping": [
        "technical",              # Price action, indicators
        "pattern_recognition",   # Chart patterns
        "microstructure",        # Order book depth + spread + liquidity
        "risk",                  # Position sizing
        "market_regime",         # Bull/bear/sideways
        "sentiment",             # News sentiment (fast-moving)
        "options",               # Options flow for scalping
    ],
    
    "Intraday": [
        "technical",              # Price action, indicators
        "pattern_recognition",   # Chart patterns
        "microstructure",        # Order flow + entry/exit timing
        "risk",                  # Position sizing
        "market_regime",         # Market direction
        "sentiment",             # Intraday news
        "options",               # Options activity (institutional flow)
    ],
    
    # SWING & POSITIONAL: Longer timeframe, comprehensive analysis
    "Swing": [
        "technical",              # Technical analysis
        "pattern_recognition",   # Chart patterns
        "market_regime",         # Market phase
        "global",                # Global correlations
        "options",               # Options flow
        "sentiment",             # Market sentiment
        "policy",                # Policy/macro events
        "watchlist_intelligence", # Watchlist recommendations
        "risk",                  # Risk management
        "trade_strategy",        # Trade plan generation
    ],
    
    # OPTIONS: Focus on volatility, Greeks, and options-specific factors
    "Options": [
        "options",               # PRIMARY: IV, PCR, max pain, strategies
        "technical",             # Underlying price action
        "pattern_recognition",   # Support/resistance for strikes
        "market_regime",         # Volatility regime
        "sentiment",             # News impact on IV
        "global",                # VIX, global vol
        "risk",                  # Options risk (Greeks)
        "policy",                # Policy events (high IV)
    ],
    
    # FUTURES: Similar to Intraday but with global correlations
    "Futures": [
        "technical",              # Price action
        "pattern_recognition",   # Chart patterns
        "market_regime",         # Market direction
        "global",                # Global futures correlations
        "sentiment",             # Market sentiment
        "policy",                # Policy impact on commodities/indices
        "options",               # Options-futures parity
        "risk",                  # Leverage risk
        "microstructure",        # Order flow
    ],
    
    # COMMODITIES: Global macro focus
    "Commodities": [
        "technical",              # Price action
        "pattern_recognition",   # Chart patterns
        "global",                # PRIMARY: Global supply/demand
        "policy",                # PRIMARY: Central bank, tariffs, regulations
        "market_regime",         # Commodity cycles
        "sentiment",             # Commodity sentiment
        "risk",                  # Volatility risk
        "options",               # Commodity options activity
    ],
}


def get_agents_for_mode(mode: str) -> List[str]:
    """
    Get the list of relevant agents for a trading mode.
    
    Args:
        mode: Trading mode (Scalping, Intraday, Swing, etc.)
        
    Returns:
        List of agent names to use for analysis
        
    Example:
        >>> get_agents_for_mode("Scalping")
        ['technical', 'pattern_recognition', 'scalping', 'microstructure', 'risk', 'market_regime', 'sentiment']
    """
    # Normalize mode name
    mode = normalize_mode(mode)
    mode = mode.strip().title()
    
    # Return agent list or default to all agents for Swing
    return MODE_AGENT_MAP.get(mode, MODE_AGENT_MAP["Swing"])


def get_agent_weights_for_mode(mode: str) -> Dict[str, float]:
    """
    Get optimized agent weights for a specific trading mode.
    
    Args:
        mode: Trading mode
        
    Returns:
        Dictionary of agent weights (sum = 1.0)
    """
    mode = normalize_mode(mode)
    mode = mode.strip().title()
    
    # Mode-specific weight distributions
    weight_configs = {
        "Scalping": {
            "technical": 0.25,
            "pattern_recognition": 0.20,
            "scalping": 0.18,
            "microstructure": 0.15,
            "market_regime": 0.12,
            "sentiment": 0.07,
            "risk": 0.03,
        },
        
        "Intraday": {
            "technical": 0.22,
            "pattern_recognition": 0.18,
            "scalping": 0.12,
            "market_regime": 0.15,
            "options": 0.12,
            "microstructure": 0.10,
            "sentiment": 0.08,
            "risk": 0.03,
        },
        
        "Swing": {
            "technical": 0.20,
            "pattern_recognition": 0.18,
            "market_regime": 0.15,
            "global": 0.12,
            "options": 0.12,
            "sentiment": 0.10,
            "policy": 0.08,
            "watchlist_intelligence": 0.03,
            "risk": 0.01,
            "personalization": 0.01,
            "trade_strategy": 0.00,
        },
        
        "Options": {
            "options": 0.35,          # PRIMARY for options
            "technical": 0.18,
            "pattern_recognition": 0.15,
            "market_regime": 0.12,
            "global": 0.08,
            "sentiment": 0.05,
            "policy": 0.04,
            "risk": 0.02,
            "personalization": 0.01,
        },
        
        "Futures": {
            "technical": 0.22,
            "pattern_recognition": 0.18,
            "market_regime": 0.15,
            "global": 0.15,
            "sentiment": 0.10,
            "policy": 0.08,
            "options": 0.05,
            "microstructure": 0.04,
            "risk": 0.03,
        },
        
        "Commodities": {
            "global": 0.25,           # PRIMARY for commodities
            "policy": 0.20,           # PRIMARY for commodities
            "technical": 0.18,
            "pattern_recognition": 0.15,
            "market_regime": 0.10,
            "sentiment": 0.07,
            "options": 0.03,
            "risk": 0.02,
        },
    }
    
    # Return weights or default to Swing
    return weight_configs.get(mode, weight_configs["Swing"])


def get_analysis_depth(mode: str) -> str:
    """
    Get the recommended analysis depth for a trading mode.
    
    Args:
        mode: Trading mode
        
    Returns:
        'fast', 'standard', or 'comprehensive'
    """
    mode = normalize_mode(mode)
    mode = mode.strip().title()
    
    depth_map = {
        "Scalping": "fast",        # Minimal analysis, speed critical
        "Intraday": "fast",        # Quick analysis
        "Swing": "standard",       # Balanced
        "Options": "standard",     # Options-specific depth
        "Futures": "standard",     # Moderate depth
        "Commodities": "comprehensive",  # Global macro needs depth
    }
    
    return depth_map.get(mode, "standard")


def get_performance_estimate(mode: str, universe_size: int) -> Dict[str, Any]:
    """
    Estimate analysis time for a mode and universe size.
    
    Args:
        mode: Trading mode
        universe_size: Number of symbols to analyze
        
    Returns:
        Performance estimate with time and agent count
    """
    norm_mode = normalize_mode(mode)
    agents = get_agents_for_mode(norm_mode)
    agent_count = len(agents)
    
    # Time estimates (seconds per symbol)
    time_per_symbol = {
        "fast": 1.5,           # Scalping/Intraday
        "standard": 2.5,       # Swing/Options/Futures
        "comprehensive": 4.0,  # Positional/Commodities
    }
    
    depth = get_analysis_depth(norm_mode)
    base_time = time_per_symbol[depth]
    
    # Parallel execution improves performance
    # Assume 5 concurrent symbol analyses
    parallel_factor = min(5, universe_size)
    total_time = (universe_size / parallel_factor) * base_time
    
    return {
        "mode": norm_mode,
        "agent_count": agent_count,
        "agents": agents,
        "analysis_depth": depth,
        "universe_size": universe_size,
        "estimated_time_seconds": round(total_time, 1),
        "estimated_time_display": f"{int(total_time // 60)}m {int(total_time % 60)}s" if total_time >= 60 else f"{int(total_time)}s"
    }


# Convenience function for API usage
def optimize_analysis_for_mode(
    mode: str,
    universe: List[str]
) -> Dict[str, Any]:
    """
    Complete optimization config for a trading mode.
    
    Args:
        mode: Trading mode
        universe: List of symbols
        
    Returns:
        Optimization configuration with agents, weights, and estimates
    """
    norm_mode = normalize_mode(mode)
    agents = get_agents_for_mode(norm_mode)
    weights = get_agent_weights_for_mode(norm_mode)
    estimate = get_performance_estimate(norm_mode, len(universe))
    
    return {
        "mode": mode,
        "agents_to_use": agents,
        "agent_weights": weights,
        "performance_estimate": estimate,
        "optimization_level": get_analysis_depth(mode)
    }
