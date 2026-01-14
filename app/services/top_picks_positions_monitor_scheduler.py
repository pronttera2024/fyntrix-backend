"""Top Picks Positions Monitor Scheduler

Periodically monitors logical positions derived from Top Picks runs for
non-scalping modes (Intraday, Swing, etc.) and raises alerts via
AutoMonitoringAgent.

This scheduler is **read-only**: it does not place or modify any
orders. It only computes health/alert information and publishes it to
Redis and WebSocket clients for dashboards.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from ..core.market_hours import now_ist, is_cash_market_open_ist
from .redis_client import set_json
from .chart_data_service import chart_data_service
from .websocket_manager import get_websocket_manager
from .top_picks_positions_service import get_top_picks_positions
from ..agents.auto_monitoring_agent import auto_monitoring_agent
from .event_logger import log_event
from .strategy_exit_tracker import strategy_exit_tracker
from ..db import SessionLocal
from ..models import TopPicksPositionSnapshot

logger = logging.getLogger(__name__)

# Scheduler instance
_scheduler_task: Optional[asyncio.Task] = None
_running: bool = False


def _is_market_open_ist() -> bool:
    """Return True if current time is within cash market hours (IST 9:15-15:30)."""
    ist_now = now_ist()
    return is_cash_market_open_ist(ist_now)


async def _run_top_picks_positions_cycle() -> None:
    """Single monitoring cycle for Top Picks-derived positions."""
    try:
        positions = get_top_picks_positions()
    except Exception as e:
        logger.error("[TopPicksPositions] Failed to load positions: %s", e, exc_info=True)
        return

    if not positions:
        payload: Dict[str, Any] = {
            "as_of": datetime.utcnow().isoformat() + "Z",
            "positions": [],
            "summary": {
                "positions": 0,
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "avg_health_score": 100.0,
            },
        }
        try:
            set_json("top_picks:monitor:positions:last", payload, ex=600)
        except Exception as e:
            logger.error("[TopPicksPositions] Failed to cache empty snapshot: %s", e, exc_info=True)
        try:
            log_event(
                event_type="top_picks_positions_cycle",
                source="top_picks_positions_monitor_scheduler",
                payload=payload["summary"],
            )
        except Exception as e:
            logger.warning("[TopPicksPositions] Failed to log empty positions summary: %s", e, exc_info=True)
        return

    logger.info("[TopPicksPositions] Monitoring %d logical positions", len(positions))

    positions_out: List[Dict[str, Any]] = []
    urgency_counts: Dict[str, int] = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    health_scores: List[float] = []

    for pos in positions:
        symbol = pos.get("symbol")
        if not symbol:
            continue

        try:
            chart = await chart_data_service.fetch_chart_data(symbol, "1M")
        except Exception as e:
            logger.error("[TopPicksPositions] Chart data fetch failed for %s: %s", symbol, e, exc_info=True)
            continue

        if not chart or not isinstance(chart, dict):
            continue

        cur = chart.get("current", {}) or {}
        price = cur.get("price")
        try:
            current_price = float(price) if price is not None else 0.0
        except Exception:
            current_price = 0.0

        if current_price <= 0:
            continue

        entry_price = float(pos.get("entry_price") or 0.0)
        direction = pos.get("direction") or "LONG"

        # Basic P&L
        return_pct = 0.0
        if entry_price > 0:
            sign = 1.0 if direction == "LONG" else -1.0
            try:
                return_pct = ((current_price - entry_price) / entry_price) * 100.0 * sign
            except ZeroDivisionError:
                return_pct = 0.0

        stop_loss = pos.get("stop_loss")
        target = pos.get("target")

        alerts: List[Dict[str, Any]] = []
        health_score = 100.0
        urgency = "LOW"

        position_ctx: Dict[str, Any] = {
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "target": target,
            "quantity": 1,
            "direction": direction,
        }

        if pos.get("exit_strategy"):
            position_ctx["exit_strategy"] = pos.get("exit_strategy")

        # Invoke AutoMonitoringAgent in read-only mode to generate alerts
        try:
            monitoring_result = await auto_monitoring_agent.analyze(
                symbol=symbol,
                context={
                    "source": "top_picks_positions",
                    "position": position_ctx,
                    "current_price": current_price,
                },
            )

            meta = getattr(monitoring_result, "metadata", {}) or {}
            alerts = meta.get("alerts", [])
            try:
                health_score = float(meta.get("health_score", health_score))
            except Exception:
                pass
            urgency = meta.get("urgency_level", urgency) or urgency
        except Exception as e:
            logger.error("[TopPicksPositions] AutoMonitoringAgent failed for %s: %s", symbol, e, exc_info=True)

        if alerts:
            try:
                for alert in alerts:
                    alert_type = alert.get("type") or ""
                    if (
                        alert_type
                        in {
                            "S1_STRATEGY_ADVISORY",
                            "S2_STRATEGY_ADVISORY",
                            "S3_STRATEGY_ADVISORY",
                            "SR_STRATEGY_ADVISORY",
                            "NEWS_STRATEGY_ADVISORY",
                        }
                        and alert.get("enforcement") == "ADVISORY_ONLY"
                        and alert.get("recommended_exit_price") is not None
                    ):
                        strategy_exit_tracker.log_advisory(
                            alert,
                            {
                                "symbol": symbol,
                                "universe": pos.get("universe"),
                                "mode": pos.get("mode"),
                                "direction": direction,
                                "entry_price": entry_price,
                                "source": pos.get("source"),
                            },
                        )
            except Exception as e:
                logger.error(
                    "[TopPicksPositions] Strategy exit logging failed for %s: %s",
                    symbol,
                    e,
                    exc_info=True,
                )

        urgency_counts[urgency] = urgency_counts.get(urgency, 0) + 1
        health_scores.append(health_score)

        positions_out.append(
            {
                **pos,
                "current_price": round(current_price, 2),
                "return_pct": round(return_pct, 2),
                "health_score": round(health_score, 1),
                "urgency": urgency,
                "alerts": alerts[:5],
            }
        )

    avg_health = sum(health_scores) / len(health_scores) if health_scores else 100.0

    payload = {
        "as_of": datetime.utcnow().isoformat() + "Z",
        "positions": positions_out,
        "summary": {
            "positions": len(positions_out),
            "critical": urgency_counts.get("CRITICAL", 0),
            "high": urgency_counts.get("HIGH", 0),
            "medium": urgency_counts.get("MEDIUM", 0),
            "low": urgency_counts.get("LOW", 0),
            "avg_health_score": round(avg_health, 1),
        },
    }

    # HYBRID APPROACH: Write to both Redis (cache) and PostgreSQL (history)
    
    # 1. Write to Redis for fast access
    try:
        set_json("top_picks:monitor:positions:last", payload, ex=600)
        logger.info("[TopPicksPositions] Cached positions snapshot (%d positions)", len(positions_out))
    except Exception as e:
        logger.error("[TopPicksPositions] Failed to cache positions snapshot: %s", e, exc_info=True)

    # 2. Write to PostgreSQL for historical tracking
    try:
        db = SessionLocal()
        try:
            summary = payload.get("summary", {})
            # Extract universe and mode from positions if available
            universe = "mixed"
            mode = "mixed"
            if positions_out:
                first_pos = positions_out[0]
                universe = first_pos.get("universe", "mixed")
                mode = first_pos.get("mode", "mixed")
            
            # Calculate win/loss counts
            win_count = sum(1 for p in positions_out if p.get("return_pct", 0) > 0)
            loss_count = sum(1 for p in positions_out if p.get("return_pct", 0) <= 0)
            total_pnl = sum(p.get("return_pct", 0) for p in positions_out)
            
            snapshot = TopPicksPositionSnapshot(
                universe=universe,
                mode=mode,
                total_positions=summary.get("positions"),
                active_positions=summary.get("positions"),
                total_pnl=total_pnl,
                total_pnl_pct=total_pnl / len(positions_out) if positions_out else 0,
                win_count=win_count,
                loss_count=loss_count,
                positions_json=positions_out,
                metadata_json=summary,
                snapshot_at=datetime.utcnow()
            )
            db.add(snapshot)
            db.commit()
            logger.info("[TopPicksPositions] Saved positions snapshot to PostgreSQL")
        except Exception as e:
            db.rollback()
            logger.error("[TopPicksPositions] Failed to save to PostgreSQL: %s", e, exc_info=True)
        finally:
            db.close()
    except Exception as e:
        logger.error("[TopPicksPositions] PostgreSQL connection failed: %s", e, exc_info=True)

    # Optional WebSocket broadcast for live dashboards
    try:
        ws_manager = get_websocket_manager()
        message = {
            "type": "top_picks_positions_update",
            **payload,
        }
        asyncio.create_task(ws_manager.broadcast_all(message))
        logger.info("[TopPicksPositions] Broadcast top_picks_positions_update to WebSocket clients")
    except Exception as e:
        logger.error("[TopPicksPositions] Failed to broadcast positions update: %s", e, exc_info=True)

    try:
        log_event(
            event_type="top_picks_positions_cycle",
            source="top_picks_positions_monitor_scheduler",
            payload=payload["summary"],
        )
    except Exception as e:
        logger.warning("[TopPicksPositions] Failed to log positions summary: %s", e, exc_info=True)


async def top_picks_positions_monitor_loop() -> None:
    """Main loop: monitor Top Picks positions every 5 minutes during market hours."""
    global _running

    logger.info("[TopPicksPositions] Starting Top Picks positions monitor scheduler")

    while _running:
        try:
            if _is_market_open_ist():
                logger.info("[TopPicksPositions] Market open - running monitor cycle")
                await _run_top_picks_positions_cycle()
            else:
                ist_now = now_ist()
                logger.debug(
                    "[TopPicksPositions] Market closed (IST %02d:%02d), skipping monitor",
                    ist_now.hour,
                    ist_now.minute,
                )

            await asyncio.sleep(300)  # 5 minutes
        except asyncio.CancelledError:
            logger.info("[TopPicksPositions] Scheduler cancelled")
            break
        except Exception as e:
            logger.error("[TopPicksPositions] Unexpected error: %s", e, exc_info=True)
            await asyncio.sleep(60)


async def start_top_picks_positions_monitor() -> None:
    """Start the Top Picks positions monitor scheduler (called on app startup)."""
    global _scheduler_task, _running

    if _running:
        logger.warning("[TopPicksPositions] Scheduler already running")
        return

    _running = True
    _scheduler_task = asyncio.create_task(top_picks_positions_monitor_loop())
    logger.info("[TopPicksPositions] Scheduler started - monitoring every 5 minutes")


def stop_top_picks_positions_monitor() -> None:
    """Stop the Top Picks positions monitor scheduler (called on app shutdown)."""
    global _scheduler_task, _running

    if not _running:
        return

    _running = False

    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        logger.info("[TopPicksPositions] Scheduler stopped")
