"""
Scalping Monitor Scheduler Service

Runs auto-monitoring every 5 minutes during market hours.
Detects exits and logs them automatically.

Features:
- 5-minute interval monitoring
- Market hours check (9:15 AM - 3:30 PM IST)
- Automatic exit detection
- Graceful error handling
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from ..core.market_hours import now_ist, is_cash_market_open_ist, is_eod_window_ist
from .redis_client import set_json, get_json
from .event_logger import log_event

logger = logging.getLogger(__name__)

# Scheduler instance
_scheduler_task: Optional[asyncio.Task] = None
_running = False


async def scalping_monitor_loop():
    """
    Main monitoring loop - runs every 5 minutes during market hours.
    """
    global _running
    
    logger.info("[ScalpingScheduler] Starting scalping monitor scheduler")
    
    while _running:
        try:
            # Check if market is open (India cash market hours)
            ist_now = now_ist()
            # Regular market hours: 9:15 AM to 3:30 PM IST
            market_open = is_cash_market_open_ist(ist_now)

            # Short EOD window just after close (15:30-15:45) to allow EOD_AUTO_EXIT processing
            eod_window = is_eod_window_ist(ist_now)

            if market_open or eod_window:
                logger.info("[ScalpingScheduler] %s - running scalping monitor", "Market open" if market_open else "EOD window")
                
                try:
                    # Import here to avoid circular dependencies
                    from ..agents.auto_monitoring_agent import auto_monitoring_agent
                    
                    result = await auto_monitoring_agent.monitor_scalping_positions(manual_trigger=False)

                    # Attach latest scalping Top Picks metadata for supported universes
                    try:
                        universes = ["nifty50", "banknifty", "nifty100", "nifty500"]
                        meta_list = []
                        for u in universes:
                            top_picks_key = f"top_picks:{u}:scalping"
                            tp = get_json(top_picks_key)
                            if isinstance(tp, dict):
                                meta_list.append({
                                    "universe": tp.get("universe", u),
                                    "mode": tp.get("mode", "Scalping"),
                                    "as_of": tp.get("as_of") or tp.get("generated_at"),
                                    "run_id": tp.get("run_id"),
                                    "source_key": top_picks_key,
                                })
                        if meta_list:
                            result["scalping_top_picks_meta"] = meta_list
                    except Exception as e:
                        logger.warning("[ScalpingScheduler] Failed to attach scalping top picks metadata: %s", e, exc_info=True)
                    
                    logger.info(
                        f"[ScalpingScheduler] Monitoring complete: "
                        f"{result['active_positions']} active, "
                        f"{result['exits_detected']} exits detected"
                    )

                    try:
                        log_event(
                            event_type="scalping_monitor_cycle",
                            source="scalping_monitor_scheduler",
                            payload={
                                "active_positions": result.get("active_positions"),
                                "exits_detected": result.get("exits_detected"),
                                "timestamp": result.get("timestamp"),
                            },
                        )
                    except Exception as e:
                        logger.warning("[ScalpingScheduler] Failed to log scalping monitor summary: %s", e, exc_info=True)
                    
                    # Log individual exits
                    for exit in result.get('exits', []):
                        logger.info(
                            f"[ScalpingScheduler] EXIT: {exit['symbol']} - "
                            f"{exit['exit_reason']} @ {exit['exit_price']}, "
                            f"return: {exit['return_pct']:.2f}%"
                        )

                        try:
                            log_event(
                                event_type="scalping_exit",
                                source="scalping_monitor_scheduler",
                                payload=exit,
                            )
                        except Exception as e:
                            logger.warning("[ScalpingScheduler] Failed to log scalping exit event: %s", e, exc_info=True)

                    # Broadcast scalping monitor summary to WebSocket clients (non-blocking)
                    try:
                        from .websocket_manager import get_websocket_manager

                        ws_manager = get_websocket_manager()
                        message = {
                            "type": "scalping_monitor_update",
                            **result,
                        }
                        asyncio.create_task(ws_manager.broadcast_all(message))
                        logger.info("[ScalpingScheduler] Broadcast scalping_monitor_update to WebSocket clients")
                    except Exception as e:
                        logger.error(f"[ScalpingScheduler] Failed to broadcast scalping monitor update: {e}", exc_info=True)

                    # Cache latest summary in Redis (optional)
                    try:
                        set_json("scalping:monitor:last", result, ex=600)
                    except Exception as e:
                        logger.error(f"[ScalpingScheduler] Failed to cache scalping monitor result to Redis: {e}", exc_info=True)
                    
                except Exception as e:
                    logger.error(f"[ScalpingScheduler] Monitoring error: {e}", exc_info=True)
            else:
                logger.debug(
                    "[ScalpingScheduler] Market closed (IST %02d:%02d), skipping monitoring",
                    ist_now.hour,
                    ist_now.minute,
                )
            
            # Wait 5 minutes before next check
            await asyncio.sleep(300)  # 300 seconds = 5 minutes
            
        except asyncio.CancelledError:
            logger.info("[ScalpingScheduler] Scheduler cancelled")
            break
        except Exception as e:
            logger.error(f"[ScalpingScheduler] Unexpected error: {e}", exc_info=True)
            # Wait before retry
            await asyncio.sleep(60)


async def start_scalping_monitor():
    """
    Start the scalping monitor scheduler.
    Called on app startup.
    """
    global _scheduler_task, _running
    
    if _running:
        logger.warning("[ScalpingScheduler] Already running")
        return
    
    _running = True
    _scheduler_task = asyncio.create_task(scalping_monitor_loop())
    logger.info("[ScalpingScheduler] Scheduler started - monitoring every 5 minutes")


def stop_scalping_monitor():
    """
    Stop the scalping monitor scheduler.
    Called on app shutdown.
    """
    global _scheduler_task, _running
    
    if not _running:
        return
    
    _running = False
    
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        logger.info("[ScalpingScheduler] Scheduler stopped")
