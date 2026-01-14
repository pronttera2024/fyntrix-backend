"""Dashboard / Overview Scheduler

Periodically aggregates lightweight overview statistics for dashboards.

- Intraday overview (every 15 minutes):
  - Today's scalping exits summary (count, win rate, avg return, reasons)
- Daily performance snapshot (once per day):
  - 7-day winning strategies metrics for NIFTY50 (via PerformanceAnalytics)

Results are cached in Redis for instant access and optionally broadcast
via WebSocket to connected clients.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .redis_client import set_json
from .websocket_manager import get_websocket_manager
from .scalping_exit_tracker import scalping_exit_tracker
from .performance_analytics import performance_analytics
from .event_logger import log_event
from ..db import SessionLocal
from ..models import DashboardPerformance

logger = logging.getLogger(__name__)


class DashboardScheduler:
    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler()

    async def _save_performance_to_postgres(self, metrics: dict, result: dict) -> None:
        """Save performance snapshot to PostgreSQL in background (non-blocking)."""
        try:
            db = SessionLocal()
            try:
                snapshot = DashboardPerformance(
                    period_type="7d",
                    total_recommendations=metrics.get("total_recommendations"),
                    evaluated_count=metrics.get("evaluated_count"),
                    win_rate=metrics.get("win_rate"),
                    avg_pnl_pct=metrics.get("avg_pnl_pct"),
                    total_pnl_pct=metrics.get("total_pnl_pct"),
                    metrics_json=metrics,
                    recommendations_json=result.get("recommendations", []),
                    snapshot_at=datetime.utcnow()
                )
                db.add(snapshot)
                db.commit()
                logger.info("[DashboardScheduler] Saved performance snapshot to PostgreSQL")
            except Exception as e:
                db.rollback()
                logger.error("[DashboardScheduler] Failed to save to PostgreSQL: %s", e, exc_info=True)
            finally:
                db.close()
        except Exception as e:
            logger.error("[DashboardScheduler] PostgreSQL connection failed: %s", e, exc_info=True)

    async def _compute_intraday_overview(self) -> None:
        """Compute fast intraday overview stats and cache in Redis.

        Focuses on scalping exits, which are inexpensive to aggregate
        from local JSON logs.
        """
        try:
            today_summary = scalping_exit_tracker.get_daily_summary()
            exits = today_summary.get("exits", [])
            total_exits = today_summary.get("total_exits", len(exits))

            winning = [e for e in exits if e.get("return_pct", 0) > 0]
            losing = [e for e in exits if e.get("return_pct", 0) <= 0]

            win_rate = (len(winning) / total_exits * 100) if total_exits > 0 else 0.0
            avg_return = (
                sum(e.get("return_pct", 0) for e in exits) / total_exits
                if total_exits > 0
                else 0.0
            )

            # Exit reason breakdown
            reason_breakdown = {}
            for e in exits:
                reason = e.get("exit_reason", "UNKNOWN")
                reason_breakdown[reason] = reason_breakdown.get(reason, 0) + 1

            payload = {
                "as_of": datetime.utcnow().isoformat() + "Z",
                "date": today_summary.get("date"),
                "scalping_today": {
                    "total_exits": total_exits,
                    "winning_exits": len(winning),
                    "losing_exits": len(losing),
                    "win_rate": round(win_rate, 1),
                    "avg_return": round(avg_return, 2),
                    "avg_hold_time_mins": today_summary.get("avg_hold_time_mins", 0),
                    "exit_reason_breakdown": reason_breakdown,
                },
            }

            # Cache to Redis (short TTL, refreshed frequently)
            set_json("dashboard:overview:intraday", payload, ex=15 * 60)

            # Optionally broadcast to WebSocket clients
            try:
                ws_manager = get_websocket_manager()
                message = {
                    "type": "dashboard_update",
                    "scope": "intraday",
                    **payload,
                }
                asyncio.create_task(ws_manager.broadcast_all(message))
            except Exception as e:
                logger.warning("[DashboardScheduler] WS broadcast failed: %s", e)

            logger.info("[DashboardScheduler] Intraday overview updated")

            try:
                log_event(
                    event_type="dashboard_intraday_overview",
                    source="dashboard_scheduler",
                    payload=payload,
                )
            except Exception as e:
                logger.warning("[DashboardScheduler] Failed to log intraday overview event: %s", e, exc_info=True)

        except Exception as e:
            logger.error("[DashboardScheduler] Intraday overview failed: %s", e, exc_info=True)

    async def _compute_daily_performance(self) -> None:
        """Compute slower 7-day performance snapshot and cache in Redis.

        Uses PerformanceAnalytics, which may fetch chart data, so this is
        scheduled once per day outside peak hours.
        """
        try:
            # For now, focus on NIFTY50 universe; extend later as needed.
            result = await performance_analytics.get_winning_strategies(
                lookback_days=7,
                universe="nifty50",
            )

            payload = {
                "as_of": datetime.utcnow().isoformat() + "Z",
                "universe": result.get("universe", "nifty50"),
                "lookback_days": result.get("lookback_days", 7),
                "metrics": result.get("metrics", {}),
            }

            # HYBRID APPROACH: Write to both Redis (cache) and PostgreSQL (history)
            
            # 1. Write to Redis for fast access (synchronous, instant)
            set_json("dashboard:overview:performance:7d", payload, ex=24 * 3600)

            # 2. Write to PostgreSQL in background (async, non-blocking)
            metrics = result.get("metrics", {})
            asyncio.create_task(self._save_performance_to_postgres(metrics, result))

            # Optionally broadcast summary only (not full recommendations list)
            try:
                ws_manager = get_websocket_manager()
                message = {
                    "type": "dashboard_update",
                    "scope": "performance_7d",
                    **payload,
                }
                asyncio.create_task(ws_manager.broadcast_all(message))
            except Exception as e:
                logger.warning("[DashboardScheduler] WS performance broadcast failed: %s", e)

            logger.info("[DashboardScheduler] Daily performance overview updated")

        except Exception as e:
            logger.error("[DashboardScheduler] Daily performance computation failed: %s", e, exc_info=True)

    def start(self) -> None:
        """Start dashboard scheduler.

        - Intraday overview: every 15 minutes
        - Daily performance: once per day at 20:00 server time
        """
        try:
            # Every 15 minutes
            self.scheduler.add_job(
                self._compute_intraday_overview,
                CronTrigger(minute="*/15"),
                id="dashboard_intraday_overview",
                replace_existing=True,
            )

            # Daily at 20:00 (server local time)
            self.scheduler.add_job(
                self._compute_daily_performance,
                CronTrigger(hour="20", minute="0"),
                id="dashboard_daily_performance",
                replace_existing=True,
            )

            self.scheduler.start()
            logger.info(
                "[DashboardScheduler] Started (intraday every 15m, daily performance at 20:00)"
            )
        except Exception as e:
            logger.error("[DashboardScheduler] Failed to start: %s", e, exc_info=True)

    def stop(self) -> None:
        try:
            self.scheduler.shutdown()
            logger.info("[DashboardScheduler] Stopped")
        except Exception as e:
            logger.error("[DashboardScheduler] Failed to stop: %s", e, exc_info=True)


_scheduler: DashboardScheduler | None = None


def get_dashboard_scheduler() -> DashboardScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = DashboardScheduler()
    return _scheduler


async def start_dashboard_scheduler() -> None:
    scheduler = get_dashboard_scheduler()
    scheduler.start()


def stop_dashboard_scheduler() -> None:
    scheduler = get_dashboard_scheduler()
    scheduler.stop()
