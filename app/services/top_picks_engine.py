"""
ARISE Top Picks Engine
Automated daily stock recommendations using 7-agent analysis
"Trading Simplified" - AI finds the best opportunities for you
"""

import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import json
from pathlib import Path
import random
import numpy as np
import pandas as pd

from ..agents.coordinator import AgentCoordinator
from ..agents.technical_agent import TechnicalAgent
from ..agents.global_market_agent import GlobalMarketAgent
from ..agents.policy_macro_agent import PolicyMacroAgent
from ..agents.options_agent import OptionsAgent
from ..agents.sentiment_agent import SentimentAgent
from ..agents.microstructure_agent import MicrostructureAgent
from ..agents.risk_agent import RiskAgent
from ..agents.pattern_recognition_agent import PatternRecognitionAgent
from ..agents.market_regime_agent import MarketRegimeAgent
from ..agents.watchlist_intelligence_agent import WatchlistIntelligenceAgent
from ..agents.trade_strategy_agent import TradeStrategyAgent
from ..agents.auto_monitoring_agent import AutoMonitoringAgent
from ..agents.personalization_agent import PersonalizationAgent
from .intelligent_insights import generate_batch_insights
from .realtime_prices import enrich_picks_with_realtime_data
from .event_logger import log_event
from .chart_data_service import chart_data_service
from .policy_store import get_policy_store
from .support_resistance_redis import support_resistance_service
from .pick_logger import get_active_rl_policy
from ..providers import get_data_provider
from ..utils.trading_modes import normalize_mode, TradingMode, get_strategy_parameters
from ..core.market_hours import now_ist

# Import recommendation system for actionable picks
from ..utils.recommendation_system import (
    get_recommendation,
    filter_actionable_picks,
    get_recommendation_display_text
)


# Nifty 50 symbols (complete list)
NIFTY_50_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
    "LT", "AXISBANK", "ASIANPAINT", "MARUTI", "SUNPHARMA",
    "TITAN", "ULTRACEMCO", "NESTLEIND", "BAJFINANCE", "WIPRO",
    "ONGC", "NTPC", "POWERGRID", "COALINDIA", "TATAMOTORS",
    "TECHM", "HCLTECH", "INDUSINDBK", "DRREDDY", "CIPLA",
    "EICHERMOT", "TATASTEEL", "ADANIPORTS", "JSWSTEEL", "HINDALCO",
    "BRITANNIA", "HEROMOTOCO", "GRASIM", "SHREECEM", "TATACONSUM",
    "APOLLOHOSP", "DIVISLAB", "BAJAJFINSV", "BAJAJ-AUTO", "SBILIFE",
    "HDFCLIFE", "UPL", "BPCL", "M&M", "ADANIENT"
]

# Bank Nifty symbols (complete list, hardcoded for now)
BANKNIFTY_SYMBOLS = [
    "HDFCBANK", "ICICIBANK", "AXISBANK", "KOTAKBANK", "SBIN",
    "INDUSINDBK", "BANKBARODA", "PNB", "FEDERALBNK", "IDFCFIRSTB",
    "AUBANK", "BANDHANBNK"
]

# Additional universe options (placeholders for future expansion)
NIFTY_100_SYMBOLS = NIFTY_50_SYMBOLS + [
    # Add more when expanding
]

NIFTY_500_SYMBOLS = NIFTY_100_SYMBOLS + [
    # Add more when expanding
]

UNIVERSES = {
    "nifty50": NIFTY_50_SYMBOLS,
    "banknifty": BANKNIFTY_SYMBOLS,
    "nifty100": NIFTY_100_SYMBOLS,
    "nifty500": NIFTY_500_SYMBOLS,
    "test": ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]  # For testing
}

# Path to optional dynamic index universe cache
INDEX_UNIVERSE_CACHE_FILE = Path(__file__).parent.parent.parent / "data" / "index_universe" / "index_universes.json"


def get_universe_symbols(universe: str) -> List[str]:
    """Public helper to get symbols for a given universe name.

    Order of precedence:
    1) Dynamic cache (if present and valid)
    2) Static hardcoded UNIVERSES
    3) Fallback to NIFTY_50_SYMBOLS
    """
    universe_lower = (universe or "").lower()

    # 1) Try dynamic cache written by index_universe_monitor
    try:
        if INDEX_UNIVERSE_CACHE_FILE.exists():
            with open(INDEX_UNIVERSE_CACHE_FILE, "r") as f:
                data = json.load(f)
                symbols = data.get(universe_lower)
                if isinstance(symbols, list) and symbols:
                    return [str(s).upper() for s in symbols]
    except Exception as e:
        # Soft-fail: log to stdout but do not break
        print(f"[TopPicksEngine] Failed to read index universe cache: {e}")

    # 2) Static mapping
    if universe_lower in UNIVERSES:
        return UNIVERSES[universe_lower]

    # 3) Fallback
    return NIFTY_50_SYMBOLS



class TopPicksEngine:
    """
    Generates top stock picks using 13-agent analysis with DYNAMIC MODE-SPECIFIC WEIGHTING.
    
    Agent Configuration:
    - 10 Core Scoring Agents: Technical, Global, Policy, Options, Sentiment, Microstructure, Risk, Pattern, Regime, Watchlist
    - 3 Utility Agents: Trade Strategy (supra), Auto-Monitoring, Personalization
    
    Trading Modes (weights loaded from config/mode_weights.json):
    - Scalping: Ultra-short-term (seconds to minutes) - Focus: Microstructure, Quick patterns, Liquidity
    - Intraday: Within-day trades (30 mins to hours) - Focus: Technical patterns, Sentiment, Momentum
    - Swing: Multi-day to long-term (3 days to months) - Focus: Macro trends, Fundamentals, Policy, Multi-day patterns
    
    Note: Positional and Delivery modes are aliases for Swing (same weight profile).
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        """Initialize the Top Picks Engine"""
        # Storage for historical picks
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            self.storage_path = Path(__file__).parent.parent.parent / "data" / "top_picks"
        
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize 13-agent coordinator
        # 10 Core Scoring Agents
        self.coordinator = AgentCoordinator()
        self.coordinator.register_agent(TechnicalAgent(weight=0.20))
        self.coordinator.register_agent(GlobalMarketAgent(weight=0.12))
        self.coordinator.register_agent(PolicyMacroAgent(weight=0.08))
        self.coordinator.register_agent(OptionsAgent(weight=0.12))
        self.coordinator.register_agent(SentimentAgent(weight=0.12))
        self.coordinator.register_agent(MicrostructureAgent(weight=0.08))
        self.coordinator.register_agent(RiskAgent(weight=0.08))
        self.coordinator.register_agent(PatternRecognitionAgent(weight=0.10))
        self.coordinator.register_agent(MarketRegimeAgent(weight=0.05))
        self.coordinator.register_agent(WatchlistIntelligenceAgent(weight=0.05))
        
        # 3 Utility Agents (0 weight - not scored)
        self.coordinator.register_agent(TradeStrategyAgent(weight=0.00))  # Supra agent
        self.coordinator.register_agent(AutoMonitoringAgent(weight=0.00))
        self.coordinator.register_agent(PersonalizationAgent(weight=0.00))
        
        # Default weights (will be overridden by mode-specific weights)
        self.coordinator.set_weights({
            'technical': 0.2233,
            'global': 0.12,
            'policy': 0.08,
            'options': 0.12,
            'sentiment': 0.12,
            'microstructure': 0.0893,
            'risk': 0.08,
            'pattern': 0.1116,
            'regime': 0.0558,
            'watchlist': 0.00,
            'trade_strategy': 0.00,
            'auto_monitoring': 0.00,
            'personalization': 0.00
        })
    
    async def generate_daily_picks(
        self,
        universe: str = "nifty50",
        top_n: int = 5,
        min_confidence: str = "medium",
        max_concurrent: int = 10,
        agent_names: Optional[List[str]] = None,
        mode: str = "Swing"
    ) -> Dict[str, Any]:
        """Generate top N stock picks from a universe."""

        mode = normalize_mode(mode)

        # Consistent IST timestamp for this run (used for metadata and
        # intraday session segmentation). We compute once so all picks in the
        # batch share the same "generated_at" value.
        ist_now = now_ist()

        agent_desc = f"{len(agent_names)} selected agents" if agent_names else "all agents"
        
        # Apply mode-specific agent weights from PolicyStore
        policy_store = get_policy_store()
        mode_policy = policy_store.get_mode_policy(mode)
        if mode_policy.weights:
            self.coordinator.set_weights(mode_policy.weights)
            print(f"\n[MODE] Applied {mode_policy.mode} weight profile:")
            sorted_weights = sorted(mode_policy.weights.items(), key=lambda x: x[1], reverse=True)
            top_agents = [(name, weight) for name, weight in sorted_weights if weight > 0][:3]
            print(f"       Top agents: {', '.join([f'{name}({w:.0%})' for name, w in top_agents])}")
        else:
            print(f"\n[MODE] Using default embedded weights (no policy weights for mode '{mode}')")

        thresholds = mode_policy.thresholds or {}

        # Load active RL policy once. Used for exit-profile overlays for
        # Scalping and, when configured, for other modes as well.
        active_rl_policy = None
        try:
            active_rl_policy = get_active_rl_policy()
        except Exception:
            active_rl_policy = None
        
        print(f"\n{'='*60}")
        print(f"ARISE Top Picks Engine - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")
        print(f"Universe: {universe.upper()}")
        print(f"Mode: {mode}")
        print(f"Analyzing stocks...")
        
        # Get symbols for the requested universe.
        # IMPORTANT: Do NOT cap the universe size here – ARISE's USP is to
        # analyze the full index (e.g. all 50 NIFTY names) and then surface the
        # best opportunities. Any performance optimizations should be handled
        # by scheduling/caching, not by trimming the search space.
        symbols = self._get_universe_symbols(universe)
        print(f"Total stocks to analyze: {len(symbols)}")
        
        # Batch analyze all stocks
        print(f"Running analysis ({agent_desc}, max {max_concurrent} concurrent)...")
        start_time = datetime.now()
        
        results = await self.coordinator.batch_analyze(
            symbols,
            agent_names=agent_names,
            max_concurrent=max_concurrent
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"Analysis complete in {elapsed:.1f} seconds")
        
        # Filter by confidence
        confidence_levels = {'low': 1, 'medium': 2, 'high': 3}
        min_level = confidence_levels.get(min_confidence.lower(), 2)
        
        filtered_results = []
        for result in results:
            confidence = result.get('confidence', 'Low').lower()
            result_level = confidence_levels.get(confidence, 1)
            
            if result_level >= min_level:
                filtered_results.append(result)
        
        print(f"Filtered to {len(filtered_results)} stocks meeting confidence threshold")
        
        # Sort by blend score
        filtered_results.sort(key=lambda x: x.get('blend_score', 0), reverse=True)
        
        # Apply recommendations and build bullish / bearish buckets for
        # directional selection.
        all_picks_with_recs: List[Dict[str, Any]] = []
        for result in filtered_results:
            risk_score = None
            for agent in result.get('agents', []):
                if agent.get('agent') == 'risk':
                    risk_score = agent.get('score')
                    break

            rec_result = get_recommendation(
                score=result.get('blend_score', 0),
                confidence=result.get('confidence', 'Medium'),
                risk_agent_score=risk_score,
                agent_signals=result.get('key_signals', [])
            )

            result['recommendation'] = rec_result.recommendation.value
            result['is_actionable'] = rec_result.is_actionable
            result['recommendation_note'] = rec_result.note
            result['risk_reward_ratio'] = rec_result.risk_reward_ratio
            result['color_scheme'] = rec_result.color_scheme

            all_picks_with_recs.append(result)

        bullish_results: List[Dict[str, Any]] = []
        bearish_results: List[Dict[str, Any]] = []

        def _get_score(val: Any) -> float:
            try:
                v = val.get('score_blend', val.get('blend_score', 0.0))
            except AttributeError:
                try:
                    return float(val or 0.0)
                except Exception:
                    return 0.0
            try:
                return float(v or 0.0)
            except Exception:
                return 0.0

        def _get_rr(val: Any) -> Optional[float]:
            rr_val = val.get('risk_reward_ratio')
            if rr_val is None:
                return None
            try:
                return float(rr_val)
            except Exception:
                return None

        # Per-mode directional thresholds (defaults when not provided by policy)
        mode_key = mode
        bull_min_score = 0.0
        bull_min_rr = 0.0
        bear_max_score = 0.0
        bear_min_rr = 0.0

        # Entry bandit (initially added for Scalping): chooses an
        # entry_action_id that defines directional thresholds and max
        # long/short picks for this run, conditioned on (mode,
        # regime_bucket, vol_bucket, user_risk_bucket).
        entry_action_id: Optional[str] = None
        entry_action_cfg: Optional[Dict[str, Any]] = None
        entry_regime_bias: Dict[str, Any] = {}
        regime_bucket_for_entry = "Range"
        vol_bucket_for_entry = "Unknown"
        user_risk_bucket_for_entry = "Moderate"

        if active_rl_policy and mode_key in (
            "Scalping",
            "Intraday",
            "Swing",
            "Options",
            "Futures",
        ):
            try:
                cfg = active_rl_policy.get("config") or {}
                metrics = active_rl_policy.get("metrics") or {}

                entry_all = cfg.get("entry_bandit") or {}
                entry_mode_cfg = entry_all.get(mode_key) or {}
                if isinstance(entry_mode_cfg, dict):
                    entry_enabled = bool(entry_mode_cfg.get("enabled"))
                    epsilon = float(entry_mode_cfg.get("epsilon", 0.0) or 0.0)
                    if epsilon < 0.0:
                        epsilon = 0.0
                    if epsilon > 1.0:
                        epsilon = 1.0
                    min_trades = int(
                        entry_mode_cfg.get("min_trades_per_action", 0) or 0
                    )
                    actions_cfg = entry_mode_cfg.get("actions") or {}
                    if not isinstance(actions_cfg, dict):
                        actions_cfg = {}
                    regime_bias_all = entry_mode_cfg.get("regime_bias") or {}
                    if not isinstance(regime_bias_all, dict):
                        regime_bias_all = {}

                    # Entry bandit metrics: metrics.entry_bandit.{mode}.contexts
                    entry_metrics_all = (
                        metrics.get("entry_bandit") if isinstance(metrics, dict) else None
                    ) or {}
                    if not isinstance(entry_metrics_all, dict):
                        entry_metrics_all = {}
                    entry_mode_metrics = (
                        entry_metrics_all.get(mode_key)
                        if isinstance(entry_metrics_all, dict)
                        else None
                    ) or {}
                    if not isinstance(entry_mode_metrics, dict):
                        entry_mode_metrics = {}
                    contexts_state = (
                        entry_mode_metrics.get("contexts")
                        if isinstance(entry_mode_metrics, dict)
                        else None
                    ) or {}
                    if not isinstance(contexts_state, dict):
                        contexts_state = {}

                    # Derive a market context from the first analyzed result's
                    # market_regime agent. This should be common across
                    # symbols.
                    rep = filtered_results[0] if filtered_results else None
                    if isinstance(rep, dict):
                        for agent in rep.get("agents", []) or []:
                            if agent.get("agent") == "market_regime":
                                meta = agent.get("metadata") or {}
                                regime_raw = str(meta.get("regime") or "UNKNOWN").upper()
                                vol_level_raw = (
                                    str(meta.get("volatility") or "").upper() or None
                                )
                                if regime_raw in ("BULL", "WEAK_BULL"):
                                    regime_bucket_for_entry = "Bull"
                                elif regime_raw in ("BEAR", "WEAK_BEAR"):
                                    regime_bucket_for_entry = "Bear"
                                else:
                                    regime_bucket_for_entry = "Range"

                                if vol_level_raw == "LOW":
                                    vol_bucket_for_entry = "LowVol"
                                elif vol_level_raw == "MEDIUM":
                                    vol_bucket_for_entry = "MediumVol"
                                elif vol_level_raw == "HIGH":
                                    vol_bucket_for_entry = "HighVol"
                                else:
                                    vol_bucket_for_entry = "Unknown"
                                break

                    ctx_key = (
                        f"{mode_key}|{regime_bucket_for_entry}|"
                        f"{vol_bucket_for_entry}|{user_risk_bucket_for_entry}"
                    )
                    ctx_state = contexts_state.get(ctx_key) or {}
                    actions_state = (
                        ctx_state.get("actions") if isinstance(ctx_state, dict) else None
                    ) or {}

                    if (
                        entry_enabled
                        and isinstance(actions_state, dict)
                        and actions_state
                    ):
                        # Candidate actions: intersection of configured
                        # actions (when provided) and those present in
                        # bandit state.
                        if actions_cfg:
                            candidate_ids = [
                                aid
                                for aid in actions_cfg.keys()
                                if aid in actions_state
                            ]
                        else:
                            candidate_ids = list(actions_state.keys())

                        # Filter by minimum trades when specified.
                        if min_trades > 0 and candidate_ids:
                            eligible: List[str] = []
                            for aid in candidate_ids:
                                a_state = actions_state.get(aid) or {}
                                try:
                                    n_trades = int(a_state.get("n") or 0)
                                except Exception:
                                    n_trades = 0
                                if n_trades >= min_trades:
                                    eligible.append(aid)
                            if eligible:
                                candidate_ids = eligible

                        if candidate_ids:
                            explore = (
                                epsilon > 0.0
                                and len(candidate_ids) > 1
                                and random.random() < epsilon
                            )
                            if explore:
                                entry_action_id = random.choice(candidate_ids)
                            else:
                                def _q(aid: str) -> float:
                                    a_state = actions_state.get(aid) or {}
                                    try:
                                        return float(a_state.get("q") or 0.0)
                                    except Exception:
                                        return 0.0

                                entry_action_id = max(candidate_ids, key=_q)

                    # Fallback: use configured default_action or the first
                    # configured action when bandit state is empty.
                    if entry_action_id is None and actions_cfg:
                        default_action = entry_mode_cfg.get("default_action")
                        if (
                            isinstance(default_action, str)
                            and default_action in actions_cfg
                        ):
                            entry_action_id = default_action
                        else:
                            try:
                                entry_action_id = next(iter(actions_cfg.keys()))
                            except StopIteration:
                                entry_action_id = None

                    if entry_action_id and actions_cfg:
                        cfg_for_action = actions_cfg.get(entry_action_id) or {}
                        if isinstance(cfg_for_action, dict):
                            entry_action_cfg = cfg_for_action

                    if isinstance(regime_bias_all, dict):
                        rb = regime_bias_all.get(regime_bucket_for_entry) or {}
                        if isinstance(rb, dict):
                            entry_regime_bias = rb
            except Exception as e:
                try:
                    print(f"[ScalpingEntryBandit] Failed selection: {e}")
                except Exception:
                    pass

        max_long_picks: Optional[int] = None
        max_short_picks: Optional[int] = None

        if mode_key == "Scalping":
            if entry_action_cfg:
                bull_min_score = float(
                    entry_action_cfg.get("bull_min_score")
                    or thresholds.get("bull_min_score", 55)
                    or 55
                )
                bull_min_rr = float(
                    entry_action_cfg.get("bull_min_rr")
                    or thresholds.get("bull_min_rr", 1.2)
                    or 1.2
                )
                bear_max_score = float(
                    entry_action_cfg.get("bear_max_score")
                    or thresholds.get("bear_max_score", 44)
                    or 44
                )
                bear_min_rr = float(
                    entry_action_cfg.get("bear_min_rr")
                    or thresholds.get("bear_min_rr", 1.2)
                    or 1.2
                )

                try:
                    max_long_picks = int(
                        entry_action_cfg.get("max_long_picks") or top_n
                    )
                except Exception:
                    max_long_picks = top_n
                try:
                    max_short_picks = int(
                        entry_action_cfg.get("max_short_picks") or top_n
                    )
                except Exception:
                    max_short_picks = top_n
            else:
                bull_min_score = float(thresholds.get("bull_min_score", 55) or 55)
                bull_min_rr = float(thresholds.get("bull_min_rr", 1.2) or 1.2)
                bear_max_score = float(thresholds.get("bear_max_score", 44) or 44)
                bear_min_rr = float(thresholds.get("bear_min_rr", 1.2) or 1.2)
                max_long_picks = top_n
                max_short_picks = top_n

            # Apply regime-aware multipliers for long/short caps.
            try:
                long_mult = float(entry_regime_bias.get("long_mult", 1.0) or 1.0)
            except Exception:
                long_mult = 1.0
            try:
                short_mult = float(entry_regime_bias.get("short_mult", 1.0) or 1.0)
            except Exception:
                short_mult = 1.0

            if max_long_picks is not None:
                max_long_picks = max(
                    0, min(top_n, int(round(max_long_picks * long_mult)))
                )
            if max_short_picks is not None:
                max_short_picks = max(
                    0, min(top_n, int(round(max_short_picks * short_mult)))
                )
        elif mode_key == "Intraday":
            if entry_action_cfg:
                bull_min_score = float(
                    entry_action_cfg.get("bull_min_score")
                    or thresholds.get("bull_min_score", 60)
                    or 60
                )
                bull_min_rr = float(
                    entry_action_cfg.get("bull_min_rr")
                    or thresholds.get("bull_min_rr", 1.5)
                    or 1.5
                )
                bear_max_score = float(
                    entry_action_cfg.get("bear_max_score")
                    or thresholds.get("bear_max_score", 44)
                    or 44
                )
                bear_min_rr = float(
                    entry_action_cfg.get("bear_min_rr")
                    or thresholds.get("bear_min_rr", 1.5)
                    or 1.5
                )
            else:
                bull_min_score = float(thresholds.get("bull_min_score", 60) or 60)
                bull_min_rr = float(thresholds.get("bull_min_rr", 1.5) or 1.5)
                bear_max_score = float(thresholds.get("bear_max_score", 44) or 44)
                bear_min_rr = float(thresholds.get("bear_min_rr", 1.5) or 1.5)
        elif mode_key == "Swing":
            if entry_action_cfg:
                bull_min_score = float(
                    entry_action_cfg.get("bull_min_score")
                    or thresholds.get("bull_min_score", 60)
                    or 60
                )
                bull_min_rr = float(
                    entry_action_cfg.get("bull_min_rr")
                    or thresholds.get("bull_min_rr", 1.8)
                    or 1.8
                )
                bear_max_score = float(
                    entry_action_cfg.get("bear_max_score")
                    or thresholds.get("bear_max_score", 45)
                    or 45
                )
                bear_min_rr = float(
                    entry_action_cfg.get("bear_min_rr")
                    or thresholds.get("bear_min_rr", 1.8)
                    or 1.8
                )
            else:
                bull_min_score = float(thresholds.get("bull_min_score", 60) or 60)
                bull_min_rr = float(thresholds.get("bull_min_rr", 1.8) or 1.8)
                bear_max_score = float(thresholds.get("bear_max_score", 45) or 45)
                bear_min_rr = float(thresholds.get("bear_min_rr", 1.8) or 1.8)
        elif mode_key == "Options":
            if entry_action_cfg:
                bull_min_score = float(
                    entry_action_cfg.get("bull_min_score")
                    or thresholds.get("bull_min_score", 65)
                    or 65
                )
                bull_min_rr = float(
                    entry_action_cfg.get("bull_min_rr")
                    or thresholds.get("bull_min_rr", 1.8)
                    or 1.8
                )
                bear_max_score = float(
                    entry_action_cfg.get("bear_max_score")
                    or thresholds.get("bear_max_score", 40)
                    or 40
                )
                bear_min_rr = float(
                    entry_action_cfg.get("bear_min_rr")
                    or thresholds.get("bear_min_rr", 1.8)
                    or 1.8
                )
            else:
                bull_min_score = float(thresholds.get("bull_min_score", 65) or 65)
                bull_min_rr = float(thresholds.get("bull_min_rr", 1.8) or 1.8)
                bear_max_score = float(thresholds.get("bear_max_score", 40) or 40)
                bear_min_rr = float(thresholds.get("bear_min_rr", 1.8) or 1.8)
        elif mode_key == "Futures":
            if entry_action_cfg:
                bull_min_score = float(
                    entry_action_cfg.get("bull_min_score")
                    or thresholds.get("bull_min_score", 60)
                    or 60
                )
                bull_min_rr = float(
                    entry_action_cfg.get("bull_min_rr")
                    or thresholds.get("bull_min_rr", 1.7)
                    or 1.7
                )
                bear_max_score = float(
                    entry_action_cfg.get("bear_max_score")
                    or thresholds.get("bear_max_score", 44)
                    or 44
                )
                bear_min_rr = float(
                    entry_action_cfg.get("bear_min_rr")
                    or thresholds.get("bear_min_rr", 1.7)
                    or 1.7
                )
            else:
                bull_min_score = float(thresholds.get("bull_min_score", 60) or 60)
                bull_min_rr = float(thresholds.get("bull_min_rr", 1.7) or 1.7)
                bear_max_score = float(thresholds.get("bear_max_score", 44) or 44)
                bear_min_rr = float(thresholds.get("bear_min_rr", 1.7) or 1.7)
        else:
            bull_min_score = float(thresholds.get("min_blend_score", 0) or 0)
            bull_min_rr = float(thresholds.get("min_risk_reward", 0) or 0)

        long_count = 0
        short_count = 0

        for r in all_picks_with_recs:
            if not r.get('is_actionable', True):
                continue

            score_f = _get_score(r)
            rr_f = _get_rr(r)
            rec_text = str(r.get('recommendation') or "")

            if rec_text in ("Strong Buy", "Buy"):
                if bull_min_score > 0 and score_f < bull_min_score:
                    continue
                if bull_min_rr > 0 and (rr_f is None or rr_f < bull_min_rr):
                    continue
                if (
                    mode_key == "Scalping"
                    and max_long_picks is not None
                    and long_count >= max_long_picks
                ):
                    continue
                bullish_results.append(r)
                if mode_key == "Scalping" and max_long_picks is not None:
                    long_count += 1
            elif rec_text in ("Sell", "Strong Sell"):
                if bear_max_score > 0 and score_f > bear_max_score:
                    continue
                if bear_min_rr > 0 and (rr_f is None or rr_f < bear_min_rr):
                    continue
                bearish_results.append(r)
                if mode_key == "Scalping" and max_short_picks is not None:
                    short_count += 1

        # Optional relaxed bear threshold when too few shorts are available
        if mode_key in ("Scalping", "Intraday", "Futures") and not bearish_results:
            relaxed_max = bear_max_score if bear_max_score > 0 else 48.0
            relaxed_max = max(relaxed_max, 48.0)
            for r in all_picks_with_recs:
                if not r.get('is_actionable', True):
                    continue
                rec_text = str(r.get('recommendation') or "")
                if rec_text not in ("Sell", "Strong Sell"):
                    continue
                score_f = _get_score(r)
                rr_f = _get_rr(r)
                if score_f <= relaxed_max and (
                    bear_min_rr <= 0 or (rr_f is not None and rr_f >= bear_min_rr)
                ):
                    if (
                        mode_key == "Scalping"
                        and max_short_picks is not None
                        and short_count >= max_short_picks
                    ):
                        continue
                    bearish_results.append(r)
                    if mode_key == "Scalping" and max_short_picks is not None:
                        short_count += 1

        if mode_key in ("Scalping", "Intraday", "Futures"):
            try:
                bullish_results, bearish_results = await self._apply_index_relative_filters(
                    mode_key,
                    bullish_results,
                    bearish_results,
                )
            except Exception as e:
                print(f"[TopPicksEngine] Index/relative-strength filter failed: {e}")

        bullish_results.sort(key=lambda x: _get_score(x), reverse=True)
        bearish_results.sort(key=lambda x: _get_score(x))

        actionable_results = bullish_results + bearish_results

        # Robust fallback: if no picks survive the directional thresholds for a
        # given mode (e.g. overly strict score/RR cutoffs), fall back to the
        # broader definition of "actionable" from the recommendation system.
        # This guarantees that the engine still surfaces some ideas instead of
        # returning an empty list and forcing the UI into deterministic
        # placeholders.
        if not actionable_results:
            try:
                fallback_actionable, ac_count, total_count = filter_actionable_picks(
                    all_picks_with_recs
                )
                if ac_count > 0:
                    print(
                        f"[TopPicksEngine] No picks passed directional thresholds in {mode_key}; "
                        f"falling back to {ac_count}/{total_count} actionable picks by recommendation."
                    )
                    fallback_actionable.sort(key=lambda x: _get_score(x), reverse=True)
                    actionable_results = fallback_actionable
            except Exception as e:
                print(f"[TopPicksEngine] Fallback actionable filter failed: {e}")

        print(
            f"Filtered to {len(actionable_results)} actionable picks "
            f"(excluded {len(all_picks_with_recs) - len(actionable_results)} by rec/thresholds)"
        )

        # For Intraday mode, gently tilt ordering using multi-timeframe
        # support/resistance context so that entries near favorable
        # supports (and away from heavy resistance) are preferred.
        if mode == "Intraday" and actionable_results:
            try:
                actionable_results = await self._apply_sr_scoring(universe, actionable_results)
            except Exception as e:
                print(f"[TopPicksEngine] S/R scoring failed for Intraday: {e}")

        # Generate picks from actionable results
        picks = []
        for rank, result in enumerate(actionable_results[:top_n], 1):
            pick = self._format_pick(rank, result)

            # Attach a normalized exit_strategy for non-Scalping modes so that
            # downstream analytics and monitoring can reason about consistent
            # entry/stop/target levels. Scalping has its own specialized
            # strategy handled in the block below.
            if mode != "Scalping":
                self._attach_exit_strategy_from_plan_or_mode(pick, result, mode)

            picks.append(pick)

        # Enrich final picks with real-time price data (used for Heat Map,
        # Scalping exits, and price summaries). This only hits quotes for the
        # top N picks, not the entire universe, so overhead is small compared
        # to the agent analysis above.
        try:
            picks = await enrich_picks_with_realtime_data(picks)
        except Exception as e:
            print(f"[TopPicksEngine] Failed to enrich picks with realtime data: {e}")

        # Generate intelligent insights using OpenAI
        print(f"Generating AI-powered insights for {len(picks)} picks...")
        try:
            picks = await generate_batch_insights(picks, trading_mode=mode)
            print(f"✓ AI insights generated successfully")
        except Exception as e:
            print(f"⚠️  Failed to generate AI insights: {e}")
            # Continue without AI insights - picks will have fallback text
        
        # For Scalping mode: Add entry_price and exit_strategy
        if mode == "Scalping":
            from ..agents.scalping_agent import ScalpingAgent
            scalping_agent = ScalpingAgent()

            for pick in picks:
                # Attach entry_action_id selected by the entry bandit (if any)
                if entry_action_id:
                    pick["entry_action_id"] = entry_action_id

                # Set entry_price from real-time last_price when available,
                # falling back to technical price. This ensures Scalping
                # Monitor can always find a valid entry for active positions.
                entry_price = pick.get("last_price") or pick.get("price") or 0
                if entry_price and entry_price > 0:
                    pick["entry_price"] = entry_price

                    context = None
                    try:
                        chart = await chart_data_service.fetch_chart_data(pick["symbol"], "1M")
                        if (
                            isinstance(chart, dict)
                            and isinstance(chart.get("candles"), list)
                            and chart["candles"]
                        ):
                            context = {"candles": chart["candles"]}
                    except Exception as e:
                        print(f"[ScalpingStrategy] Chart data failed for {pick['symbol']}: {e}")

                    exit_strategy = None
                    try:
                        exit_strategy = scalping_agent.generate_exit_strategy(
                            symbol=pick["symbol"],
                            entry_price=entry_price,
                            context=context,
                        )
                    except Exception as e:
                        print(f"[ScalpingStrategy] Failed for {pick['symbol']}: {e}")

                    if not exit_strategy:
                        default_target_pct = 0.5
                        default_stop_pct = 0.4
                        target_price = entry_price * (1 + default_target_pct / 100)
                        stop_loss_price = entry_price * (1 - default_stop_pct / 100)
                        exit_strategy = {
                            "target_price": round(target_price, 2),
                            "target_pct": default_target_pct,
                            "stop_loss_price": round(stop_loss_price, 2),
                            "stop_pct": default_stop_pct,
                            "max_hold_mins": 60,
                            "trailing_stop": {
                                "enabled": True,
                                "activation_pct": 0.2,
                                "trail_distance_pct": 0.3,
                            },
                            "atr": round(entry_price * 0.003, 2),
                            "atr_pct": 0.3,
                            "scalp_type": "standard",
                            "conditions": [
                                f"Exit at +{default_target_pct}% (target)",
                                f"Exit at -{default_stop_pct}% (stop loss)",
                                "Trail stop by 0.3% after +0.2% profit",
                                "Exit after 60 minutes max",
                            ],
                            "description": f"Default scalp strategy: Target={default_target_pct}%, Stop={default_stop_pct}%",
                        }

                    pick["exit_strategy"] = exit_strategy

                    # Apply RL meta-policy overlay (exit profile tuning) when available.
                    if active_rl_policy:
                        try:
                            self._apply_rl_scalping_exit_profile(pick, active_rl_policy)
                        except Exception as e:
                            print(f"[ScalpingStrategy][RL] Failed to apply RL exit profile for {pick['symbol']}: {e}")

                    if isinstance(pick.get("exit_strategy"), dict):
                        try:
                            desc = pick["exit_strategy"].get("description") or ""
                            print(f"[ScalpingStrategy] {pick['symbol']}: {desc}")
                        except Exception:
                            pass

        # For Intraday mode: propagate entry_action_id chosen by the
        # entry bandit so that it is available for logging/analytics.
        if mode == "Intraday" and entry_action_id:
            for pick in picks:
                pick["entry_action_id"] = entry_action_id

        # For Swing/Options/Futures, also propagate entry_action_id when
        # an entry bandit action was selected so that offline trainers can
        # attribute outcomes correctly.
        if mode in ("Swing", "Options", "Futures") and entry_action_id:
            for pick in picks:
                pick["entry_action_id"] = entry_action_id

        session_segment = None
        if mode == "Intraday":
            try:
                total_minutes = ist_now.hour * 60 + ist_now.minute
                if total_minutes < 570:
                    session_segment = "OpeningRange"
                elif total_minutes < 660:
                    session_segment = "MorningMomentum"
                elif total_minutes < 720:
                    session_segment = "PostMorning"
                elif total_minutes < 810:
                    session_segment = "MiddayZone"
                elif total_minutes < 870:
                    session_segment = "PostLunch"
                else:
                    session_segment = "PowerHour"
            except Exception:
                session_segment = "OpeningRange"

            if session_segment:
                for pick in picks:
                    pick["session_segment"] = session_segment

        # Compute position-within-day value bucket (Open/Mid/High/Close)
        # using today's low/high and the current or last price. This is
        # logged for analytics and used by contextual bandits (e.g.
        # Intraday exits) to understand where entries/exits were taken
        # relative to the day's range.
        for pick in picks:
            try:
                low_val = pick.get("low")
                high_val = pick.get("high")
                price_val = pick.get("last_price") or pick.get("price")

                if low_val is None or high_val is None or price_val is None:
                    continue

                low_f = float(low_val)
                high_f = float(high_val)
                price_f = float(price_val)
            except Exception:
                continue

            if high_f <= low_f:
                continue

            try:
                pos = (price_f - low_f) / (high_f - low_f)
            except Exception:
                continue

            if pos < 0.0:
                pos = 0.0
            elif pos > 1.0:
                pos = 1.0

            if pos < 0.25:
                value_bucket = "Open"
            elif pos < 0.5:
                value_bucket = "Mid"
            elif pos < 0.75:
                value_bucket = "High"
            else:
                value_bucket = "Close"

            pick["value_bucket"] = value_bucket

        # Apply RL meta-policy exit overlay for non-Scalping modes after
        # realtime enrichment and intraday context tagging so that
        # Intraday exits can use session_segment/value_bucket in their
        # bandit context.
        if active_rl_policy and mode != "Scalping":
            for pick in picks:
                try:
                    self._apply_rl_exit_profile_for_mode(pick, active_rl_policy, mode)
                except Exception as e:
                    print(
                        f"[TopPicksEngine][RL] Failed to apply RL exit profile for "
                        f"{pick.get('symbol')} ({mode}): {e}"
                    )

        picks_data = {
            'date': ist_now.strftime('%Y-%m-%d'),
            'generated_at': ist_now.isoformat(),
            'universe': universe,
            'mode': mode,  # Trading mode (Scalping, Intraday, Swing, etc.)
            'total_analyzed': len(symbols),
            'passed_filter': len(filtered_results),
            'picks_count': len(picks),
            'picks': picks,
            'next_refresh': self._get_next_refresh_time(),
            'metadata': {
                'analysis_time_seconds': elapsed,
                'min_confidence': min_confidence,
                'agent_weights': self.coordinator.weights,
                'version': '1.0',  # Engine version
                'policy_version': policy_store.get_policy_version(),
            }
        }
        try:
            log_event(
                event_type="top_picks_generated",
                source="top_picks_engine",
                payload={
                    "universe": universe,
                    "mode": mode,
                    "min_confidence": min_confidence,
                    "analysis_time_seconds": elapsed,
                    "total_analyzed": len(symbols),
                    "passed_filter": len(filtered_results),
                    "picks": [
                        {
                            "rank": p.get("rank"),
                            "symbol": p.get("symbol"),
                            "score_blend": p.get("score_blend"),
                            "recommendation": p.get("recommendation"),
                            "risk_reward_ratio": p.get("risk_reward_ratio"),
                            "entry_price": p.get("price"),
                            "target": p.get("target"),
                            "horizon": p.get("horizon"),
                        }
                        for p in picks
                    ],
                    "agent_weights": self.coordinator.weights,
                },
            )
        except Exception:
            pass
        
        # Sanitize for JSON (convert numpy/pandas scalars to native types)
        safe_picks_data = self._sanitize_for_json(picks_data)

        # Store to disk
        self._store_picks(safe_picks_data)
        
        # Print summary
        self._print_summary(safe_picks_data)
        
        return safe_picks_data
    
    def _get_universe_symbols(self, universe: str) -> List[str]:
        """Get symbols for specified universe"""
        return get_universe_symbols(universe)
    
    def _attach_exit_strategy_from_plan_or_mode(
        self,
        pick: Dict[str, Any],
        result: Dict[str, Any],
        mode: str,
    ) -> None:
        """Attach a normalized exit_strategy dict to a pick if possible.

        Priority:
        1) Use TradeStrategyAgent trade_plan when available (Swing and any
           mode where the agent ran).
        2) Fallback to mode-specific strategy templates (e.g. Intraday) from
           trading_modes.get_strategy_parameters.
        """

        try:
            mode_norm = normalize_mode(mode)

            # First try to build from TradeStrategyAgent trade_plan
            agents = result.get("agents", []) or []
            strategy_agent = next(
                (a for a in agents if a.get("agent") == "trade_strategy"),
                None,
            )
            trade_plan = None
            if strategy_agent:
                metadata = strategy_agent.get("metadata") or {}
                trade_plan = metadata.get("trade_plan") or None

            exit_strategy = None
            if trade_plan:
                exit_strategy = self._build_exit_strategy_from_trade_plan(
                    trade_plan, mode_norm
                )

            # If no trade_plan or it could not be normalized, fall back to a
            # light-weight template based on mode + blend score.
            if exit_strategy is None:
                exit_strategy = self._build_exit_strategy_from_mode_template(
                    result, pick, mode_norm
                )

            if exit_strategy:
                if mode == "Intraday":
                    self._attach_s1_strategy_profile(exit_strategy)
                elif mode == "Swing":
                    self._attach_s3_strategy_profile(exit_strategy)
                pick["exit_strategy"] = exit_strategy
        except Exception as e:
            # Soft-fail: exit strategy is auxiliary, never break Top Picks.
            print(
                f"[TopPicksEngine] Failed to attach exit_strategy for "
                f"{pick.get('symbol')}: {e}"
            )

    def _apply_rl_exit_profile_for_mode(
        self,
        pick: Dict[str, Any],
        rl_policy: Optional[Dict[str, Any]],
        mode: str,
    ) -> None:
        """Overlay RL exit profile for a given mode onto an existing exit_strategy.

        This is the non-Scalping counterpart to _apply_rl_scalping_exit_profile.
        It reads config.modes[mode].exits.profiles and best_exit_profiles[mode]
        from the active RL policy, then gently adjusts the numeric exit
        parameters (stop/target/trailing/time-based) for the pick. It never
        removes the base exit_strategy; it only tweaks fields when a matching
        profile is found.
        """

        if not rl_policy:
            return

        cfg = rl_policy.get("config") or {}
        if not isinstance(cfg, dict):
            return

        modes_cfg = cfg.get("modes") or {}
        if not isinstance(modes_cfg, dict):
            return

        mode_key = str(mode)
        mode_cfg = modes_cfg.get(mode_key) or modes_cfg.get(mode_key.lower()) or {}
        if not isinstance(mode_cfg, dict):
            return

        exits_cfg = mode_cfg.get("exits") or {}
        if not isinstance(exits_cfg, dict):
            return

        profiles = exits_cfg.get("profiles") or {}
        if not isinstance(profiles, dict) or not profiles:
            return

        metrics = rl_policy.get("metrics") or {}

        # Offline evaluation metrics per exit profile for this mode.
        exit_profiles_metrics = (
            (metrics.get("exit_profiles") or {}).get(mode_key)
            if isinstance(metrics, dict)
            else None
        ) or {}

        best_profiles = (
            metrics.get("best_exit_profiles") if isinstance(metrics, dict) else None
        ) or {}
        best_mode = (
            best_profiles.get(mode_key) if isinstance(best_profiles, dict) else None
        ) or {}
        best_id = best_mode.get("id") if isinstance(best_mode, dict) else None

        profile_id: Optional[str] = None

        # --- Contextual exit bandit selection (primary, per-mode) ---
        bandit_enabled = False
        epsilon = 0.0
        min_trades = 0
        actions_cfg: Optional[List[str]] = None
        contexts_state: Dict[str, Any] = {}

        if isinstance(cfg.get("bandit"), dict):
            bandit_cfg_all = cfg.get("bandit") or {}
            mode_bandit_cfg = bandit_cfg_all.get(mode_key) or {}
            if isinstance(mode_bandit_cfg, dict):
                bandit_enabled = bool(mode_bandit_cfg.get("enabled"))
                try:
                    epsilon = float(mode_bandit_cfg.get("epsilon", 0.0) or 0.0)
                except Exception:
                    epsilon = 0.0
                if epsilon < 0.0:
                    epsilon = 0.0
                if epsilon > 1.0:
                    epsilon = 1.0
                try:
                    min_trades = int(
                        mode_bandit_cfg.get("min_trades_per_action", 0) or 0
                    )
                except Exception:
                    min_trades = 0

                # Optional allow-list of profile IDs to consider.
                raw_actions_cfg = mode_bandit_cfg.get("actions") or None
                if isinstance(raw_actions_cfg, list) and raw_actions_cfg:
                    actions_cfg = [str(a) for a in raw_actions_cfg]

                # Contextual bandit state: metrics.bandit[mode].contexts
                bandit_state_all = (
                    metrics.get("bandit") if isinstance(metrics, dict) else None
                ) or {}
                mode_bandit_state = (
                    bandit_state_all.get(mode_key)
                    if isinstance(bandit_state_all, dict)
                    else None
                ) or {}
                contexts_state = (
                    mode_bandit_state.get("contexts")
                    if isinstance(mode_bandit_state, dict)
                    else None
                ) or {}
                if not isinstance(contexts_state, dict):
                    contexts_state = {}

        if bandit_enabled and isinstance(contexts_state, dict):
            try:
                # Build bandit context key consistent with trainer and
                # pick_logger.
                regime_bucket = str(pick.get("regime_bucket") or "Unknown")
                vol_bucket = str(pick.get("vol_bucket") or "Unknown")
                user_risk_bucket = str(pick.get("user_risk_bucket") or "Moderate")

                if mode_key == "Intraday":
                    # "Intraday|regime|vol|risk|session|value"
                    session_segment = str(pick.get("session_segment") or "Unknown")
                    value_bucket = str(pick.get("value_bucket") or "Unknown")
                    ctx_key = (
                        f"Intraday|{regime_bucket}|{vol_bucket}|{user_risk_bucket}|"
                        f"{session_segment}|{value_bucket}"
                    )
                else:
                    # Generic form used by Swing/Options/Futures trainers:
                    # "{mode}|regime|vol|risk".
                    ctx_key = (
                        f"{mode_key}|{regime_bucket}|{vol_bucket}|{user_risk_bucket}"
                    )

                ctx_state = contexts_state.get(ctx_key) or {}
                actions_state = (
                    ctx_state.get("actions") if isinstance(ctx_state, dict) else None
                ) or {}

                if isinstance(actions_state, dict) and actions_state:
                    # Candidate actions: intersection of configured actions
                    # (when provided) and those present in bandit state.
                    if isinstance(actions_cfg, list) and actions_cfg:
                        candidate_ids = [
                            pid
                            for pid in actions_cfg
                            if pid in actions_state and pid in profiles
                        ]
                    else:
                        candidate_ids = [
                            pid for pid in actions_state.keys() if pid in profiles
                        ]

                    # Filter by minimum trades N when specified.
                    if min_trades > 0 and candidate_ids:
                        eligible: List[str] = []
                        for pid in candidate_ids:
                            a_state = actions_state.get(pid) or {}
                            try:
                                n_trades = int(a_state.get("n") or 0)
                            except Exception:
                                n_trades = 0
                            if n_trades >= min_trades:
                                eligible.append(pid)
                        if eligible:
                            candidate_ids = eligible

                    if candidate_ids:
                        explore = (
                            epsilon > 0.0
                            and len(candidate_ids) > 1
                            and random.random() < epsilon
                        )
                        if explore:
                            profile_id = random.choice(candidate_ids)
                        else:
                            def _q(pid: str) -> float:
                                a_state = actions_state.get(pid) or {}
                                try:
                                    return float(a_state.get("q") or 0.0)
                                except Exception:
                                    return 0.0

                            profile_id = max(candidate_ids, key=_q)
            except Exception as e:
                try:
                    print(
                        f"[TopPicksEngine][RL][Bandit][{mode_key}][Ctx] Failed selection: {e}"
                    )
                except Exception:
                    pass

        # --- Secondary: fall back to offline profile scores when bandit is thin ---
        if profile_id is None and bandit_enabled and exit_profiles_metrics:
            try:
                if isinstance(actions_cfg, list) and actions_cfg:
                    candidate_ids = [
                        pid
                        for pid in actions_cfg
                        if pid in profiles and pid in exit_profiles_metrics
                    ]
                else:
                    candidate_ids = [
                        pid
                        for pid in profiles.keys()
                        if pid in exit_profiles_metrics
                    ]

                if min_trades > 0 and candidate_ids:
                    eligible: List[str] = []
                    for pid in candidate_ids:
                        m = exit_profiles_metrics.get(pid) or {}
                        try:
                            n_trades = int(m.get("trades") or 0)
                        except Exception:
                            n_trades = 0
                        if n_trades >= min_trades:
                            eligible.append(pid)
                    if eligible:
                        candidate_ids = eligible

                if candidate_ids:
                    explore = epsilon > 0.0 and len(candidate_ids) > 1 and random.random() < epsilon
                    if explore:
                        profile_id = random.choice(candidate_ids)
                    else:
                        def _score(pid: str) -> float:
                            m = exit_profiles_metrics.get(pid) or {}
                            try:
                                return float(m.get("score") or 0.0)
                            except Exception:
                                return 0.0

                        profile_id = max(candidate_ids, key=_score)
            except Exception as e:
                try:
                    print(f"[TopPicksEngine][RL][Bandit][Intraday][Global] Failed selection: {e}")
                except Exception:
                    pass

        # --- Fallback for all modes: best_exit_profiles then default_profile ---
        if profile_id is None:
            if isinstance(best_id, str) and best_id in profiles:
                profile_id = best_id
            else:
                default_id = exits_cfg.get("default_profile")
                if isinstance(default_id, str) and default_id in profiles:
                    profile_id = default_id

        if not profile_id:
            return

        profile_cfg = profiles.get(profile_id) or {}
        if not isinstance(profile_cfg, dict):
            return

        exit_strategy = pick.get("exit_strategy") or {}
        if not isinstance(exit_strategy, dict):
            exit_strategy = {}

        symbol = pick.get("symbol") or "?"

        try:
            entry_price = float(
                pick.get("entry_price")
                or pick.get("last_price")
                or pick.get("price")
                or 0.0
            )
        except Exception:
            entry_price = 0.0

        if entry_price <= 0:
            return

        rec = str(pick.get("recommendation") or "").lower()
        direction = "SHORT" if "sell" in rec else "LONG"

        # --- Stop configuration ---
        stop_cfg = profile_cfg.get("stop") or {}
        stop_type = str(stop_cfg.get("type") or "percent")
        try:
            stop_val = float(stop_cfg.get("value") or 0.0)
        except Exception:
            stop_val = 0.0

        stop_price: Optional[float] = None
        stop_pct: Optional[float] = None
        if stop_type == "price" and stop_val > 0:
            stop_price = stop_val
        elif stop_type in ("percent", "atr_multiple") and stop_val > 0:
            stop_pct = stop_val
            dist = entry_price * (stop_val / 100.0)
            if direction == "LONG":
                stop_price = entry_price - dist
            else:
                stop_price = entry_price + dist

        # --- Target configuration ---
        target_cfg = profile_cfg.get("target") or {}
        target_type = str(target_cfg.get("type") or "percent")
        target_val_raw = target_cfg.get("value")
        target_price: Optional[float] = None
        target_pct: Optional[float] = None
        if target_val_raw is not None:
            try:
                target_val = float(target_val_raw)
            except Exception:
                target_val = 0.0
            if target_val > 0:
                if target_type == "price":
                    target_price = target_val
                elif target_type == "percent":
                    target_pct = target_val
                    dist = entry_price * (target_val / 100.0)
                    if direction == "LONG":
                        target_price = entry_price + dist
                    else:
                        target_price = entry_price - dist
                elif target_type == "rr_multiple" and stop_price is not None:
                    stop_dist = abs(entry_price - stop_price)
                    dist = stop_dist * target_val
                    if direction == "LONG":
                        target_price = entry_price + dist
                    else:
                        target_price = entry_price - dist

        # --- Trailing stop configuration ---
        trailing_cfg = profile_cfg.get("trailing") or {}
        trailing_enabled = bool(trailing_cfg.get("enabled"))
        activation_type = str(trailing_cfg.get("activation_type") or "percent")
        trail_type = str(trailing_cfg.get("trail_type") or "percent")
        try:
            activation_val = float(trailing_cfg.get("activation_value") or 0.0)
        except Exception:
            activation_val = 0.0
        try:
            trail_val = float(trailing_cfg.get("trail_value") or 0.0)
        except Exception:
            trail_val = 0.0

        trailing_stop: Dict[str, Any] = exit_strategy.get("trailing_stop") or {}
        if not isinstance(trailing_stop, dict):
            trailing_stop = {}

        if trailing_enabled and activation_type == "percent" and trail_type == "percent":
            trailing_stop.update(
                {
                    "enabled": True,
                    "activation_pct": activation_val,
                    "trail_distance_pct": trail_val,
                }
            )
        elif trailing_enabled:
            trailing_stop.setdefault("enabled", True)

        # --- Time stop configuration ---
        time_stop_cfg = profile_cfg.get("time_stop") or {}
        time_enabled = bool(time_stop_cfg.get("enabled"))
        max_hold_minutes = time_stop_cfg.get("max_hold_minutes")
        try:
            max_hold_mins_f = (
                float(max_hold_minutes) if max_hold_minutes is not None else None
            )
        except Exception:
            max_hold_mins_f = None

        # --- Apply overlay to exit_strategy ---
        if stop_price is not None:
            exit_strategy["stop_loss_price"] = round(stop_price, 2)
        if stop_pct is not None:
            exit_strategy["stop_pct"] = round(stop_pct, 2)
        if target_price is not None:
            exit_strategy["target_price"] = round(target_price, 2)
        if target_pct is not None:
            exit_strategy["target_pct"] = round(target_pct, 2)
        if trailing_stop:
            exit_strategy["trailing_stop"] = trailing_stop
        if time_enabled and max_hold_mins_f is not None:
            exit_strategy["max_hold_mins"] = max_hold_mins_f

        # Attach / enrich strategy_profile so RL profile is traceable via
        # exit_profile_id in pick_events.extra_context.
        strategy_profile = exit_strategy.get("strategy_profile") or {}
        if not isinstance(strategy_profile, dict):
            strategy_profile = {}
        strategy_profile.setdefault("id", profile_id)
        strategy_profile.setdefault("name", profile_cfg.get("name") or profile_id)
        strategy_profile.setdefault("mode", mode_key)
        strategy_profile.setdefault("direction", direction)
        strategy_profile.setdefault("symbol", symbol)
        exit_strategy["strategy_profile"] = strategy_profile

        exit_strategy.setdefault("direction", direction)
        exit_strategy.setdefault("mode", mode_key)
        exit_strategy.setdefault("entry_price", round(entry_price, 2))

        pick["exit_strategy"] = exit_strategy

    def _apply_rl_scalping_exit_profile(
        self,
        pick: Dict[str, Any],
        rl_policy: Optional[Dict[str, Any]],
    ) -> None:
        """Overlay RL meta-policy scalping exit profile onto an existing exit_strategy.

        This reads the active RL policy config (modes.Scalping.exits.profiles) and
        adjusts stop/target/trailing/time-based parameters for Scalping picks. It
        never removes the exit_strategy; it only tweaks fields when a matching
        profile is found.
        """

        if not rl_policy:
            return

        cfg = rl_policy.get("config") or {}
        if not isinstance(cfg, dict):
            return

        modes_cfg = cfg.get("modes") or {}
        if not isinstance(modes_cfg, dict):
            return

        scalping_cfg = modes_cfg.get("Scalping") or modes_cfg.get("scalping") or {}
        if not isinstance(scalping_cfg, dict):
            return

        exits_cfg = scalping_cfg.get("exits") or {}
        if not isinstance(exits_cfg, dict):
            return

        profiles = exits_cfg.get("profiles") or {}
        if not isinstance(profiles, dict) or not profiles:
            return

        metrics = rl_policy.get("metrics") or {}

        # Bandit configuration for Scalping (optional). If disabled or
        # misconfigured, we fall back to best_exit_profiles / default_profile.
        bandit_cfg_all = cfg.get("bandit") or {}
        bandit_scalp_cfg = bandit_cfg_all.get("Scalping") or {}
        bandit_enabled = bool(bandit_scalp_cfg.get("enabled"))
        epsilon = float(bandit_scalp_cfg.get("epsilon", 0.0) or 0.0)
        if epsilon < 0.0:
            epsilon = 0.0
        if epsilon > 1.0:
            epsilon = 1.0
        min_trades = int(bandit_scalp_cfg.get("min_trades_per_action", 0) or 0)
        actions_cfg = bandit_scalp_cfg.get("actions") or None

        exit_profiles_metrics = (
            (metrics.get("exit_profiles") or {}).get("Scalping")
            if isinstance(metrics, dict)
            else None
        ) or {}

        best_profiles = (
            metrics.get("best_exit_profiles") if isinstance(metrics, dict) else None
        ) or {}
        best_scalping = (
            best_profiles.get("Scalping") if isinstance(best_profiles, dict) else None
        ) or {}
        best_id = best_scalping.get("id") if isinstance(best_scalping, dict) else None

        # Contextual bandit state: metrics.bandit.Scalping.contexts
        bandit_state_all = (
            metrics.get("bandit") if isinstance(metrics, dict) else None
        ) or {}
        scalp_bandit_state = (
            bandit_state_all.get("Scalping") if isinstance(bandit_state_all, dict) else None
        ) or {}
        contexts_state = (
            scalp_bandit_state.get("contexts") if isinstance(scalp_bandit_state, dict) else None
        ) or {}

        profile_id: Optional[str] = None

        # --- Primary: epsilon-greedy over contextual Q-values (bandit state) ---
        if bandit_enabled and isinstance(contexts_state, dict) and contexts_state:
            try:
                # Build bandit context key the same way we log it in
                # TopPicksScheduler: "Scalping|regime|vol|risk".
                regime_bucket = str(pick.get("regime_bucket") or "Unknown")
                vol_bucket = str(pick.get("vol_bucket") or "Unknown")
                user_risk_bucket = str(pick.get("user_risk_bucket") or "Moderate")
                ctx_key = f"Scalping|{regime_bucket}|{vol_bucket}|{user_risk_bucket}"

                ctx_state = contexts_state.get(ctx_key) or {}
                actions_state = (
                    ctx_state.get("actions") if isinstance(ctx_state, dict) else None
                ) or {}

                if isinstance(actions_state, dict) and actions_state:
                    # Candidate actions: intersection of configured actions
                    # (when provided) and actions present in bandit state.
                    if isinstance(actions_cfg, list) and actions_cfg:
                        candidate_ids = [
                            str(a)
                            for a in actions_cfg
                            if str(a) in actions_state and str(a) in profiles
                        ]
                    else:
                        candidate_ids = [
                            pid for pid in actions_state.keys() if pid in profiles
                        ]

                    # Filter by minimum trades N when specified.
                    if min_trades > 0 and candidate_ids:
                        eligible: List[str] = []
                        for pid in candidate_ids:
                            a_state = actions_state.get(pid) or {}
                            try:
                                n_trades = int(a_state.get("n") or 0)
                            except Exception:
                                n_trades = 0
                            if n_trades >= min_trades:
                                eligible.append(pid)
                        if eligible:
                            candidate_ids = eligible

                    if candidate_ids:
                        # Exploration vs exploitation using learned Q-values.
                        explore = epsilon > 0.0 and random.random() < epsilon
                        if explore and len(candidate_ids) > 1:
                            profile_id = random.choice(candidate_ids)
                        else:
                            def _q(pid: str) -> float:
                                a_state = actions_state.get(pid) or {}
                                try:
                                    return float(a_state.get("q") or 0.0)
                                except Exception:
                                    return 0.0

                            profile_id = max(candidate_ids, key=_q)
            except Exception as e:
                try:
                    print(f"[ScalpingStrategy][Bandit][Ctx] Failed selection: {e}")
                except Exception:
                    pass

        # --- Secondary: fall back to offline profile scores (non-contextual) ---
        if profile_id is None and bandit_enabled and exit_profiles_metrics:
            try:
                if isinstance(actions_cfg, list) and actions_cfg:
                    candidate_ids = [
                        str(a)
                        for a in actions_cfg
                        if str(a) in profiles and str(a) in exit_profiles_metrics
                    ]
                else:
                    candidate_ids = [
                        pid
                        for pid in profiles.keys()
                        if pid in exit_profiles_metrics
                    ]

                if min_trades > 0 and candidate_ids:
                    eligible: List[str] = []
                    for pid in candidate_ids:
                        m = exit_profiles_metrics.get(pid) or {}
                        try:
                            n_trades = int(m.get("trades") or 0)
                        except Exception:
                            n_trades = 0
                        if n_trades >= min_trades:
                            eligible.append(pid)
                    if eligible:
                        candidate_ids = eligible

                if candidate_ids:
                    explore = epsilon > 0.0 and random.random() < epsilon
                    if explore and len(candidate_ids) > 1:
                        profile_id = random.choice(candidate_ids)
                    else:
                        def _score(pid: str) -> float:
                            m = exit_profiles_metrics.get(pid) or {}
                            try:
                                return float(m.get("score") or 0.0)
                            except Exception:
                                return 0.0

                        profile_id = max(candidate_ids, key=_score)
            except Exception as e:
                try:
                    print(f"[ScalpingStrategy][Bandit][Global] Failed selection: {e}")
                except Exception:
                    pass

        # If bandit did not select a profile (disabled, no metrics, or other
        # failure), fall back to best_exit_profiles.Scalping then default.
        if profile_id is None:
            if isinstance(best_id, str) and best_id in profiles:
                profile_id = best_id
            else:
                default_id = exits_cfg.get("default_profile")
                if isinstance(default_id, str) and default_id in profiles:
                    profile_id = default_id

        if not profile_id:
            return

        profile_cfg = profiles.get(profile_id) or {}
        if not isinstance(profile_cfg, dict):
            return

        exit_strategy = pick.get("exit_strategy") or {}
        if not isinstance(exit_strategy, dict):
            exit_strategy = {}

        symbol = pick.get("symbol") or "?"

        try:
            entry_price = float(
                pick.get("entry_price")
                or pick.get("last_price")
                or pick.get("price")
                or 0.0
            )
        except Exception:
            entry_price = 0.0

        if entry_price <= 0:
            return

        rec = str(pick.get("recommendation") or "").lower()
        direction = "SHORT" if "sell" in rec else "LONG"

        stop_cfg = profile_cfg.get("stop") or {}
        stop_type = str(stop_cfg.get("type") or "percent")
        try:
            stop_val = float(stop_cfg.get("value") or 0.0)
        except Exception:
            stop_val = 0.0

        stop_price: Optional[float] = None
        stop_pct: Optional[float] = None
        if stop_type == "price" and stop_val > 0:
            stop_price = stop_val
        elif stop_type in ("percent", "atr_multiple") and stop_val > 0:
            stop_pct = stop_val
            dist = entry_price * (stop_val / 100.0)
            if direction == "LONG":
                stop_price = entry_price - dist
            else:
                stop_price = entry_price + dist

        target_cfg = profile_cfg.get("target") or {}
        target_type = str(target_cfg.get("type") or "percent")
        target_val_raw = target_cfg.get("value")
        target_price: Optional[float] = None
        target_pct: Optional[float] = None
        if target_val_raw is not None:
            try:
                target_val = float(target_val_raw)
            except Exception:
                target_val = 0.0
            if target_val > 0:
                if target_type == "price":
                    target_price = target_val
                elif target_type == "percent":
                    target_pct = target_val
                    dist = entry_price * (target_val / 100.0)
                    if direction == "LONG":
                        target_price = entry_price + dist
                    else:
                        target_price = entry_price - dist
                elif target_type == "rr_multiple" and stop_price is not None:
                    stop_dist = abs(entry_price - stop_price)
                    dist = stop_dist * target_val
                    if direction == "LONG":
                        target_price = entry_price + dist
                    else:
                        target_price = entry_price - dist

        trailing_cfg = profile_cfg.get("trailing") or {}
        trailing_enabled = bool(trailing_cfg.get("enabled"))
        activation_type = str(trailing_cfg.get("activation_type") or "percent")
        trail_type = str(trailing_cfg.get("trail_type") or "percent")
        try:
            activation_val = float(trailing_cfg.get("activation_value") or 0.0)
        except Exception:
            activation_val = 0.0
        try:
            trail_val = float(trailing_cfg.get("trail_value") or 0.0)
        except Exception:
            trail_val = 0.0

        trailing_stop: Dict[str, Any] = exit_strategy.get("trailing_stop") or {}
        if not isinstance(trailing_stop, dict):
            trailing_stop = {}

        if trailing_enabled and activation_type == "percent" and trail_type == "percent":
            trailing_stop.update(
                {
                    "enabled": True,
                    "activation_pct": activation_val,
                    "trail_distance_pct": trail_val,
                }
            )
        elif trailing_enabled:
            trailing_stop.setdefault("enabled", True)

        time_stop_cfg = profile_cfg.get("time_stop") or {}
        time_enabled = bool(time_stop_cfg.get("enabled"))
        max_hold_minutes = time_stop_cfg.get("max_hold_minutes")
        try:
            max_hold_mins_f = (
                float(max_hold_minutes) if max_hold_minutes is not None else None
            )
        except Exception:
            max_hold_mins_f = None

        if stop_price is not None:
            exit_strategy["stop_loss_price"] = round(stop_price, 2)
        if stop_pct is not None:
            exit_strategy["stop_pct"] = round(stop_pct, 2)
        if target_price is not None:
            exit_strategy["target_price"] = round(target_price, 2)
        if target_pct is not None:
            exit_strategy["target_pct"] = round(target_pct, 2)
        if trailing_stop:
            exit_strategy["trailing_stop"] = trailing_stop
        if time_enabled and max_hold_mins_f is not None:
            exit_strategy["max_hold_mins"] = max_hold_mins_f

        profile_kind = str(profile_cfg.get("kind") or "").lower()
        if not profile_kind:
            upper_id = str(profile_id).upper()
            if "TRAIL" in upper_id:
                profile_kind = "trail"
            elif "TIGHT" in upper_id:
                profile_kind = "tight_stop"
            else:
                profile_kind = "standard"

        scalp_type = profile_kind
        exit_strategy["scalp_type"] = scalp_type

        strategy_profile = exit_strategy.get("strategy_profile") or {}
        if not isinstance(strategy_profile, dict):
            strategy_profile = {}
        strategy_profile.setdefault("id", profile_id)
        strategy_profile.setdefault("name", profile_cfg.get("name") or profile_id)
        strategy_profile.setdefault("mode", "Scalping")
        strategy_profile.setdefault("direction", direction)
        strategy_profile.setdefault("symbol", symbol)
        exit_strategy["strategy_profile"] = strategy_profile

        exit_strategy.setdefault("direction", direction)
        exit_strategy.setdefault("mode", "Scalping")
        exit_strategy.setdefault("entry_price", round(entry_price, 2))

        pick["exit_strategy"] = exit_strategy
    
    def _attach_s1_strategy_profile(
        self,
        exit_strategy: Dict[str, Any],
    ) -> None:
        direction = str(exit_strategy.get("direction") or "LONG").upper()

        if exit_strategy.get("strategy_profile"):
            return

        strategy_profile: Dict[str, Any] = {
            "id": "S1_HEIKIN_ASHI_PSAR_RSI_3M",
            "name": "Heikin-Ashi + PSAR + RSI (3m)",
            "mode": "Intraday",
            "timeframe": "3m",
            "direction": direction,
            "version": 1,
            "indicator_params": {
                "psar": {"step": 0.02, "increment": 0.02, "max_step": 0.2},
                "rsi": {"length": 14},
            },
            "entry_criteria": {
                "ha_trend": "green" if direction == "LONG" else "red",
                "price_vs_psar": "above" if direction == "LONG" else "below",
                "rsi_min": 50 if direction == "LONG" else None,
                "rsi_max": None if direction == "LONG" else 50,
                "description": "HA trend, PSAR alignment, and RSI(14) confirmation on 3m candles.",
            },
            "exit_criteria": {
                "rr_targets": [1.0, 2.0, 3.0],
                "partial_booking_at_rr": 1.0,
                "move_sl_to_breakeven_at_rr": 1.0,
                "trail_with": "PSAR",
                "invalidated_when_long": {
                    "ha_trend": "red",
                    "price_vs_psar": "below",
                    "rsi_below": 50,
                },
                "invalidated_when_short": {
                    "ha_trend": "green",
                    "price_vs_psar": "above",
                    "rsi_above": 50,
                },
            },
            "bearish_execution": {
                "allowed_modes": [
                    "CASH_INTRADAY",
                    "FUTURES",
                    "OPTIONS_PUT",
                ],
                "default_mode": "CASH_INTRADAY",
            },
        }

        exit_strategy["strategy_profile"] = strategy_profile

    def _attach_s3_strategy_profile(
        self,
        exit_strategy: Dict[str, Any],
    ) -> None:
        direction = str(exit_strategy.get("direction") or "LONG").upper()

        if exit_strategy.get("strategy_profile"):
            return

        strategy_profile: Dict[str, Any] = {
            "id": "S3_BB_TREND_PULLBACK",
            "name": "Bollinger Bands Trend Pullback",
            "mode": "Swing",
            "timeframe": "1h",
            "direction": direction,
            "version": 1,
            "indicator_params": {
                "bb": {
                    "length": 20,
                    "multiplier": 2.0,
                    "slope_lookback_bars": 5,
                }
            },
            "entry_criteria": {
                "description": "Trend-following BB pullback: BB mid-band aligned with trend and price bouncing from mid-band.",
            },
            "exit_criteria": {
                "partial_booking_at_rr": 2.0,
                "slope_lookback_bars": 5,
            },
        }

        exit_strategy["strategy_profile"] = strategy_profile

    def _build_exit_strategy_from_trade_plan(
        self,
        trade_plan: Dict[str, Any],
        mode: str,
    ) -> Optional[Dict[str, Any]]:
        """Normalize TradeStrategyAgent trade_plan into exit_strategy schema.

        This is primarily used for Swing-mode trades where TradeStrategyAgent
        runs and produces a detailed multi-target plan.
        """

        try:
            direction = (trade_plan.get("direction") or "LONG").upper()
            entry = trade_plan.get("entry") or {}
            entry_price = float(entry.get("price") or 0.0)

            stops = trade_plan.get("stop_loss") or {}
            stop_price = float(stops.get("initial") or 0.0)

            targets = trade_plan.get("targets") or {}

            # Extract individual T1/T2/T3 price levels when present
            def _get_level_price(level_key: str) -> float:
                level = targets.get(level_key) or {}
                try:
                    return float(level.get("price") or 0.0)
                except Exception:
                    return 0.0

            t1_price = _get_level_price("T1")
            t2_price = _get_level_price("T2")
            t3_price = _get_level_price("T3")

            # Backward-compatible primary target: prefer T2, then T1, then T3
            target_price = None
            for price_val in (t2_price, t1_price, t3_price):
                if price_val > 0:
                    target_price = price_val
                    break

            if entry_price <= 0 or stop_price <= 0 or target_price is None:
                return None

            stop_pct = abs(entry_price - stop_price) / entry_price * 100.0

            def _pct(price_val: float) -> Optional[float]:
                if price_val <= 0:
                    return None
                try:
                    return abs(price_val - entry_price) / entry_price * 100.0
                except Exception:
                    return None

            tp1_pct = _pct(t1_price)
            tp2_pct = _pct(t2_price)
            tp3_pct = _pct(t3_price)

            # Backward-compatible single target_pct kept for existing consumers:
            # use the highest defined target (T3 > T2 > T1) as the primary.
            primary_target_pct = None
            for pct_val in (tp3_pct, tp2_pct, tp1_pct):
                if isinstance(pct_val, (int, float)) and pct_val > 0:
                    primary_target_pct = pct_val
                    break

            if primary_target_pct is None:
                primary_target_pct = abs(target_price - entry_price) / entry_price * 100.0

            exit_strategy: Dict[str, Any] = {
                "direction": direction,
                "entry_price": round(entry_price, 2),
                "stop_loss_price": round(stop_price, 2),
                "target_price": round(target_price, 2),
                "stop_pct": round(stop_pct, 2),
                "target_pct": round(primary_target_pct, 2),
                "time_horizon": trade_plan.get("time_horizon"),
                "risk_percent": trade_plan.get("risk_percent"),
                "risk_reward": trade_plan.get("risk_reward"),
                "setup_quality": trade_plan.get("setup_quality"),
                "invalidation": trade_plan.get("invalidation"),
                "mode": mode,
                "source": "trade_strategy",
            }

            # Attach explicit TP1/TP2/TP3 ladder (prices and percentages) for
            # downstream analytics (Winning Trades, ladders, TP3 HIT status).
            # Only include levels that are actually present in the trade plan.
            ladder: Dict[str, Any] = {}
            if t1_price > 0:
                ladder["tp1_price"] = round(t1_price, 2)
                if isinstance(tp1_pct, (int, float)):
                    ladder["tp1_pct"] = round(float(tp1_pct), 2)
            if t2_price > 0:
                ladder["tp2_price"] = round(t2_price, 2)
                if isinstance(tp2_pct, (int, float)):
                    ladder["tp2_pct"] = round(float(tp2_pct), 2)
            if t3_price > 0:
                ladder["tp3_price"] = round(t3_price, 2)
                if isinstance(tp3_pct, (int, float)):
                    ladder["tp3_pct"] = round(float(tp3_pct), 2)

            if ladder:
                exit_strategy["targets_ladder"] = ladder

            return exit_strategy
        except Exception:
            return None

    def _build_exit_strategy_from_mode_template(
        self,
        result: Dict[str, Any],
        pick: Dict[str, Any],
        mode: str,
    ) -> Optional[Dict[str, Any]]:
        """Fallback exit_strategy from mode-specific templates.

        Uses trading_modes.get_strategy_parameters for modes like Intraday
        where we may not run TradeStrategyAgent but still want a consistent
        target/stop structure for monitoring.
        """

        try:
            mode_enum_map = {
                "Intraday": TradingMode.INTRADAY,
                "Swing": TradingMode.SWING,
                "Options": TradingMode.OPTIONS,
                "Futures": TradingMode.FUTURES,
            }

            tm = mode_enum_map.get(mode)
            if tm is None:
                return None

            blend_score = float(result.get("blend_score", 0.0))
            current_price = pick.get("price")
            try:
                current_price_f = float(current_price) if current_price is not None else 0.0
            except Exception:
                current_price_f = 0.0

            params = get_strategy_parameters(tm, blend_score, current_price_f or None)

            entry_price = current_price_f
            stop_price = float(params.get("stop_loss") or 0.0)
            target_price = float(params.get("target_price") or 0.0)

            if entry_price <= 0 or (stop_price <= 0 and target_price <= 0):
                return None

            stop_pct = float(params.get("stop_percent") or 0.0)
            target_pct = float(params.get("target_percent") or 0.0)

            rec = str(result.get("recommendation") or "").lower()
            direction = "SHORT" if "sell" in rec else "LONG"

            return {
                "direction": direction,
                "entry_price": round(entry_price, 2),
                "stop_loss_price": round(stop_price, 2) if stop_price > 0 else None,
                "target_price": round(target_price, 2) if target_price > 0 else None,
                "stop_pct": round(stop_pct, 2) if stop_pct > 0 else None,
                "target_pct": round(target_pct, 2) if target_pct > 0 else None,
                "time_horizon": params.get("horizon"),
                "risk_percent": None,
                "risk_reward": params.get("risk_reward"),
                "setup_quality": None,
                "invalidation": None,
                "mode": mode,
                "source": "mode_template",
            }
        except Exception:
            return None

    async def _apply_sr_scoring(
        self,
        universe: str,
        actionable_results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Enrich Intraday actionable results with S/R context and adjust ordering.

        This is a light tilt on top of the existing blend_score-based
        ordering so that high-quality S/R locations get preferred when
        scores are otherwise comparable.
        """

        scored: List[Dict[str, Any]] = []

        for r in actionable_results:
            symbol = r.get("symbol")
            if not symbol:
                scored.append(r)
                continue

            # Determine direction from recommendation (LONG for Buy, SHORT for Sell).
            rec_str = str(r.get("recommendation") or "").lower()
            direction = "SHORT" if "sell" in rec_str else "LONG"

            # Get current price from technical agent metadata.
            current_price = None
            for agent_result in r.get("agents", []):
                if agent_result.get("agent") == "technical":
                    meta = agent_result.get("metadata") or {}
                    current_price = meta.get("current_price")
                    break

            try:
                price_f = float(current_price) if current_price is not None else 0.0
            except Exception:
                price_f = 0.0

            if price_f > 0.0:
                try:
                    sr_context, sr_score = await self._build_sr_context_for_pick(
                        symbol=str(symbol),
                        current_price=price_f,
                        mode="Intraday",
                        direction=direction,
                    )
                    if sr_context is not None:
                        r["sr_context"] = sr_context
                    if sr_score is not None:
                        r["support_resistance_score"] = sr_score
                except Exception as e:
                    print(f"[TopPicksEngine] SR context failed for {symbol}: {e}")

            # Compute SR-adjusted score: small tilt around base blend score.
            try:
                base_val = r.get("score_blend", r.get("blend_score", 0.0))
                base_score = float(base_val or 0.0)
            except Exception:
                base_score = 0.0
            try:
                sr_val = r.get("support_resistance_score", 50.0)
                sr_score_f = float(sr_val or 50.0)
            except Exception:
                sr_score_f = 50.0

            tilt = 0.2 * (sr_score_f - 50.0)
            r["_sr_adjusted_score"] = base_score + tilt
            scored.append(r)

        scored.sort(
            key=lambda x: x.get("_sr_adjusted_score", x.get("blend_score", 0.0)),
            reverse=True,
        )
        return scored

    async def _build_sr_context_for_pick(
        self,
        symbol: str,
        current_price: float,
        mode: str,
        direction: str,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[float]]:
        """Compute multi-timeframe S/R context and composite score for a pick."""

        mode_norm = normalize_mode(mode)

        # Mode-aware weighting of timeframes (Y>M>W>D by default).
        if mode_norm == "Swing":
            weights = {"Y": 5.0, "M": 4.0, "W": 3.0, "D": 1.0}
        elif mode_norm == "Intraday":
            weights = {"Y": 3.0, "M": 4.0, "W": 3.0, "D": 2.0}
        else:  # Scalping / others
            weights = {"Y": 2.0, "M": 3.0, "W": 4.0, "D": 3.0}

        timeframes_ctx: Dict[str, Any] = {}
        weighted_sum = 0.0
        total_weight = 0.0

        for scope in ("Y", "M", "W", "D"):
            w = float(weights.get(scope, 0.0))
            if w <= 0.0:
                continue

            try:
                levels = await support_resistance_service.get_levels(symbol, scope)
            except Exception as e:
                print(f"[TopPicksEngine] SR levels fetch failed for {symbol}/{scope}: {e}")
                continue

            if levels is None:
                continue

            tf_score, tf_meta = self._score_single_timeframe_sr(
                levels=levels,
                current_price=current_price,
                direction=direction,
            )

            timeframes_ctx[scope] = {
                "p": levels.p,
                "r1": levels.r1,
                "r2": levels.r2,
                "r3": levels.r3,
                "s1": levels.s1,
                "s2": levels.s2,
                "s3": levels.s3,
                "computed_at_ist": levels.computed_at_ist.isoformat(),
                "score": round(tf_score, 1),
                **tf_meta,
            }

            weighted_sum += w * tf_score
            total_weight += w

        if total_weight <= 0.0 or not timeframes_ctx:
            return None, None

        composite_score = weighted_sum / total_weight

        # Human-readable comment summarising key confluences.
        labels = {"Y": "Yearly", "M": "Monthly", "W": "Weekly", "D": "Daily"}
        comments: List[str] = []
        for scope, meta in timeframes_ctx.items():
            label = labels.get(scope, scope)
            if meta.get("near_support"):
                comments.append(f"Near {label} support")
            if meta.get("near_resistance"):
                comments.append(f"Near {label} resistance")

        comment = "; ".join(comments) if comments else "No strong S/R confluence detected"

        sr_context: Dict[str, Any] = {
            "score": round(composite_score, 1),
            "direction": direction,
            "timeframes": timeframes_ctx,
            "comment": comment,
        }

        return sr_context, composite_score

    def _score_single_timeframe_sr(
        self,
        levels: Any,
        current_price: float,
        direction: str,
    ) -> Tuple[float, Dict[str, Any]]:
        """Return an S/R score (0-100) for one timeframe and metadata.

        LONG bias prefers proximity to support and distance from
        resistance; SHORT bias mirrors that behaviour.
        """

        meta: Dict[str, Any] = {}

        try:
            supports = [
                float(levels.s1),
                float(levels.s2),
                float(levels.s3),
            ]
            resistances = [
                float(levels.r1),
                float(levels.r2),
                float(levels.r3),
            ]
        except Exception:
            return 50.0, meta

        supports = [s for s in supports if s > 0]
        resistances = [r for r in resistances if r > 0]
        if current_price <= 0 or (not supports and not resistances):
            return 50.0, meta

        def _pct_dist(level: float) -> float:
            return abs(current_price - level) / current_price * 100.0

        nearest_support_pct = min((_pct_dist(s) for s in supports), default=999.0)
        nearest_resistance_pct = min((_pct_dist(r) for r in resistances), default=999.0)

        meta["distance_to_nearest_support_pct"] = round(nearest_support_pct, 2)
        meta["distance_to_nearest_resistance_pct"] = round(nearest_resistance_pct, 2)
        meta["near_support"] = nearest_support_pct <= 1.0
        meta["near_resistance"] = nearest_resistance_pct <= 1.0

        score = 50.0

        if direction.upper() == "LONG":
            # Reward being close to support.
            if nearest_support_pct <= 1.0:
                score += 20.0
            elif nearest_support_pct <= 2.0:
                score += 10.0

            # Penalise being very close to resistance.
            if nearest_resistance_pct <= 1.0:
                score -= 20.0
            elif nearest_resistance_pct <= 2.0:
                score -= 10.0
        else:  # SHORT
            # For shorts, support below is a risk; resistance above is helpful.
            if nearest_resistance_pct <= 1.0:
                score += 20.0
            elif nearest_resistance_pct <= 2.0:
                score += 10.0

            if nearest_support_pct <= 1.0:
                score -= 20.0
            elif nearest_support_pct <= 2.0:
                score -= 10.0

        # Clamp to [0, 100]
        if score < 0.0:
            score = 0.0
        elif score > 100.0:
            score = 100.0

        return score, meta

    async def _apply_index_relative_filters(
        self,
        mode: str,
        bullish_results: List[Dict[str, Any]],
        bearish_results: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        mode_norm = normalize_mode(mode)

        try:
            provider = get_data_provider()
            indices = provider.get_indices_quote()
        except Exception as e:
            print(f"[TopPicksEngine] Index data unavailable: {e}")
            return bullish_results, bearish_results

        index_entry = None
        for key in ("NIFTY 50", "NIFTY50", "NIFTY"):
            if key in indices:
                index_entry = indices[key]
                break

        if not index_entry:
            return bullish_results, bearish_results

        try:
            index_raw = index_entry.get("change_percent", 0)
            index_change = float(index_raw or 0.0)
        except Exception:
            index_change = 0.0

        if mode_norm in ("Intraday", "Futures"):
            down_threshold = -0.8
            up_threshold = 0.8
            rel_threshold = 1.0
            max_with_trend = 2
        else:
            down_threshold = -0.8
            up_threshold = 0.8
            rel_threshold = 0.5
            max_with_trend = 3

        if index_change >= up_threshold:
            market_direction = "UP"
        elif index_change <= down_threshold:
            market_direction = "DOWN"
        else:
            return bullish_results, bearish_results

        symbols = sorted(
            {r.get("symbol") for r in bullish_results + bearish_results if r.get("symbol")}
        )

        if not symbols:
            return bullish_results, bearish_results

        try:
            quotes = provider.get_quote(symbols)
        except Exception as e:
            print(f"[TopPicksEngine] Quote fetch failed for index filter: {e}")
            return bullish_results, bearish_results

        def _change(symbol: str) -> Optional[float]:
            quote = quotes.get(symbol)
            if not quote:
                return None
            value = quote.get("change_percent")
            try:
                return float(value)
            except Exception:
                return None

        if market_direction == "DOWN":
            filtered_bullish: List[Dict[str, Any]] = []
            for r in bullish_results:
                symbol = r.get("symbol")
                if not symbol:
                    filtered_bullish.append(r)
                    continue
                stock_change = _change(symbol)
                if stock_change is None:
                    filtered_bullish.append(r)
                    continue
                if stock_change >= index_change + rel_threshold:
                    filtered_bullish.append(r)
            if len(filtered_bullish) > max_with_trend:
                filtered_bullish = filtered_bullish[:max_with_trend]
            bullish_results = filtered_bullish
        else:
            filtered_bearish: List[Dict[str, Any]] = []
            for r in bearish_results:
                symbol = r.get("symbol")
                if not symbol:
                    filtered_bearish.append(r)
                    continue
                stock_change = _change(symbol)
                if stock_change is None:
                    filtered_bearish.append(r)
                    continue
                if stock_change <= index_change - rel_threshold:
                    filtered_bearish.append(r)
            if len(filtered_bearish) > max_with_trend:
                filtered_bearish = filtered_bearish[:max_with_trend]
            bearish_results = filtered_bearish

        return bullish_results, bearish_results

    def _format_pick(self, rank: int, result: Dict[str, Any]) -> Dict[str, Any]:
        """Format analysis result as a pick"""

        # Get current price (from technical agent metadata)
        current_price: Optional[float] = None
        target_price: Optional[float] = None
        upside_pct: Optional[float] = None

        for agent_result in result.get("agents", []):
            if agent_result.get("agent") == "technical":
                metadata = agent_result.get("metadata", {})
                current_price = metadata.get("current_price")

                # Get highest target from signals
                for signal in agent_result.get("signals", []):
                    if "Target" in str(signal.get("type", "")):
                        try:
                            value = signal.get("value", "")
                            if "₹" in value:
                                price_str = value.split("₹")[1].split()[0]
                                price = float(price_str.replace(",", ""))
                                if target_price is None or price > target_price:
                                    target_price = price
                        except Exception:
                            continue

                break

        # Calculate upside
        if current_price is not None and target_price is not None and current_price > 0:
            try:
                upside_pct = (float(target_price) - float(current_price)) / float(current_price) * 100.0
            except Exception:
                upside_pct = None

        # Extract agent scores for insights generation
        scores: Dict[str, Any] = {}
        for agent in result.get("agents", []):
            agent_name = agent.get("agent", "")
            scores[agent_name] = agent.get("score", 50)

        # Derive simple regime/volatility/user-risk buckets for bandit context.
        regime_raw: Optional[str] = None
        vol_level_raw: Optional[str] = None
        for agent in result.get("agents", []):
            if agent.get("agent") == "market_regime":
                meta = agent.get("metadata") or {}
                regime_raw = str(meta.get("regime") or "UNKNOWN").upper()
                # market_regime_agent exposes volatility level as 'volatility'.
                try:
                    vol_level_raw = str(meta.get("volatility") or "").upper() or None
                except Exception:
                    vol_level_raw = None
                break

        if regime_raw in ("BULL", "WEAK_BULL"):
            regime_bucket = "Bull"
        elif regime_raw in ("BEAR", "WEAK_BEAR"):
            regime_bucket = "Bear"
        else:
            regime_bucket = "Range"

        # Map volatility level into coarse buckets. This will drive both
        # contextual bandits and regime/vol-aware entry filters.
        if vol_level_raw == "LOW":
            vol_bucket = "LowVol"
        elif vol_level_raw == "MEDIUM":
            vol_bucket = "MediumVol"
        elif vol_level_raw == "HIGH":
            vol_bucket = "HighVol"
        else:
            vol_bucket = "Unknown"

        # User risk bucket will eventually come from personalization; keep
        # a stable default so bandit_ctx is always defined.
        user_risk_bucket = "Moderate"

        pick: Dict[str, Any] = {
            "rank": rank,
            "symbol": result.get("symbol"),
            "score_blend": round(result.get("blend_score", 0) or 0.0, 1),
            "blend_score": round(result.get("blend_score", 0) or 0.0, 1),
            "recommendation": result.get("recommendation", "Hold"),
            "is_actionable": result.get("is_actionable", True),
            "recommendation_note": result.get("recommendation_note"),
            "risk_reward_ratio": result.get("risk_reward_ratio"),
            "color_scheme": result.get("color_scheme", {}),
            "confidence": result.get("confidence", "Medium"),
            "reasoning": self._generate_reasoning(result),
            "rationale": self._generate_reasoning(result),
            "scores": scores,
            "price": current_price,
            "target": target_price,
            "upside_pct": round(upside_pct, 2) if upside_pct is not None else None,
            "key_signals": (result.get("key_signals", []) or [])[:3],
            "agent_consensus": self._calculate_consensus(result),
            "horizon": "Swing",  # Default horizon, can be made dynamic
            "timestamp": datetime.now().isoformat() + "Z",
            "regime_bucket": regime_bucket,
            "vol_bucket": vol_bucket,
            "user_risk_bucket": user_risk_bucket,
        }

        if "sr_context" in result:
            pick["sr_context"] = result.get("sr_context")
        if "support_resistance_score" in result:
            pick["support_resistance_score"] = result.get("support_resistance_score")

        return pick

    def _generate_reasoning(self, result: Dict[str, Any]) -> str:
        """Generate human-readable reasoning for the pick"""

        agents_data = result.get("agents", [])
        bullish_agents: List[str] = []
        bearish_agents: List[str] = []

        for agent in agents_data:
            score = agent.get("score", 50)
            agent_name = str(agent.get("agent", "")).replace("_", " ").title()

            if score >= 60:
                bullish_agents.append(f"{agent_name} ({score})")
            elif score <= 40:
                bearish_agents.append(f"{agent_name} ({score})")

        parts: List[str] = []

        if len(bullish_agents) >= 7:
            parts.append(f"Strong consensus with {len(bullish_agents)}/10 agents bullish")
        elif len(bullish_agents) >= 5:
            parts.append(f"Moderate bullish view from {len(bullish_agents)}/10 agents")

        key_signals = result.get("key_signals", [])
        if key_signals:
            top_signal = key_signals[0]
            parts.append(f"{top_signal.get('type', 'Signal')}: {top_signal.get('signal', '')}")

        reasoning = ". ".join(parts) if parts else result.get("reasoning", "Analysis complete")

        return reasoning

    def _calculate_consensus(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Compute a simple agent consensus snapshot for a result.

        This is used for analytics/summary only and does NOT affect
        recommendation thresholds or KPI-related selection logic. It counts how
        many agents are bullish/bearish based on their scores and scales the
        bullish count to a 0-10 range for display.
        """

        agents = result.get("agents", []) or []
        if not isinstance(agents, list) or not agents:
            return {"bullish": 0, "bearish": 0, "neutral": 0, "total_agents": 0}

        bullish = 0
        bearish = 0
        neutral = 0

        for agent in agents:
            try:
                score_val = agent.get("score", 50)
                score = float(score_val if score_val is not None else 50.0)
            except Exception:
                score = 50.0

            if score >= 60.0:
                bullish += 1
            elif score <= 40.0:
                bearish += 1
            else:
                neutral += 1

        total = len(agents)
        if total > 0:
            try:
                bullish_scaled = int(round(10.0 * bullish / float(total)))
            except Exception:
                bullish_scaled = bullish
        else:
            bullish_scaled = 0

        return {
            "bullish": bullish_scaled,
            "bearish": bearish,
            "neutral": neutral,
            "total_agents": total,
        }

    def _get_next_refresh_time(self) -> str:
        """Get next refresh time (6 AM IST next day)"""
        now = datetime.now()
        tomorrow = now + timedelta(days=1)
        next_refresh = tomorrow.replace(hour=6, minute=0, second=0, microsecond=0)
        return next_refresh.isoformat() + 'Z'
    
    def _store_picks(self, picks_data: Dict[str, Any]):
        """Store picks to disk for historical tracking"""
        try:
            date_str = picks_data['date']
            file_path = self.storage_path / f"picks_{date_str}.json"
            
            with open(file_path, 'w') as f:
                json.dump(picks_data, f, indent=2)
            
            print(f"✅ Picks stored to: {file_path}")
            
        except Exception as e:
            print(f"⚠️  Failed to store picks: {e}")

    def _sanitize_for_json(self, obj: Any) -> Any:
        """Recursively convert objects to JSON-serializable types.

        Handles common offenders like numpy scalar types, pandas timestamps,
        and any other custom objects by falling back to string conversion.
        """

        # Numpy scalar types
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)

        # Pandas timestamp / datetime-like
        if isinstance(obj, (pd.Timestamp,)):
            return obj.to_pydatetime().isoformat()

        # Primitive JSON types pass through
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj

        # Dicts and lists: recurse
        if isinstance(obj, dict):
            return {self._sanitize_for_json(k): self._sanitize_for_json(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._sanitize_for_json(v) for v in obj]

        # Tuples/sets -> lists
        if isinstance(obj, (tuple, set)):
            return [self._sanitize_for_json(v) for v in obj]

        # Fallback: best-effort string representation
        return str(obj)
    
    def load_latest_picks(self) -> Optional[Dict[str, Any]]:
        """Load the most recent picks from storage"""
        try:
            # Find latest file
            files = sorted(self.storage_path.glob("picks_*.json"), reverse=True)
            
            if files:
                latest_file = files[0]
                with open(latest_file, 'r') as f:
                    return json.load(f)
            
            return None
            
        except Exception as e:
            print(f"⚠️  Failed to load picks: {e}")
            return None
    
    def _print_summary(self, picks_data: Dict[str, Any]):
        """Print a beautiful summary of the picks"""
        print(f"\n{'='*60}")
        print(f"🎯 TOP {len(picks_data['picks'])} PICKS - {picks_data['date']}")
        print(f"{'='*60}\n")
        
        for pick in picks_data['picks']:
            print(f"{pick['rank']}. {pick['symbol']:<12} | Score: {pick['blend_score']:>5.1f} | {pick['recommendation']:<10}")
            print(f"   Confidence: {pick['confidence']:<8} | Consensus: {pick['agent_consensus']['bullish']}/10 bullish")
            
            if pick.get('upside_pct'):
                print(f"   Target: ₹{pick['target']:.0f} ({pick['upside_pct']:+.1f}% upside)")
            
            print(f"   Reason: {pick['reasoning'][:80]}...")
            print()
        
        print(f"{'='*60}")
        print(f"✅ Generation complete!")
        print(f"Next refresh: {picks_data['next_refresh']}")
        print(f"{'='*60}\n")


# Global instance
top_picks_engine = TopPicksEngine()


# Convenience functions
async def generate_top_picks(
    universe: str = "nifty50",
    top_n: int = 5,
    min_confidence: str = "medium",
    mode: str = "Swing"
) -> Dict[str, Any]:
    """
    Generate top picks (convenience function).
    Can be called from scheduler or API.
    
    Args:
        universe: Stock universe to analyze
        top_n: Number of picks to return
        min_confidence: Minimum confidence filter
        mode: Trading mode for agent selection optimization
    """
    # Import mode-specific agent selector
    from ..utils.mode_agent_selector import get_agents_for_mode, get_agent_weights_for_mode
    
    # Get optimized agent list and weights for this mode
    selected_agents = get_agents_for_mode(mode)
    agent_weights = get_agent_weights_for_mode(mode)
    
    print(f"📊 Mode: {mode} | Using {len(selected_agents)} agents: {', '.join(selected_agents)}")
    
    return await top_picks_engine.generate_daily_picks(
        universe=universe,
        top_n=top_n,
        min_confidence=min_confidence,
        agent_names=selected_agents,
        mode=mode  # Pass mode for storage and tracking
    )


def get_latest_picks() -> Optional[Dict[str, Any]]:
    """Get the latest generated picks from storage"""
    return top_picks_engine.load_latest_picks()


# For testing
if __name__ == "__main__":
    async def test():
        # Test with small universe
        picks = await generate_top_picks(universe="test", top_n=3)
        print("\n✅ Test complete!")
        print(f"Generated {len(picks['picks'])} picks")
    
    asyncio.run(test())
