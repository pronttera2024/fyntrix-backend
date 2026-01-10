"""
Global Score Store for ARISE
Ensures consistent scoring across multiple universes (Nifty 50, Bank Nifty, etc.)

Key Feature: A stock's score is computed ONCE and reused across all universes
This prevents inconsistency where SBIN ranks #1 in Bank Nifty but doesn't appear 
in Top 5 Nifty 50 while lower-ranked ICICI does.
"""

import asyncio
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from pathlib import Path
import json
from collections import defaultdict

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

# Import recommendation system for actionable picks
from ..utils.recommendation_system import (
    get_recommendation,
    filter_actionable_picks,
    format_pick_for_api,
    calculate_risk_reward_ratio
)


class GlobalScoreStore:
    """
    Maintains a single source of truth for stock scores across all universes.
    
    Workflow:
    1. Analyze ALL unique stocks from ALL universes ONCE
    2. Store scores in global cache with timestamp
    3. Filter by universe when serving top picks
    4. Guarantee: If SBIN > ICICI globally, this order is maintained in ALL universes
    """
    
    def __init__(self, cache_ttl_hours: int = 6):
        """
        Initialize Global Score Store
        
        Args:
            cache_ttl_hours: How long scores remain valid (default 6 hours = market session)
        """
        self.cache_ttl_hours = cache_ttl_hours
        self.cache_file = Path(__file__).parent.parent.parent / "data" / "global_scores" / "score_cache.json"
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        
        # In-memory cache
        self._score_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_timestamp: Optional[datetime] = None
        
        # Load existing cache
        self._load_cache()
        
        # Initialize 13-agent coordinator
        self.coordinator = AgentCoordinator()
        self._setup_agents()
    
    def _setup_agents(self):
        """Setup the 13-agent system with proper weights"""
        # 10 Core Scoring Agents (100% total)
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
        self.coordinator.register_agent(TradeStrategyAgent(weight=0.00))
        self.coordinator.register_agent(AutoMonitoringAgent(weight=0.00))
        self.coordinator.register_agent(PersonalizationAgent(weight=0.00))
        
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
    
    def _is_cache_valid(self) -> bool:
        """Check if current cache is still valid"""
        if not self._cache_timestamp or not self._score_cache:
            return False
        
        age = datetime.now() - self._cache_timestamp
        return age < timedelta(hours=self.cache_ttl_hours)
    
    def _load_cache(self):
        """Load cache from disk"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    self._score_cache = data.get('scores', {})
                    timestamp_str = data.get('timestamp')
                    if timestamp_str:
                        self._cache_timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    
                    # Check if valid
                    if self._is_cache_valid():
                        print(f"[GlobalScoreStore] Loaded valid cache with {len(self._score_cache)} stocks")
                    else:
                        print(f"[GlobalScoreStore] Cache expired, will refresh")
                        self._score_cache = {}
                        self._cache_timestamp = None
        except Exception as e:
            print(f"[GlobalScoreStore] Failed to load cache: {e}")
            self._score_cache = {}
            self._cache_timestamp = None
    
    def _save_cache(self):
        """Save cache to disk"""
        try:
            data = {
                'timestamp': self._cache_timestamp.isoformat() + 'Z' if self._cache_timestamp else None,
                'scores': self._score_cache,
                'ttl_hours': self.cache_ttl_hours
            }
            
            with open(self.cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f"[GlobalScoreStore] Cache saved with {len(self._score_cache)} stocks")
        except Exception as e:
            print(f"[GlobalScoreStore] Failed to save cache: {e}")
    
    async def ensure_scores_available(
        self,
        all_symbols: Set[str],
        force_refresh: bool = False,
        max_concurrent: int = 10
    ) -> Dict[str, Dict[str, Any]]:
        """
        Ensure all symbols have valid scores in cache.
        
        Args:
            all_symbols: Set of ALL symbols across ALL universes
            force_refresh: Force re-analysis even if cache valid
            max_concurrent: Max parallel analyses
            
        Returns:
            Dictionary of {symbol: score_data}
        """
        
        # Check if we need to refresh
        if not force_refresh and self._is_cache_valid():
            # Check if all requested symbols are in cache
            missing_symbols = all_symbols - set(self._score_cache.keys())
            if not missing_symbols:
                print(f"[GlobalScoreStore] Cache hit! All {len(all_symbols)} symbols available")
                return self._score_cache
            else:
                print(f"[GlobalScoreStore] Partial cache hit. Missing {len(missing_symbols)} symbols")
                all_symbols = missing_symbols  # Only analyze missing ones
        else:
            print(f"[GlobalScoreStore] Cache {'refresh forced' if force_refresh else 'invalid'}, analyzing all {len(all_symbols)} symbols")
        
        # Analyze all symbols
        print(f"[GlobalScoreStore] Running 13-agent analysis on {len(all_symbols)} symbols...")
        start_time = datetime.now()
        
        results = await self.coordinator.batch_analyze(
            list(all_symbols),
            max_concurrent=max_concurrent
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"[GlobalScoreStore] Analysis complete in {elapsed:.1f}s ({elapsed/len(all_symbols):.2f}s per symbol)")
        
        # Update cache
        for result in results:
            symbol = result.get('symbol')
            if symbol:
                # Extract risk agent score for risk/reward calculation
                risk_score = None
                agents = result.get('agents', [])
                for agent in agents:
                    if agent.get('agent') == 'risk':
                        risk_score = agent.get('score')
                        break
                
                # Get enhanced recommendation with risk/reward
                blend_score = result.get('score_blend', result.get('score', 0))
                confidence = result.get('confidence', 'Medium')
                
                rec_result = get_recommendation(
                    score=blend_score,
                    confidence=confidence,
                    risk_agent_score=risk_score,
                    agent_signals=result.get('key_signals', [])
                )
                
                score_data = {
                    'symbol': symbol,
                    'blend_score': blend_score,
                    'confidence': confidence,
                    'recommendation': rec_result.recommendation.value,
                    'is_actionable': rec_result.is_actionable,
                    'recommendation_note': rec_result.note,
                    'risk_reward_ratio': rec_result.risk_reward_ratio,
                    'color_scheme': rec_result.color_scheme,
                    'agents': agents,
                    'key_signals': result.get('key_signals', []),
                    'reasoning': result.get('reasoning', ''),
                    'analyzed_at': datetime.now().isoformat() + 'Z'
                }
        
                self._score_cache[symbol] = score_data
        
        # Update timestamp and save
        self._cache_timestamp = datetime.now()
        self._save_cache()
        
        return self._score_cache
    
    def get_top_picks_for_universe(
        self,
        universe_symbols: List[str],
        top_n: int = 5,
        min_confidence: str = "medium",
        actionable_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get top N picks for a specific universe, maintaining global ranking consistency.
        
        CRITICAL: Uses the global scores, so if SBIN > ICICI globally, 
        this order is maintained when filtering by any universe.
        
        NEW: Filters out "Neutral" recommendations from Top Picks (actionable_only=True)
        Top Picks = Trade ideas (Strong Buy, Buy, Sell) - NOT Hold/Neutral
        
        Args:
            universe_symbols: Symbols in this universe (e.g., Bank Nifty stocks)
            top_n: Number of top picks
            min_confidence: Minimum confidence filter
            actionable_only: If True, exclude Neutral recommendations (default: True)
            
        Returns:
            List of actionable top picks sorted by global blend_score
        """
        
        # Filter to universe
        universe_scores = []
        for symbol in universe_symbols:
            if symbol in self._score_cache:
                universe_scores.append(self._score_cache[symbol])
        
        # Apply confidence filter
        confidence_levels = {'low': 1, 'medium': 2, 'high': 3}
        min_level = confidence_levels.get(min_confidence.lower(), 2)
        
        filtered = []
        for score_data in universe_scores:
            confidence = score_data.get('confidence', 'Medium').lower()
            result_level = confidence_levels.get(confidence, 2)
            if result_level >= min_level:
                filtered.append(score_data)
        
        # Sort by global blend_score (THIS IS THE KEY - single source of truth!)
        filtered.sort(key=lambda x: x.get('blend_score', 0), reverse=True)
        
        # Filter to actionable picks only (exclude Neutral/Hold)
        if actionable_only:
            actionable_picks = []
            for score_data in filtered:
                if score_data.get('is_actionable', True):
                    actionable_picks.append(score_data)
            filtered = actionable_picks
            
            print(f"[GlobalScoreStore] Filtered to {len(filtered)} actionable picks (excluded Neutral)")
        
        # Take top N from actionable picks
        top_picks = filtered[:top_n]
        
        # Assign ranks within this universe
        picks = []
        for rank, score_data in enumerate(top_picks, 1):
            pick = {**score_data, 'rank': rank}
            picks.append(pick)
        
        total_analyzed = len(universe_symbols)
        total_actionable = len(filtered)
        print(f"[GlobalScoreStore] Returning top {len(picks)} actionable picks from {total_actionable} actionable / {total_analyzed} total stocks")
        
        return picks
    
    def get_score(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get score for a single symbol"""
        return self._score_cache.get(symbol)
    
    def get_all_scores(self) -> Dict[str, Dict[str, Any]]:
        """Get all cached scores"""
        return self._score_cache.copy()
    
    def invalidate_cache(self):
        """Manually invalidate cache to force refresh"""
        self._score_cache = {}
        self._cache_timestamp = None
        print(f"[GlobalScoreStore] Cache invalidated")


# Global instance
global_score_store = GlobalScoreStore(cache_ttl_hours=6)


# Convenience functions
async def get_consistent_top_picks(
    universes: Dict[str, List[str]],
    top_n: int = 5,
    force_refresh: bool = False
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get top picks for multiple universes with guaranteed consistency.
    
    Example:
        universes = {
            'nifty50': ['RELIANCE', 'TCS', ..., 'SBIN', 'ICICI', ...],
            'banknifty': ['SBIN', 'ICICI', 'HDFCBANK', ...]
        }
        
        result = {
            'nifty50': [top 5 from nifty50, sorted by global score],
            'banknifty': [top 5 from banknifty, sorted by SAME global score]
        }
        
    GUARANTEE: If SBIN scores 85 and ICICI scores 80 globally,
               SBIN will rank higher than ICICI in BOTH universes.
    """
    
    # Step 1: Get ALL unique symbols across ALL universes
    all_symbols = set()
    for symbols in universes.values():
        all_symbols.update(symbols)
    
    print(f"[get_consistent_top_picks] Processing {len(all_symbols)} unique stocks across {len(universes)} universes")
    
    # Step 2: Ensure all symbols are analyzed (uses cache if valid)
    await global_score_store.ensure_scores_available(all_symbols, force_refresh=force_refresh)
    
    # Step 3: Get top picks for each universe (filtered from global scores)
    results = {}
    for universe_name, universe_symbols in universes.items():
        picks = global_score_store.get_top_picks_for_universe(
            universe_symbols=universe_symbols,
            top_n=top_n
        )
        results[universe_name] = picks
    
    # Step 4: Verify consistency for common stocks
    _verify_consistency(results, universes)
    
    return results


def _verify_consistency(results: Dict[str, List[Dict[str, Any]]], universes: Dict[str, List[str]]):
    """
    Verify and log consistency of rankings across universes.
    
    This is a sanity check to ensure our global scoring is working correctly.
    """
    
    # Find common symbols across universes
    universe_names = list(universes.keys())
    if len(universe_names) < 2:
        return  # Nothing to compare
    
    common_symbols = set(universes[universe_names[0]])
    for universe_name in universe_names[1:]:
        common_symbols &= set(universes[universe_name])
    
    if not common_symbols:
        print(f"[Consistency Check] No common stocks between universes")
        return
    
    print(f"[Consistency Check] Verifying {len(common_symbols)} common stocks: {sorted(common_symbols)}")
    
    # Check if rankings are consistent
    inconsistencies = []
    for symbol1 in common_symbols:
        for symbol2 in common_symbols:
            if symbol1 >= symbol2:
                continue
            
            # Get scores
            score1 = global_score_store.get_score(symbol1)['blend_score']
            score2 = global_score_store.get_score(symbol2)['blend_score']
            
            # Check all universes where both appear
            for universe_name, picks in results.items():
                symbols_in_picks = [p['symbol'] for p in picks]
                
                if symbol1 in symbols_in_picks and symbol2 in symbols_in_picks:
                    rank1 = next((p['rank'] for p in picks if p['symbol'] == symbol1), None)
                    rank2 = next((p['rank'] for p in picks if p['symbol'] == symbol2), None)
                    
                    # If score1 > score2, then rank1 should be < rank2 (lower rank = better)
                    if score1 > score2 and rank1 > rank2:
                        inconsistencies.append(f"{universe_name}: {symbol1} (score {score1:.1f}, rank {rank1}) ranked BELOW {symbol2} (score {score2:.1f}, rank {rank2})")
                    elif score1 < score2 and rank1 < rank2:
                        inconsistencies.append(f"{universe_name}: {symbol1} (score {score1:.1f}, rank {rank1}) ranked ABOVE {symbol2} (score {score2:.1f}, rank {rank2})")
    
    if inconsistencies:
        print(f"[Consistency Check] ⚠️  WARNING: {len(inconsistencies)} inconsistencies found!")
        for issue in inconsistencies[:5]:  # Show first 5
            print(f"  - {issue}")
    else:
        print(f"[Consistency Check] ✅ All rankings consistent across universes")
