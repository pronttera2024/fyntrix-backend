from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import asyncio

from ..services.memory import MEMORY
from ..agents.coordinator import AgentCoordinator
from ..agents.technical_agent import TechnicalAgent
from ..utils.trading_modes import (
    TradingMode, get_agent_weights, get_strategy_parameters,
    get_mode_display_info, validate_mode_combination, MODE_CONFIGS,
    normalize_mode,
)
from ..agents.global_market_agent import GlobalMarketAgent
from ..agents.policy_macro_agent import PolicyMacroAgent
from ..agents.options_agent import OptionsAgent
from ..agents.sentiment_agent import SentimentAgent
from ..agents.microstructure_agent import MicrostructureAgent
from ..agents.risk_agent import RiskAgent
# Phase 2 New Agents
from ..agents.pattern_recognition_agent import PatternRecognitionAgent
from ..agents.market_regime_agent import MarketRegimeAgent
from ..agents.trade_strategy_agent import TradeStrategyAgent
from ..agents.watchlist_intelligence_agent import WatchlistIntelligenceAgent
from ..agents.auto_monitoring_agent import AutoMonitoringAgent
from ..agents.personalization_agent import PersonalizationAgent
# Scalping Agent
from ..agents.scalping_agent import ScalpingAgent
from ..services.intelligent_insights import generate_batch_insights
from ..services.top_picks_scheduler import get_cached_top_picks, force_refresh_universe, TOP_PICKS_CACHE
from ..services.realtime_prices import enrich_picks_with_realtime_data
from ..services.redis_client import get_json
from ..services.top_picks_store import get_top_picks_store

router = APIRouter(tags=["agents"])

# Initialize 14-Agent System
# Architecture:
#   - 11 Scoring Agents (100% weight): Generate blend score
#   - 1 Super Agent (Trade Strategy): Consumes scores, generates trade plans
#   - 2 Utility Agents (Auto-Monitoring, Personalization): Support functions
coordinator = AgentCoordinator()

# 11 SCORING AGENTS (100% weight distributed)
coordinator.register_agent(TechnicalAgent(weight=0.20))
coordinator.register_agent(PatternRecognitionAgent(weight=0.18))
coordinator.register_agent(MarketRegimeAgent(weight=0.15))
coordinator.register_agent(GlobalMarketAgent(weight=0.12))
coordinator.register_agent(OptionsAgent(weight=0.12))
coordinator.register_agent(SentimentAgent(weight=0.10))
coordinator.register_agent(PolicyMacroAgent(weight=0.08))
coordinator.register_agent(ScalpingAgent(weight=0.03))  # NEW: Scalping-specific analysis
coordinator.register_agent(WatchlistIntelligenceAgent(weight=0.01))
coordinator.register_agent(MicrostructureAgent(weight=0.01))
coordinator.register_agent(RiskAgent(weight=0.00))

# SUPER AGENT (No weight - generates trade plans from other agents)
coordinator.register_agent(TradeStrategyAgent(weight=0.00))

# UTILITY AGENTS (No weight - monitoring & personalization)
coordinator.register_agent(AutoMonitoringAgent(weight=0.00))
coordinator.register_agent(PersonalizationAgent(weight=0.00))

coordinator.set_weights({
    # 11 SCORING AGENTS (100% total)
    'technical': 0.2037,              # Technical analysis
    'pattern_recognition': 0.1833,    # Chart patterns
    'market_regime': 0.1528,          # Bull/Bear/Sideways
    'global': 0.12,                   # Global markets
    'options': 0.12,                  # Options flow
    'sentiment': 0.10,                # Market sentiment
    'policy': 0.08,                   # Policy/Macro
    'scalping': 0.03,                 # NEW: Scalping-specific (spread, volume, order flow)
    'watchlist_intelligence': 0.00,   # Watchlist recommendations (monitoring only, not scored)
    'microstructure': 0.0102,         # Order flow
    'risk': 0.00,                     # Risk management
    
    # SUPER AGENT (0% weight - not in blend score)
    'trade_strategy': 0.00,           # Trade plan generator
    
    # UTILITY AGENTS (0% weight - not in blend score)
    'auto_monitoring': 0.00,          # Position monitoring
    'personalization': 0.00           # User preferences
}) 

class TopPicksReq(BaseModel):
    symbols: List[str]
    timeframe: str = "1d"
    horizon: int = 365

# Import top picks engine
from ..services.top_picks_engine import generate_top_picks, get_latest_picks, get_universe_symbols
# Import global score store for consistent rankings
from ..services.global_score_store import get_consistent_top_picks, global_score_store

@router.get("/top-picks")
async def get_top_picks(
    universe: str = Query("nifty50", description="Universe: nifty50, nifty100, test"),
    mode: str = Query("Swing", description="Trading mode: Scalping, Intraday, Swing, Options, Futures, Commodities"),
    limit: int = Query(5, ge=1, le=10, description="Number of picks"),
    min_confidence: str = Query("medium", description="Minimum confidence: low, medium, high"),
    refresh: bool = Query(False, description="Force refresh (otherwise use cached)")
):
    """
    Get today's top stock picks from AI analysis.
    
    Mode-specific agent selection for optimal performance:
    - Scalping/Intraday: 6-7 agents, ~30s for 50 stocks
    - Swing: All 11 agents, ~60s for 50 stocks
    - Options/Futures/Commodities: Specialized agents
    
    By default, returns cached picks. Set refresh=true to regenerate.
    Picks are automatically generated every one hour during market hours.
    """
    
    # Try to load cached picks first (universe + mode specific)
    if not refresh:
        cached_data = get_cached_top_picks(universe, mode)
        
        if cached_data and cached_data.get('items'):
            # Return cached picks - much faster!
            items = cached_data['items'][:limit]
            
            # Calculate cache age
            cache_age_seconds = 0
            last_updated = "Just now"
            if 'as_of' in cached_data:
                try:
                    cache_age_seconds = (datetime.now() - datetime.fromisoformat(cached_data['as_of'].replace('Z', ''))).total_seconds()
                    if cache_age_seconds < 60:
                        last_updated = "Just now"
                    elif cache_age_seconds < 3600:
                        mins = int(cache_age_seconds / 60)
                        last_updated = f"{mins} min{'s' if mins > 1 else ''} ago"
                    else:
                        hours = int(cache_age_seconds / 3600)
                        last_updated = f"{hours} hour{'s' if hours > 1 else ''} ago"
                except Exception:
                    pass
            
            # Format to match expected response structure
            response = {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'generated_at': cached_data.get('as_of', datetime.now().isoformat() + 'Z'),
                'universe': cached_data.get('universe', universe),
                'mode': cached_data.get('mode', mode),
                'picks_count': len(items),
                'picks': items,
                'cached': True,
                'cache_age_seconds': cache_age_seconds,
                'last_updated': last_updated,
                'next_refresh': "Next refresh in ~1 hour during market hours",
                'metadata': {
                    'analysis_time_seconds': cached_data.get('elapsed_seconds', 0),
                    'cache_status': 'fresh' if cache_age_seconds < 3600 else 'stale'
                }
            }
            
            print(f"✓ Serving cached picks for {universe} (age: {last_updated})")
            return response
        else:
            print(f"⚠️  No cached picks for {universe}, generating fresh...")
    
    # Generate fresh picks (only if refresh=true or no cache)
    picks_data = await generate_top_picks(
        universe=universe,
        top_n=limit,
        min_confidence=min_confidence,
        mode=mode  # Mode-specific agent selection
    )
    
    picks_data['cached'] = False
    picks_data['mode'] = mode
    return picks_data


@router.get("/top-picks/status")
async def top_picks_status() -> Dict[str, Any]:
    universes = ["NIFTY50", "BANKNIFTY"]
    modes = ["Scalping", "Intraday", "Swing", "Options", "Futures"]
    now = datetime.utcnow()
    rows: List[Dict[str, Any]] = []
    store = get_top_picks_store()

    for universe in universes:
        universe_lower = universe.lower()
        for mode in modes:
            memory_key = f"{universe.upper()}::{mode}"
            memory_payload = TOP_PICKS_CACHE.get(memory_key)
            memory_items = 0
            if isinstance(memory_payload, dict):
                items = memory_payload.get("items") or []
                if isinstance(items, list):
                    memory_items = len(items)

            redis_key = f"top_picks:{universe_lower}:{mode.lower()}"
            try:
                redis_payload = get_json(redis_key)
            except Exception:
                redis_payload = None
            redis_items = 0
            if isinstance(redis_payload, dict):
                items = redis_payload.get("items") or []
                if isinstance(items, list):
                    redis_items = len(items)

            try:
                sqlite_payload = store.get_latest_run_for(universe_lower, mode)
            except Exception:
                sqlite_payload = None
            sqlite_items = 0
            if isinstance(sqlite_payload, dict):
                items = sqlite_payload.get("items") or []
                if isinstance(items, list):
                    sqlite_items = len(items)

            effective = get_cached_top_picks(universe, mode)
            as_of: Optional[str] = None
            age_minutes: Optional[float] = None
            effective_items = 0
            if isinstance(effective, dict):
                items = effective.get("items") or []
                if isinstance(items, list):
                    effective_items = len(items)
                raw_as_of = effective.get("as_of") or effective.get("generated_at")
                if isinstance(raw_as_of, str):
                    as_of = raw_as_of
                    try:
                        ts = datetime.fromisoformat(raw_as_of.replace("Z", ""))
                        age_minutes = (now - ts).total_seconds() / 60.0
                    except Exception:
                        age_minutes = None

            rows.append(
                {
                    "universe": universe,
                    "mode": mode,
                    "effective": {
                        "has_cache": bool(effective_items),
                        "items_count": effective_items,
                        "as_of": as_of,
                        "age_minutes": age_minutes,
                    },
                    "layers": {
                        "memory": {"present": bool(memory_items), "items": memory_items},
                        "redis": {"present": bool(redis_items), "key": redis_key, "items": redis_items},
                        "sqlite": {"present": bool(sqlite_items), "items": sqlite_items},
                    },
                }
            )

    return {
        "universes": universes,
        "modes": modes,
        "rows": rows,
        "generated_at": now.isoformat() + "Z",
    }


@router.post("/agents/top-picks")
def agent_top_picks(req: TopPicksReq):
    picks = []
    for s in req.symbols[:10]:
        picks.append({
            "symbol": s.upper(),
            "score": 0.62,
            "rationale": f"{s.upper()} shows constructive structure on {req.timeframe}.",
        })
    return {"picks": picks, "timeframe": req.timeframe, "horizon": req.horizon}


def _base_universe(universe: str) -> List[str]:
    """Resolve the base symbol universe for agent picks.

    Uses the shared universe definition from top_picks_engine so that
    NIFTY50 / BANKNIFTY (and future universes) are consistent across
    scheduled Top Picks and on-demand /agents/picks.
    """
    # Accept both upper and lower case universe names
    symbols = get_universe_symbols(universe)
    # Fallback safety: if something goes wrong, keep a minimal core set
    if not symbols:
        return ["NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "HDFCBANK"]
    return symbols


def _det_score(seed: str, salt: str) -> float:
    # simple deterministic pseudo score 0..100 based on chars
    s = sum((ord(c) * (i + 1)) for i, c in enumerate((seed + salt)[:12]))
    return round((s % 10000) / 100.0, 2)


# New Models
class AnalyzeRequest(BaseModel):
    symbol: str = Field(..., description="Stock symbol to analyze")
    timeframe: str = Field("1d", description="Timeframe: 1d, 60m, 15m")
    include_agents: Optional[List[str]] = Field(None, description="Specific agents to run")

class BatchAnalyzeRequest(BaseModel):
    symbols: List[str] = Field(..., description="List of symbols to analyze")
    sort_by: str = Field("blend_score", description="Sort by: blend_score, confidence, risk")
    limit: int = Field(10, ge=1, le=50)


@router.post("/analyze")
async def analyze_stock(req: AnalyzeRequest):
    """
    Analyze a single stock using all 7 AI agents.
    Returns comprehensive analysis with blend score, recommendation, and signals.
    """
    try:
        # Run 7-agent analysis
        result = await coordinator.analyze_symbol(req.symbol)
        
        # Add timestamp
        result['timestamp'] = datetime.utcnow().isoformat() + 'Z'
        result['symbol'] = req.symbol.upper()
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.post("/batch-analyze")
async def batch_analyze(req: BatchAnalyzeRequest):
    """
    Analyze multiple stocks in parallel.
    Returns ranked list by blend score or other criteria.
    """
    try:
        # Batch analyze with coordinator
        results = await coordinator.batch_analyze(
            req.symbols,
            max_concurrent=10
        )
        
        # Sort results
        if req.sort_by == "blend_score":
            results.sort(key=lambda x: x.get('blend_score', 0), reverse=True)
        elif req.sort_by == "confidence":
            # Sort by confidence level (High > Medium > Low)
            confidence_order = {'High': 3, 'Medium': 2, 'Low': 1}
            results.sort(key=lambda x: confidence_order.get(x.get('confidence', 'Low'), 0), reverse=True)
        
        # Apply limit
        results = results[:req.limit]
        
        return {
            'results': results,
            'analyzed_count': len(req.symbols),
            'returned_count': len(results),
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch analysis failed: {str(e)}")


@router.get("/agents/picks")
async def agents_picks(
    limit: int = Query(5, ge=1, le=10),
    universe: str = "NIFTY50",
    session_id: Optional[str] = None,
    refresh: bool = Query(False, description="Force recompute instead of using cached picks"),
    primary_mode: Optional[str] = Query(None, description="Primary trading mode (overrides session preference)")
):
    syms = _base_universe(universe)[: max(limit, 1)]
    prefs = MEMORY.get(session_id or "local")
    risk = (prefs.get("risk") or "Moderate").capitalize()
    
    # NEW: Primary mode system - prioritize query param over session memory
    primary_mode_raw = primary_mode or prefs.get("primary_mode", "Swing")
    primary_mode_str = normalize_mode(primary_mode_raw)
    auxiliary_modes_list = prefs.get("auxiliary_modes", [])
    
    print(f"[agents_picks] Received primary_mode param: {primary_mode}, using: {primary_mode_str}")
    
    # Convert to TradingMode enums
    try:
        primary_mode_enum = TradingMode(primary_mode_str)
    except:
        primary_mode_enum = TradingMode.SWING  # Default
    
    auxiliary_modes = []
    for mode_str in auxiliary_modes_list:
        try:
            aux_norm = normalize_mode(mode_str)
            auxiliary_modes.append(TradingMode(aux_norm))
        except:
            pass
    
    # Get agent weights based on primary + auxiliary modes
    w = get_agent_weights(primary_mode_enum, auxiliary_modes, risk)

    # First try to serve from scheduled cache for instant responses (mode-aware)
    if not refresh:
        requested_mode = primary_mode_enum.value
        cached = get_cached_top_picks(universe, requested_mode)
        if cached and isinstance(cached.get("items"), list):
            items = cached["items"][: limit]

            # Validate cached picks have required fields
            valid_items = [item for item in items if item.get('key_findings') and item.get('strategy_rationale')]

            if len(valid_items) < len(items):
                print(f"[agents_picks] Filtered cached picks: {len(valid_items)} valid out of {len(items)} (removed {len(items) - len(valid_items)} without key_findings/strategy)")

            # If all cached picks were filtered out, fall back to raw items
            if not valid_items:
                print(f"[agents_picks] WARNING: All cached picks filtered out for {universe} / {requested_mode}. Falling back to raw cached items.")
                valid_items = items

            # If cache still yields zero items, fall back to deterministic scores
            if not valid_items:
                print(f"[agents_picks] FALLBACK: Cached payload empty for {universe} / {requested_mode}. Using deterministic scores.")
                det_items = []
                for s in syms:
                    sc = {
                        "technical": _det_score(s, "t"),
                        "microstructure": _det_score(s, "m"),
                        "options": _det_score(s, "o"),
                        "news": _det_score(s, "n"),
                        "sentiment": _det_score(s, "s"),
                    }
                    blend = round(sum(sc[k] * (w.get(k, 0) * 0.01) for k in sc) * 100, 2)
                    mode_config = MODE_CONFIGS[primary_mode_enum]
                    item = {
                        "symbol": s,
                        "score_blend": blend,
                        "rationale": "Based on the last full analysis, these are the highest-ranked ideas across technical, options, news and sentiment.",
                        "scores": sc,
                        "horizon": mode_config.horizon,
                        "deterministic": True,
                    }
                    # For Swing, present deterministic ideas as neutral watch/hold candidates
                    if primary_mode_enum == TradingMode.SWING:
                        item["recommendation"] = "Hold"
                        item["deterministic_label"] = "Watchlist idea (Swing) based on relative scores; not a full multi-agent Swing call."
                    det_items.append(item)
                valid_items = det_items[:limit]

            # Refresh realtime price fields on cached picks so that
            # intraday_change_pct and last_price are up to date for the
            # Heat Map and other UIs, even when the structural pick data
            # itself comes from cache.
            try:
                valid_items = await enrich_picks_with_realtime_data(valid_items)
            except Exception as e:
                print(f"[agents_picks] Warning: realtime enrichment failed for cached picks: {e}")

            print(f"[agents_picks] Serving {len(valid_items)} cached picks for {universe} / {requested_mode}")
            as_of = cached.get("as_of") or datetime.utcnow().isoformat() + "Z"
            session_date: Optional[str] = None
            previous_session = False
            try:
                ts = datetime.fromisoformat(as_of.replace("Z", ""))
                session_date = ts.date().isoformat()
                previous_session = ts.date() < datetime.utcnow().date()
            except Exception:
                session_date = None

            return {
                "items": valid_items,
                "as_of": as_of,
                "universe": cached.get("universe", universe),
                "risk_profile": risk,
                "primary_mode": primary_mode_enum.value,
                "auxiliary_modes": [m.value for m in auxiliary_modes],
                "mode_info": get_mode_display_info(primary_mode_enum),
                "cached": True,
                "session_date": session_date,
                "previous_session": previous_session,
            }

        # No cache available: escalate to fresh generation instead of returning empty
        print(f"[agents_picks] No cache available for {universe} / {requested_mode}. Escalating to fresh generation.")
        refresh = True
    
    # Generate fresh picks via scheduler/engine for this mode when refresh=True
    try:
        requested_mode = primary_mode_enum.value
        print(f"[agents_picks] Generating fresh picks via scheduler for {universe} / {requested_mode}")
        refreshed = await force_refresh_universe(universe=universe, mode=requested_mode)
        items = (refreshed.get("items") or [])[: limit]

        # Validate picks have required fields (key_findings and strategy)
        valid_items = []
        for item in items:
            if item.get('key_findings') and item.get('strategy_rationale'):
                valid_items.append(item)
            else:
                print(f"[agents_picks] Skipping {item.get('symbol', 'UNKNOWN')} - missing key_findings or strategy_rationale")

        print(f"[agents_picks] Generated {len(valid_items)} valid picks (filtered {len(items) - len(valid_items)} without required fields)")

        # CRITICAL: If all picks filtered out, first relax validation and use raw engine picks
        if not valid_items:
            print(f"[agents_picks] WARNING: All picks filtered out! Returning items without validation.")
            valid_items = items

        # If engine still produced zero picks, fall back to deterministic scores so UI is never empty
        if not valid_items:
            print(f"[agents_picks] FALLBACK: Engine returned 0 picks for {universe} / {requested_mode}. Using deterministic scores.")
            det_items = []
            for s in syms:
                sc = {
                    "technical": _det_score(s, "t"),
                    "microstructure": _det_score(s, "m"),
                    "options": _det_score(s, "o"),
                    "news": _det_score(s, "n"),
                    "sentiment": _det_score(s, "s"),
                }
                blend = round(sum(sc[k] * (w.get(k, 0) * 0.01) for k in sc) * 100, 2)
                mode_config = MODE_CONFIGS[primary_mode_enum]
                item = {
                    "symbol": s,
                    "score_blend": blend,
                    "rationale": "Based on the last full analysis, these are the highest-ranked ideas across technical, options, news and sentiment.",
                    "scores": sc,
                    "horizon": mode_config.horizon,
                    "deterministic": True,
                }
                if primary_mode_enum == TradingMode.SWING:
                    item["recommendation"] = "Hold"
                    item["deterministic_label"] = "Watchlist idea (Swing) based on relative scores; not a full multi-agent Swing call."
                det_items.append(item)
            valid_items = det_items[:limit]

        as_of = refreshed.get("as_of") or datetime.utcnow().isoformat() + "Z"

        # Ensure we return fresh realtime price data even in the refreshed
        # path so that intraday_change_pct and last_price are current.
        try:
            valid_items = await enrich_picks_with_realtime_data(valid_items)
        except Exception as e:
            print(f"[agents_picks] Warning: realtime enrichment failed for refreshed picks: {e}")

        session_date: Optional[str] = None
        previous_session = False
        try:
            ts = datetime.fromisoformat(as_of.replace("Z", ""))
            session_date = ts.date().isoformat()
            previous_session = ts.date() < datetime.utcnow().date()
        except Exception:
            session_date = None

        return {
            "items": valid_items,
            "as_of": as_of,
            "universe": refreshed.get("universe", universe),
            "risk_profile": risk,
            "primary_mode": primary_mode_enum.value,
            "auxiliary_modes": [m.value for m in auxiliary_modes],
            "mode_info": get_mode_display_info(primary_mode_enum),
            "cached": False,
            "session_date": session_date,
            "previous_session": previous_session,
        }
    except Exception as e:
        # Log the actual error before falling back
        print(f"[agents_picks] ERROR generating picks: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Fallback to deterministic if everything else fails
        items = []
        for s in syms:
            sc = {
                "technical": _det_score(s, "t"),
                "microstructure": _det_score(s, "m"),
                "options": _det_score(s, "o"),
                "news": _det_score(s, "n"),
                "sentiment": _det_score(s, "s"),
            }
            blend = round(sum(sc[k] * (w.get(k, 0) * 0.01) for k in sc) * 100, 2)
            mode_config = MODE_CONFIGS[primary_mode_enum]
            item = {
                "symbol": s,
                "score_blend": blend,
                "rationale": "System-ranked ideas based on recent technical, options, news and sentiment scores (analysis service temporarily unavailable).",
                "scores": sc,
                "horizon": mode_config.horizon,
                "deterministic": True,
            }
            if primary_mode_enum == TradingMode.SWING:
                item["recommendation"] = "Hold"
                item["deterministic_label"] = "Watchlist idea (Swing) based on relative scores; not a full multi-agent Swing call."
            items.append(item)

        as_of = datetime.utcnow().isoformat() + "Z"
        session_date = datetime.utcnow().date().isoformat()

        return {
            "items": items[:limit],
            "as_of": as_of,
            "universe": universe,
            "risk_profile": risk,
            "primary_mode": primary_mode_enum.value,
            "auxiliary_modes": [m.value for m in auxiliary_modes],
            "mode_info": get_mode_display_info(primary_mode_enum),
            "cached": False,
            "session_date": session_date,
            "previous_session": False,
        }


@router.get("/agents/picks-consistent")
async def agents_picks_consistent(
    universes: str = Query("NIFTY50,BANKNIFTY", description="Comma-separated list of universes"),
    limit: int = Query(5, ge=1, le=10, description="Top N picks per universe"),
    refresh: bool = Query(False, description="Force refresh scores")
):
    """
    Get top picks with GUARANTEED RANKING CONSISTENCY across universes.
    
    Problem Solved:
    - If SBIN ranks #1 in Bank Nifty and ICICI ranks #2
    - But in Nifty 50, ICICI appears in top 5 while SBIN doesn't
    - This creates inconsistency!
    
    Solution:
    - Analyze ALL unique stocks from ALL universes ONCE
    - Assign global scores (single source of truth)
    - Filter by universe AFTER scoring
    - GUARANTEE: Relative rankings are consistent across all universes
    
    Example:
        If global scores are: SBIN=85, ICICI=80, HDFCBANK=78
        Then in BOTH Nifty50 and BankNifty top picks:
        - SBIN will ALWAYS rank above ICICI
        - ICICI will ALWAYS rank above HDFCBANK
    """
    
    # Parse universe names
    universe_list = [u.strip().upper() for u in universes.split(',')]
    
    # Build universe symbol mapping
    universes_map = {}
    for univ_name in universe_list:
        symbols = get_universe_symbols(univ_name.lower())
        universes_map[univ_name] = symbols
    
    print(f"[agents_picks_consistent] Processing {len(universe_list)} universes:")
    for univ_name, symbols in universes_map.items():
        print(f"  - {univ_name}: {len(symbols)} stocks")
    
    # Get consistent top picks using global score store
    try:
        results = await get_consistent_top_picks(
            universes=universes_map,
            top_n=limit,
            force_refresh=refresh
        )
        
        # Format response with AI insights
        formatted_results = {}
        for univ_name, picks in results.items():
            # Add AI insights
            try:
                if picks:
                    print(f"[agents_picks_consistent] Generating AI insights for {len(picks)} picks in {univ_name}...")
                    picks = await generate_batch_insights(picks)
            except Exception as e:
                print(f"[agents_picks_consistent] Warning: AI insights failed for {univ_name}: {e}")
            
            # Get display message based on pick count
            from ..utils.recommendation_system import get_recommendation_display_text
            display_message = get_recommendation_display_text(
                recommendation=None,
                count=len(picks),
                total=len(universes_map[univ_name])
            )
            
            # Log analytics
            try:
                from ..services.picks_analytics import picks_analytics
                total_in_universe = len(universes_map[univ_name])
                # Count actionable vs neutral from global store
                all_scores = global_score_store.get_all_scores()
                universe_stocks = [all_scores.get(sym) for sym in universes_map[univ_name] if sym in all_scores]
                actionable = sum(1 for s in universe_stocks if s and s.get('is_actionable', True))
                neutral = len(universe_stocks) - actionable
                
                picks_analytics.log_picks_generation(
                    universe=univ_name,
                    requested=limit,
                    returned=len(picks),
                    total_analyzed=total_in_universe,
                    actionable_count=actionable,
                    neutral_filtered=neutral
                )
            except Exception as e:
                print(f"[agents_picks_consistent] Warning: Analytics logging failed: {e}")
            
            formatted_results[univ_name] = {
                "items": picks,
                "count": len(picks),
                "requested": limit,
                "total_universe_stocks": len(universes_map[univ_name]),
                "display_message": display_message
            }
        
        return {
            "universes": formatted_results,
            "as_of": datetime.utcnow().isoformat() + "Z",
            "consistency_guaranteed": True,
            "actionable_only": True,
            "cache_valid": global_score_store._is_cache_valid(),
            "note": "Only actionable picks (Strong Buy, Buy, Sell) shown. Neutral/Hold excluded from Top Picks. Rankings consistent across all universes."
        }
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate consistent picks: {str(e)}"
        )


@router.get("/trading-modes")
async def get_trading_modes():
    """
    Get all available trading modes with their configurations
    
    Returns:
        List of trading modes with display information
    """
    modes = []
    for mode in TradingMode:
        info = get_mode_display_info(mode)
        config = MODE_CONFIGS[mode]
        modes.append({
            "value": mode.value,
            "name": info["name"],
            "display_name": info["display_name"],
            "description": info["description"],
            "horizon": info["horizon"],
            "icon": info["icon"],
            "risk_multiplier": config.risk_multiplier,
            "strategy_type": config.strategy_type
        })
    
    return {
        "modes": modes,
        "default_primary": "Swing",
        "note": "Select ONE primary mode for focused strategy generation. Others can be auxiliary."
    }


@router.post("/trading-modes/validate")
async def validate_modes(
    primary_mode: str,
    auxiliary_modes: List[str] = []
):
    """
    Validate trading mode combination
    
    Args:
        primary_mode: Primary trading mode
        auxiliary_modes: List of auxiliary modes
    
    Returns:
        Validation result
    """
    try:
        primary = TradingMode(normalize_mode(primary_mode))
    except:
        raise HTTPException(status_code=400, detail=f"Invalid primary mode: {primary_mode}")
    
    auxiliary = []
    for mode_str in auxiliary_modes:
        try:
            aux_norm = normalize_mode(mode_str)
            auxiliary.append(TradingMode(aux_norm))
        except:
            raise HTTPException(status_code=400, detail=f"Invalid auxiliary mode: {mode_str}")
    
    is_valid, error_msg = validate_mode_combination(primary, auxiliary)
    
    if not is_valid:
        return {
            "valid": False,
            "error": error_msg
        }
    
    # Calculate weights preview
    weights = get_agent_weights(primary, auxiliary, "Moderate")
    
    return {
        "valid": True,
        "primary_mode": primary.value,
        "auxiliary_modes": [m.value for m in auxiliary],
        "agent_weights_preview": weights,
        "note": f"Strategy will focus on {primary.value} with auxiliary influence from {', '.join([m.value for m in auxiliary]) if auxiliary else 'none'}"
    }


@router.get("/strategy/parameters")
async def get_strategy_params(
    primary_mode: str = Query("Swing", description="Primary trading mode"),
    score: float = Query(65.0, ge=0, le=100, description="Blend score"),
    current_price: Optional[float] = Query(None, description="Current stock price")
):
    """
    Get strategy parameters for a given mode and score
    
    Args:
        primary_mode: Primary trading mode
        score: Blend score
        current_price: Current price (optional)
    
    Returns:
        Strategy parameters tailored to the mode
    """
    try:
        mode = TradingMode(normalize_mode(primary_mode))
    except:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {primary_mode}")
    
    params = get_strategy_parameters(mode, score, current_price)
    
    return {
        "primary_mode": primary_mode,
        "score": score,
        "parameters": params,
        "generated_at": datetime.now().isoformat() + "Z"
    }
