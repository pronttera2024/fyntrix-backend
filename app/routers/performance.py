"""
Performance Analytics Router
Endpoints for tracking AI recommendations performance
"""

from fastapi import APIRouter, Query
from typing import Dict, Any
from datetime import datetime

from ..services.performance_analytics import performance_analytics
from ..services.ai_recommendation_store import get_ai_recommendation_store
from ..services.policy_learner import generate_candidate_policy


router = APIRouter(prefix="/v1/performance", tags=["performance"])


@router.get("/winning-strategies")
async def get_winning_strategies(
    lookback_days: int = Query(7, ge=1, le=30, description="Days to look back"),
    universe: str = Query("nifty50", description="Stock universe (nifty50, banknifty)")
) -> Dict[str, Any]:
    """[Deprecated alias] Get performance analytics for AI recommendations.

    Prefer calling /v1/performance/winning-trades from new clients. This
    endpoint remains for backward compatibility.
    """
    return await performance_analytics.get_winning_strategies(
        lookback_days=lookback_days,
        universe=universe,
    )


@router.get("/winning-trades")
async def get_winning_trades(
    lookback_days: int = Query(7, ge=1, le=30, description="Days to look back"),
    universe: str = Query("nifty50", description="Stock universe (nifty50, banknifty)"),
) -> Dict[str, Any]:
    """Get performance analytics for AI recommendations (Winning Trades).

    Returns:
    - Win rate (% of profitable recommendations)
    - Average return per recommendation
    - Alpha generated vs benchmark
    - Total picks analyzed
    - Recent recommendations with status (TARGET HIT, ACTIVE, STOP LOSS)
    """
    return await performance_analytics.get_winning_trades(
        lookback_days=lookback_days,
        universe=universe,
    )


@router.get("/alpha/evaluate")
async def evaluate_ai_alpha(
    max_rows: int = Query(500, ge=1, le=2000, description="Max unevaluated recommendations to process in this call"),
) -> Dict[str, Any]:
    """Trigger evaluation of logged AI recommendations and return a summary.

    This endpoint uses config-driven horizons and the ai_recommendations table to
    compute realized P&L/alpha for recommendations whose outcomes are now
    observable (e.g. scalping exits logged in scalping_exit_tracker).
    """

    result = await performance_analytics.evaluate_ai_recommendations(max_rows=max_rows)
    return {
        **result,
        "max_rows": max_rows,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


@router.get("/alpha/dataset")
async def get_alpha_dataset(
    mode: str | None = Query(None, description="Filter by trading mode (Scalping, Intraday, Swing, Options, Futures)"),
    symbol: str | None = Query(None, description="Filter by symbol (e.g. RELIANCE)"),
    evaluated_only: bool = Query(True, description="Only include rows with realized P&L"),
    limit: int = Query(100, ge=1, le=500, description="Maximum rows to return"),
    offset: int = Query(0, ge=0, description="Offset for paging through the dataset"),
) -> Dict[str, Any]:
    """Page through the AI recommendations dataset (inputs + outcomes).

    This surfaces rows from the ai_recommendations table so that we can inspect
    what the agents actually recommended and how those trades performed.
    """

    store = get_ai_recommendation_store()
    items = store.fetch_dataset(
        mode=mode,
        symbol=symbol,
        evaluated_only=evaluated_only,
        limit=limit,
        offset=offset,
    )

    return {
        "items": items,
        "count": len(items),
        "filters": {
            "mode": mode,
            "symbol": symbol,
            "evaluated_only": evaluated_only,
        },
        "pagination": {
            "limit": limit,
            "offset": offset,
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


@router.get("/alpha/by-mode")
async def get_alpha_by_mode(
    lookback_days: int = Query(30, ge=1, le=365, description="Days of evaluated recommendations to include in mode-level ALPHA metrics"),
) -> Dict[str, Any]:
    """Return ALPHA / P&L metrics aggregated by trading mode over a lookback window."""

    result = await performance_analytics.get_alpha_by_mode(lookback_days=lookback_days)
    return {
        **result,
        "lookback_days": lookback_days,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


@router.post("/policy/candidate")
async def create_policy_candidate() -> Dict[str, Any]:
    """Generate a candidate mode_weights policy config for review.

    This runs the offline PolicyLearner over evaluated ai_recommendations,
    bumps the version, attaches a performance snapshot, writes a candidate
    mode_weights JSON file alongside the live config, and returns the
    candidate dict for inspection.
    """

    candidate = generate_candidate_policy()
    return {
        "candidate": candidate,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
