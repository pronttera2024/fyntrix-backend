"""
Analytics API Router
====================

Endpoints for tracking and reporting on picks system performance
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Dict, Any, List
from datetime import datetime, date, timedelta
from pydantic import BaseModel
import json
import sqlite3
from ..services.picks_analytics import picks_analytics
from ..services import event_logger
from ..services.top_picks_store import get_top_picks_store
from ..services.pick_logger import get_active_rl_policy, _DB_PATH

router = APIRouter(prefix="/v1/analytics", tags=["analytics"])


def _parse_strategy_exits_date(date: Optional[str]) -> datetime:
    if date is None:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(date)
    except Exception:
        try:
            return datetime.strptime(date, "%Y%m%d")
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Invalid date format. Use YYYY-MM-DD or YYYYMMDD.",
            )


@router.get("/picks-stats")
async def get_picks_stats(days: int = Query(7, ge=1, le=90)):
    """
    Get picks generation statistics
    
    Args:
        days: Number of days to analyze (1-90)
    
    Returns:
        Statistics about fewer-than-requested picks frequency
    """
    try:
        stats = picks_analytics.get_fewer_picks_frequency(days=days)
        return {
            **stats,
            "generated_at": datetime.now().isoformat() + "Z"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get picks stats: {str(e)}")


@router.get("/conversion-rate")
async def get_conversion_rate(days: int = Query(7, ge=1, le=90)):
    """
    Get conversion rate metrics
    
    Args:
        days: Number of days to analyze (1-90)
    
    Returns:
        Conversion metrics (picks shown → user actions)
    """
    try:
        metrics = picks_analytics.get_conversion_rate(days=days)
        return {
            **metrics,
            "generated_at": datetime.now().isoformat() + "Z"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get conversion rate: {str(e)}")


@router.get("/daily-stats")
async def get_daily_stats(date: Optional[str] = None):
    """
    Get daily statistics
    
    Args:
        date: Date in YYYY-MM-DD format (default: today)
    
    Returns:
        Daily statistics
    """
    try:
        stats = picks_analytics.get_daily_stats(date=date)
        return {
            "date": date or datetime.now().strftime('%Y-%m-%d'),
            "stats": stats,
            "generated_at": datetime.now().isoformat() + "Z"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get daily stats: {str(e)}")


@router.post("/interaction")
async def log_interaction(
    symbol: str,
    action: str,
    universe: str,
    recommendation: str,
    score: float,
    session_id: Optional[str] = None
):
    """
    Log user interaction with a pick
    
    Args:
        symbol: Stock symbol
        action: Action type (view_chart, analyze, feedback)
        universe: Universe name
        recommendation: Recommendation shown
        score: Blend score
        session_id: Optional session ID
    
    Returns:
        Confirmation
    """
    try:
        picks_analytics.log_pick_interaction(
            symbol=symbol,
            action=action,
            universe=universe,
            recommendation=recommendation,
            score=score,
            session_id=session_id
        )
        return {
            "status": "logged",
            "symbol": symbol,
            "action": action,
            "timestamp": datetime.now().isoformat() + "Z"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to log interaction: {str(e)}")


@router.post("/feedback")
async def log_feedback(
    symbol: str,
    feedback_type: str,
    rating: Optional[int] = None,
    comment: Optional[str] = None,
    recommendation: Optional[str] = None,
    session_id: Optional[str] = None
):
    """
    Log user feedback on a pick
    
    Args:
        symbol: Stock symbol
        feedback_type: Type of feedback (helpful, not_helpful, trade_executed)
        rating: Rating 1-5
        comment: User comment
        recommendation: Recommendation shown
        session_id: Optional session ID
    
    Returns:
        Confirmation
    """
    try:
        picks_analytics.log_user_feedback(
            symbol=symbol,
            feedback_type=feedback_type,
            rating=rating,
            comment=comment,
            recommendation=recommendation,
            session_id=session_id
        )
        return {
            "status": "feedback_received",
            "symbol": symbol,
            "feedback_type": feedback_type,
            "timestamp": datetime.now().isoformat() + "Z"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to log feedback: {str(e)}")


@router.get("/dashboard")
async def get_analytics_dashboard(days: int = Query(7, ge=1, le=90)):
    """
    Get comprehensive analytics dashboard
    
    Args:
        days: Number of days to analyze
    
    Returns:
        Combined dashboard with all metrics
    """
    try:
        picks_stats = picks_analytics.get_fewer_picks_frequency(days=days)
        conversion = picks_analytics.get_conversion_rate(days=days)
        
        return {
            "period_days": days,
            "picks_stats": picks_stats,
            "conversion_metrics": conversion,
            "generated_at": datetime.now().isoformat() + "Z"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get dashboard: {str(e)}")


def _parse_ymd_or_none(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format for start_date/end_date. Use YYYY-MM-DD.",
        )


def _get_daily_rl_metrics(
    *,
    mode: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
) -> List[Dict[str, Any]]:
    today = datetime.utcnow().date()

    start_dt = _parse_ymd_or_none(start_date)
    end_dt = _parse_ymd_or_none(end_date)

    if end_dt is None:
        end_dt = today
    if start_dt is None:
        start_dt = end_dt - timedelta(days=6)

    if start_dt > end_dt:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    mode_filter = (mode or "").strip() or None

    rows: List[Dict[str, Any]] = []
    conn = None
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        cursor = conn.cursor()

        sql = """
            SELECT
                e.trade_date,
                e.mode,
                COUNT(*) AS trades,
                AVG(o.ret_close_pct) AS avg_ret_close_pct,
                AVG(o.max_drawdown_pct) AS avg_max_drawdown_pct,
                AVG(CASE WHEN o.ret_close_pct IS NOT NULL AND o.ret_close_pct > 0 THEN 1.0 ELSE 0.0 END) AS win_rate,
                AVG(CASE WHEN o.hit_target = 1 THEN 1.0 ELSE 0.0 END) AS hit_target_rate,
                AVG(CASE WHEN o.hit_stop = 1 THEN 1.0 ELSE 0.0 END) AS hit_stop_rate
            FROM pick_events e
            JOIN pick_outcomes o
              ON e.pick_uuid = o.pick_uuid
            WHERE o.evaluation_horizon = ?
              AND e.trade_date >= ?
              AND e.trade_date <= ?
        """

        params: List[Any] = ["EOD", start_dt.isoformat(), end_dt.isoformat()]

        if mode_filter is not None:
            sql += " AND e.mode = ?"
            params.append(mode_filter)

        sql += " GROUP BY e.trade_date, e.mode ORDER BY e.trade_date DESC, e.mode ASC"

        for (
            trade_date,
            mode_val,
            trades,
            avg_ret_close_pct,
            avg_max_drawdown_pct,
            win_rate,
            hit_target_rate,
            hit_stop_rate,
        ) in cursor.execute(sql, params):
            rows.append(
                {
                    "date": trade_date,
                    "mode": mode_val,
                    "trades": int(trades or 0),
                    "avg_ret_close_pct": float(avg_ret_close_pct or 0.0),
                    "avg_max_drawdown_pct": float(avg_max_drawdown_pct or 0.0),
                    "win_rate": float((win_rate or 0.0) * 100.0),
                    "hit_target_rate": float((hit_target_rate or 0.0) * 100.0),
                    "hit_stop_rate": float((hit_stop_rate or 0.0) * 100.0),
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute daily RL metrics: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    return rows


@router.get("/rl-metrics")
async def get_rl_metrics(
    mode: Optional[str] = Query(None),
    view: Optional[str] = Query("policy"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
) -> Dict[str, Any]:
    view_normalized = (view or "policy").lower()

    if view_normalized == "daily":
        policy = get_active_rl_policy()
        daily_rows = _get_daily_rl_metrics(mode=mode, start_date=start_date, end_date=end_date)

        policy_payload: Optional[Dict[str, Any]]
        if not policy:
            policy_payload = None
        else:
            policy_payload = {
                "policy_id": policy.get("policy_id"),
                "name": policy.get("name"),
                "status": policy.get("status"),
                "created_at": policy.get("created_at"),
                "updated_at": policy.get("updated_at"),
                "activated_at": policy.get("activated_at"),
                "deactivated_at": policy.get("deactivated_at"),
            }

        return {
            "policy": policy_payload,
            "daily": daily_rows,
        }

    # Default view: policy-level RL metrics (existing behaviour)
    policy = get_active_rl_policy()
    if not policy:
        return {"policy": None, "modes": []}

    metrics = policy.get("metrics") or {}
    if not isinstance(metrics, dict) or not metrics:
        return {
            "policy": {
                "policy_id": policy.get("policy_id"),
                "name": policy.get("name"),
                "status": policy.get("status"),
                "created_at": policy.get("created_at"),
                "updated_at": policy.get("updated_at"),
                "activated_at": policy.get("activated_at"),
                "deactivated_at": policy.get("deactivated_at"),
            },
            "modes": [],
        }

    exit_profiles = metrics.get("exit_profiles") or {}
    best_exit_profiles = metrics.get("best_exit_profiles") or {}
    last_by_mode = metrics.get("last_evaluated_at_by_mode") or {}
    sample_by_mode = metrics.get("sample_by_mode") or {}
    bandit_block = metrics.get("bandit") or {}

    modes_out: List[Dict[str, Any]] = []

    for m, profiles in exit_profiles.items():
        if not isinstance(profiles, dict):
            continue
        if mode and str(m).lower() != str(mode).lower():
            continue

        best_cfg = best_exit_profiles.get(m) if isinstance(best_exit_profiles, dict) else None
        best_id = best_cfg.get("id") if isinstance(best_cfg, dict) else None

        prof_list: List[Dict[str, Any]] = []
        for pid, p in profiles.items():
            if not isinstance(p, dict):
                continue
            prof_list.append(
                {
                    "id": str(pid),
                    "trades": int(p.get("trades") or 0),
                    "avg_ret_close_pct": float(p.get("avg_ret_close_pct") or 0.0),
                    "avg_max_drawdown_pct": float(p.get("avg_max_drawdown_pct") or 0.0),
                    "win_rate": float(p.get("win_rate") or 0.0),
                    "hit_target_rate": float(p.get("hit_target_rate") or 0.0),
                    "hit_stop_rate": float(p.get("hit_stop_rate") or 0.0),
                    "avg_capture_ratio": float(p.get("avg_capture_ratio") or 0.0),
                    "score": float(p.get("score") or 0.0),
                    "is_best": pid == best_id,
                }
            )

        bandit_state = bandit_block.get(m) if isinstance(bandit_block, dict) else None
        contexts = 0
        actions = 0
        if isinstance(bandit_state, dict):
            ctxs = bandit_state.get("contexts") or {}
            if isinstance(ctxs, dict):
                contexts = len(ctxs)
                for ctx_state in ctxs.values():
                    if not isinstance(ctx_state, dict):
                        continue
                    a = ctx_state.get("actions") or {}
                    if isinstance(a, dict):
                        actions += len(a)

        modes_out.append(
            {
                "mode": m,
                "last_evaluated_at": last_by_mode.get(m),
                "sample": sample_by_mode.get(m),
                "profiles": prof_list,
                "bandit": {
                    "contexts": contexts,
                    "actions": actions,
                },
            }
        )

    return {
        "policy": {
            "policy_id": policy.get("policy_id"),
            "name": policy.get("name"),
            "status": policy.get("status"),
            "created_at": policy.get("created_at"),
            "updated_at": policy.get("updated_at"),
            "activated_at": policy.get("activated_at"),
            "deactivated_at": policy.get("deactivated_at"),
        },
        "modes": modes_out,
    }


@router.get("/top-picks-history")
async def get_top_picks_history(
    universe: Optional[str] = Query(
        None,
        description="Universe filter (e.g. nifty50, banknifty)"
    ),
    mode: Optional[str] = Query(
        None,
        description="Trading mode filter (e.g. Scalping, Intraday, Swing)"
    ),
    trigger: Optional[str] = Query(
        None,
        description="Trigger filter (preopen, hourly, scalping_cycle, manual)"
    ),
    start_utc: Optional[str] = Query(
        None,
        description="Start timestamp (ISO8601 UTC) for generated_at_utc"
    ),
    end_utc: Optional[str] = Query(
        None,
        description="End timestamp (ISO8601 UTC) for generated_at_utc"
    ),
    limit: int = Query(
        500,
        ge=1,
        le=5000,
        description="Maximum number of runs to return"
    ),
    include_payload: bool = Query(
        True,
        description="When false, omit the full engine payload for faster/lightweight responses"
    ),
) -> Dict[str, Any]:
    """Return raw Top Picks runs history for analytics/audit.

    This endpoint surfaces data directly from the SQLite-backed TopPicksStore
    so that legal, compliance, and analytics workflows can reconstruct the
    exact Top Picks runs that were generated by the platform.
    """

    try:
        store = get_top_picks_store()
        runs = store.query_runs(
            universe=universe,
            mode=mode,
            trigger=trigger,
            start_utc=start_utc,
            end_utc=end_utc,
            limit=limit,
        )

        if not include_payload:
            for r in runs:
                r.pop("payload", None)

        return {
            "runs": runs,
            "count": len(runs),
            "filters": {
                "universe": universe,
                "mode": mode,
                "trigger": trigger,
                "start_utc": start_utc,
                "end_utc": end_utc,
                "limit": limit,
            },
            "generated_at": datetime.now().isoformat() + "Z",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get top picks history: {str(e)}")


@router.get("/strategy-exits")
async def get_strategy_exits(
    date: Optional[str] = Query(
        None,
        description="Date in YYYY-MM-DD or YYYYMMDD format (default: today, UTC)",
    ),
    strategy_id: str = Query(
        "NEWS_EXIT",
        description="Filter by strategy_id (e.g. NEWS_EXIT, SR_EXIT, S1_HEIKIN_ASHI_PSAR_RSI_3M)",
    ),
) -> Dict[str, Any]:
    """Admin/debug endpoint: list strategy exits for a given date and strategy.

    Reads the JSON file produced by StrategyExitTracker for the requested
    date and filters exits by strategy_id. Useful for inspecting NEWS_EXIT
    and SR_EXIT behaviour for KPIs and debugging.
    """

    try:
        from ..services.strategy_exit_tracker import strategy_exit_tracker

        dt = _parse_strategy_exits_date(date)

        date_str = dt.strftime("%Y%m%d")
        file_path = strategy_exit_tracker.exits_dir / f"strategy_exits_{date_str}.json"

        if not file_path.exists():
            return {
                "date": dt.strftime("%Y-%m-%d"),
                "strategy_id": strategy_id,
                "count": 0,
                "exits": [],
                "note": "No strategy exits file found for this date.",
                "generated_at": datetime.utcnow().isoformat() + "Z",
            }

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        exits = [
            rec
            for rec in data.get("exits", [])
            if not strategy_id or rec.get("strategy_id") == strategy_id
        ]

        return {
            "date": data.get("date", dt.strftime("%Y-%m-%d")),
            "strategy_id": strategy_id,
            "count": len(exits),
            "exits": exits,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get strategy exits: {str(e)}")


class EventLoggerUpdate(BaseModel):
    enabled: Optional[bool] = None
    types: Optional[Dict[str, bool]] = None
    reset_types: bool = False


@router.get("/event-logger/config")
async def get_event_logger_config():
    """Return current event logger configuration (admin/debug)."""
    try:
        return {
            "enabled": event_logger.EVENT_LOG_ENABLED,
            "types": event_logger.EVENT_TYPES_ENABLED,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get event logger config: {str(e)}")


@router.post("/event-logger/config")
async def update_event_logger_config(update: EventLoggerUpdate):
    """Update event logger configuration (admin/debug)."""
    try:
        if update.enabled is not None:
            event_logger.EVENT_LOG_ENABLED = bool(update.enabled)

        if update.types is not None:
            if update.reset_types:
                event_logger.EVENT_TYPES_ENABLED.clear()
            event_logger.EVENT_TYPES_ENABLED.update(update.types)

        return {
            "enabled": event_logger.EVENT_LOG_ENABLED,
            "types": event_logger.EVENT_TYPES_ENABLED,
            "timestamp": datetime.now().isoformat() + "Z",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update event logger config: {str(e)}")
