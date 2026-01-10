"""
Scalping Trading API Router

Endpoints for scalping trade monitoring, exit tracking, and analytics.

Features:
- Auto-monitoring trigger (every 5 mins by scheduler)
- Manual monitoring trigger (user button)
- Active positions retrieval
- Daily statistics and summaries
- Exit history lookup
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from pathlib import Path
import logging
import json

from ..agents.auto_monitoring_agent import auto_monitoring_agent
from ..services.scalping_exit_tracker import scalping_exit_tracker
from ..services.zerodha_websocket import get_zerodha_websocket
from ..services.redis_client import get_json
from ..providers.zerodha_provider import get_zerodha_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/scalping", tags=["scalping"])


@router.post("/monitor")
async def trigger_scalping_monitor(manual: bool = Query(False, description="Manual trigger by user")):
    """
    Trigger scalping position monitoring.
    
    Checks all active scalping positions and detects exits based on:
    - Target hit
    - Stop loss hit
    - Time-based exit (60 min max)
    - Trailing stop
    - EOD auto-exit
    
    Args:
        manual: If True, manually triggered by user. If False, auto-triggered by scheduler.
        
    Returns:
        Summary with active positions count and exits detected
    """
    try:
        logger.info(f"[ScalpingAPI] Monitor triggered ({'manual' if manual else 'auto'})")
        
        result = await auto_monitoring_agent.monitor_scalping_positions(manual_trigger=manual)
        
        logger.info(f"[ScalpingAPI] Monitor complete: {result['active_positions']} active, {result['exits_detected']} exits")
        
        return {
            "status": "success",
            "trigger_type": "manual" if manual else "auto",
            "timestamp": result.get('timestamp'),
            "active_positions": result.get('active_positions', 0),
            "exits_detected": result.get('exits_detected', 0),
            "exits": result.get('exits', [])
        }
        
    except Exception as e:
        logger.error(f"[ScalpingAPI] Monitor failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Monitoring failed: {str(e)}")


@router.get("/active-positions")
async def get_active_positions(
    lookback_hours: int = Query(2, ge=1, le=24, description="Hours to look back"),
    include_recent_exits: bool = Query(
        False,
        description="If true, include recently exited scalping positions in the response",
    ),
    recent_exit_minutes: int = Query(
        60,
        ge=5,
        le=240,
        description="Lookback window (in minutes) for recently exited positions",
    ),
):
    """
    Get list of currently active scalping positions.
    
    Returns positions that have entry signals but no exit signals yet.
    
    Args:
        lookback_hours: How many hours to look back (default 2)
        include_recent_exits: Whether to include recently exited scalps in the response
        recent_exit_minutes: Window (in minutes) for what counts as a "recent" exit
        
    Returns:
        Active positions with entry details and exit strategies. When
        include_recent_exits=True, also includes a "recent_exits" list so the
        monitor view can show both open and very recent scalps.
    """
    try:
        logger.info(
            "[ScalpingAPI] Fetching active positions (lookback: %sh, include_recent_exits=%s, recent_exit_minutes=%s)",
            lookback_hours,
            include_recent_exits,
            recent_exit_minutes,
        )

        # Base active positions from tracker
        positions = scalping_exit_tracker.get_active_positions(lookback_hours=lookback_hours)

        # Prepare optional Zerodha quote fallback for symbols where we don't
        # have a live tick in the WebSocket cache.
        symbols_for_quotes = sorted(
            {
                str(p.get("symbol")).upper()
                for p in positions
                if p.get("symbol")
            }
        )
        quotes: Dict[str, Any] = {}
        if symbols_for_quotes:
            try:
                provider = get_zerodha_provider()
                if provider.is_authenticated():
                    quotes = provider.get_quote(symbols_for_quotes, exchange="NSE")
                else:
                    logger.info(
                        "[ScalpingAPI] Zerodha provider not authenticated; skipping quote fallback"
                    )
            except Exception as e:
                logger.warning(
                    "[ScalpingAPI] Zerodha quote fallback failed for scalping positions: %s",
                    e,
                    exc_info=True,
                )
                quotes = {}

        zerodha_ws = get_zerodha_websocket()
        enriched_positions: List[Dict[str, Any]] = []

        for pos in positions:
            try:
                symbol = pos.get("symbol")
                current_price: float = 0.0
                price_source = "unknown"

                # 1) Prefer latest tick from Zerodha WebSocket cache
                tick: Optional[Dict[str, Any]] = None
                try:
                    if symbol:
                        tick = zerodha_ws.get_latest_tick(symbol)
                except Exception as e:
                    logger.warning(
                        "[ScalpingAPI] Failed to read latest tick for %s: %s",
                        symbol,
                        e,
                    )
                    tick = None

                if tick:
                    last_price = tick.get("last_price") or tick.get("last_traded_price")
                    if isinstance(last_price, (int, float)) and last_price > 0:
                        current_price = float(last_price)
                        price_source = "tick"

                # 2) Batched Zerodha quote fallback
                if current_price <= 0 and symbol:
                    sym_key = str(symbol).upper()
                    quote = quotes.get(sym_key) or quotes.get(symbol)
                    if isinstance(quote, dict):
                        quote_price = (
                            quote.get("price")
                            or quote.get("last_price")
                            or quote.get("close")
                        )
                        if isinstance(quote_price, (int, float)) and quote_price > 0:
                            current_price = float(quote_price)
                            price_source = "quote"

                # 3) Lightweight fallback to entry price
                if current_price <= 0:
                    entry_price_fallback = pos.get("entry_price") or 0.0
                    try:
                        entry_price_fallback = float(entry_price_fallback)
                    except Exception:
                        entry_price_fallback = 0.0

                    if entry_price_fallback > 0:
                        current_price = entry_price_fallback
                        price_source = "entry"

                # Calculate current return
                entry_price = pos.get("entry_price", 0)
                try:
                    entry_price_val = float(entry_price)
                except Exception:
                    entry_price_val = 0.0

                if entry_price_val > 0 and current_price > 0:
                    if pos.get("recommendation") == "Buy":
                        return_pct = ((current_price - entry_price_val) / entry_price_val) * 100.0
                    else:
                        return_pct = ((entry_price_val - current_price) / entry_price_val) * 100.0
                else:
                    return_pct = 0.0

                # Calculate time left using timezone-aware UTC datetimes
                entry_time_raw = pos.get("entry_time")
                if isinstance(entry_time_raw, str):
                    entry_time = datetime.fromisoformat(entry_time_raw.replace("Z", "+00:00"))
                else:
                    entry_time = datetime.utcnow().replace(tzinfo=timezone.utc)

                if entry_time.tzinfo is None:
                    entry_time = entry_time.replace(tzinfo=timezone.utc)
                else:
                    entry_time = entry_time.astimezone(timezone.utc)

                now = datetime.utcnow().replace(tzinfo=timezone.utc)
                elapsed_mins = (now - entry_time).total_seconds() / 60.0
                max_hold = pos.get("exit_strategy", {}).get("max_hold_mins", 60)
                try:
                    max_hold_val = float(max_hold)
                except Exception:
                    max_hold_val = 60.0
                time_left_mins = max(0.0, max_hold_val - elapsed_mins)

                # Normalise exit strategy description for clean UI
                exit_strategy = pos.get("exit_strategy") or {}
                if isinstance(exit_strategy, dict):
                    scalp_type = str(exit_strategy.get("scalp_type") or "scalp").capitalize()
                    try:
                        atr_pct = (
                            float(exit_strategy.get("atr_pct"))
                            if exit_strategy.get("atr_pct") is not None
                            else None
                        )
                    except Exception:
                        atr_pct = None
                    try:
                        target_pct = (
                            float(exit_strategy.get("target_pct"))
                            if exit_strategy.get("target_pct") is not None
                            else None
                        )
                    except Exception:
                        target_pct = None
                    try:
                        stop_pct = (
                            float(exit_strategy.get("stop_pct"))
                            if exit_strategy.get("stop_pct") is not None
                            else None
                        )
                    except Exception:
                        stop_pct = None

                    pieces = []
                    if atr_pct is not None:
                        pieces.append(f"ATR={atr_pct:.2f}%")
                    if target_pct is not None:
                        pieces.append(f"Target={target_pct:.2f}%")
                    if stop_pct is not None:
                        pieces.append(f"Stop={stop_pct:.2f}%")

                    if pieces:
                        exit_strategy["description"] = (
                            f"{scalp_type} scalp strategy: " + ", ".join(pieces)
                        )
                        pos["exit_strategy"] = exit_strategy

                enriched_positions.append(
                    {
                        **pos,
                        "current_price": round(current_price, 2) if current_price > 0 else 0.0,
                        "return_pct": round(return_pct, 2),
                        "elapsed_mins": round(elapsed_mins, 1),
                        "time_left_mins": round(time_left_mins, 1),
                        "price_source": price_source,
                        "status": "ACTIVE",
                    }
                )

            except Exception as e:
                logger.error("[ScalpingAPI] Error enriching %s: %s", pos.get("symbol"), e)
                enriched_positions.append({**pos, "status": "ERROR"})

        logger.info(
            "[ScalpingAPI] Returning %s active positions after enrichment",
            len(enriched_positions),
        )

        # Attach latest scalping Top Picks metadata for supported universes
        scalping_top_picks_meta: List[Dict[str, Any]] = []
        try:
            universes = ["nifty50", "banknifty", "nifty100", "nifty500"]
            for u in universes:
                tp = get_json(f"top_picks:{u}:scalping")
                if isinstance(tp, dict):
                    scalping_top_picks_meta.append(
                        {
                            "universe": tp.get("universe", u),
                            "mode": tp.get("mode", "Scalping"),
                            "as_of": tp.get("as_of") or tp.get("generated_at"),
                            "run_id": tp.get("run_id"),
                        }
                    )
        except Exception as e:
            logger.warning(
                "[ScalpingAPI] Failed to read scalping top picks metadata: %s",
                e,
                exc_info=True,
            )

        # Optionally include recently exited scalps to make the monitor view
        # more informative even when positions are very short-lived.
        recent_exits: List[Dict[str, Any]] = []
        if include_recent_exits:
            try:
                now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
                summary = scalping_exit_tracker.get_daily_summary()

                for exit_data in summary.get("exits", []):
                    exit_time_str = exit_data.get("exit_time")
                    if not exit_time_str:
                        continue

                    try:
                        exit_dt = datetime.fromisoformat(
                            exit_time_str.replace("Z", "+00:00")
                        )
                    except Exception:
                        continue

                    # Normalise to UTC for comparison
                    if exit_dt.tzinfo is None:
                        exit_dt = exit_dt.replace(tzinfo=timezone.utc)
                    else:
                        exit_dt = exit_dt.astimezone(timezone.utc)

                    delta = now_utc - exit_dt
                    # Skip exits from the future or outside the recent window
                    if delta.total_seconds() < 0:
                        continue
                    if delta.total_seconds() > recent_exit_minutes * 60:
                        continue

                    recent_exits.append(
                        {
                            **exit_data,
                            "time_since_exit_mins": round(
                                delta.total_seconds() / 60.0, 1
                            ),
                            "status": "RECENT_EXIT",
                        }
                    )
            except Exception as e:
                logger.warning(
                    "[ScalpingAPI] Failed to compute recent exits for monitor view: %s",
                    e,
                    exc_info=True,
                )
                recent_exits = []

        response: Dict[str, Any] = {
            "status": "success",
            "count": len(enriched_positions),
            "positions": enriched_positions,
            "scalping_top_picks_meta": scalping_top_picks_meta or None,
        }

        if include_recent_exits:
            response["recent_exits"] = recent_exits
            response["recent_exits_count"] = len(recent_exits)

        return response

    except Exception as e:
        logger.error("[ScalpingAPI] Failed to get active positions: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve positions: {str(e)}",
        )


@router.get("/daily-summary")
async def get_daily_summary(date: Optional[str] = Query(None, description="Date (YYYY-MM-DD), defaults to today")):
    """
    Get daily summary of scalping exits.
    
    Includes:
    - Total exits
    - Winning vs losing trades
    - Average return
    - Average hold time
    - Individual exit details
    
    Args:
        date: Date string (YYYY-MM-DD), defaults to today
        
    Returns:
        Summary statistics for the day
    """
    try:
        logger.info(f"[ScalpingAPI] Fetching daily summary for {date or 'today'}")
        
        summary = scalping_exit_tracker.get_daily_summary(date)
        
        logger.info(f"[ScalpingAPI] Summary: {summary['total_exits']} exits, {summary.get('avg_return', 0):.2f}% avg return")
        
        return {
            "status": "success",
            **summary
        }
        
    except Exception as e:
        logger.error(f"[ScalpingAPI] Failed to get daily summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve summary: {str(e)}")


@router.get("/exits/{symbol}")
async def get_symbol_exit(
    symbol: str,
    date: str = Query(..., description="Entry date (YYYY-MM-DD)"),
    entry_time: Optional[str] = Query(None, description="Entry time for exact match")
):
    """
    Get exit signal for a specific symbol and date.
    
    Args:
        symbol: Stock symbol
        date: Entry date (YYYY-MM-DD)
        entry_time: Optional entry time for exact matching
        
    Returns:
        Exit details if found, 404 if not exited yet
    """
    try:
        logger.info(f"[ScalpingAPI] Looking up exit for {symbol} on {date}")
        
        exit_data = scalping_exit_tracker.get_exit(symbol, date, entry_time)
        
        if exit_data:
            logger.info(f"[ScalpingAPI] Found exit: {exit_data['exit_reason']}")
            return {
                "status": "success",
                "found": True,
                "exit": exit_data
            }
        else:
            logger.info(f"[ScalpingAPI] No exit found for {symbol} on {date}")
            return {
                "status": "success",
                "found": False,
                "message": f"No exit recorded for {symbol} on {date}"
            }
        
    except Exception as e:
        logger.error(f"[ScalpingAPI] Failed to get exit: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve exit: {str(e)}")


@router.get("/stats")
async def get_scalping_stats(days: int = Query(7, ge=1, le=30, description="Number of days")):
    """
    Get scalping statistics over multiple days.
    
    Args:
        days: Number of days to analyze (1-30)
        
    Returns:
        Aggregate statistics
    """
    try:
        logger.info(f"[ScalpingAPI] Fetching stats for last {days} days")
        
        from datetime import timedelta
        
        total_exits = 0
        total_wins = 0
        total_losses = 0
        total_return = 0
        all_exits = []
        
        # Aggregate data for each day
        for i in range(days):
            date = (datetime.utcnow() - timedelta(days=i)).strftime('%Y-%m-%d')
            summary = scalping_exit_tracker.get_daily_summary(date)
            
            total_exits += summary.get('total_exits', 0)
            total_wins += summary.get('winning_exits', 0)
            total_losses += summary.get('losing_exits', 0)
            
            for exit in summary.get('exits', []):
                total_return += exit.get('return_pct', 0)
                all_exits.append(exit)
        
        # Calculate aggregates
        win_rate = (total_wins / total_exits * 100) if total_exits > 0 else 0
        avg_return = (total_return / total_exits) if total_exits > 0 else 0
        
        # Exit reason breakdown
        exit_reasons = {}
        for exit in all_exits:
            reason = exit.get('exit_reason', 'UNKNOWN')
            exit_reasons[reason] = exit_reasons.get(reason, 0) + 1
        
        logger.info(f"[ScalpingAPI] Stats: {total_exits} exits, {win_rate:.1f}% win rate")
        
        return {
            "status": "success",
            "period_days": days,
            "total_exits": total_exits,
            "winning_exits": total_wins,
            "losing_exits": total_losses,
            "win_rate": round(win_rate, 2),
            "avg_return": round(avg_return, 2),
            "exit_reason_breakdown": exit_reasons
        }
        
    except Exception as e:
        logger.error(f"[ScalpingAPI] Failed to get stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve stats: {str(e)}")


@router.get("/monitor-occupancy")
async def get_monitor_occupancy():
    """Get scalping monitor occupancy metrics for last day and last week.

    Uses scalping_monitor_cycle events written by event_logger under
    data/events/scalping_monitor_cycle/YYYY/MM/DD/events.jsonl.
    """
    try:
        now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)

        def _load_events(window_days: int) -> List[Dict[str, Any]]:
            cutoff = now_utc - timedelta(days=window_days)
            events: List[Dict[str, Any]] = []

            base_dir = (
                Path(__file__).resolve().parents[3]
                / "data"
                / "events"
                / "scalping_monitor_cycle"
            )

            for i in range(window_days + 1):
                day = now_utc - timedelta(days=i)
                day_dir = (
                    base_dir
                    / f"{day.year:04d}"
                    / f"{day.month:02d}"
                    / f"{day.day:02d}"
                )
                file_path = day_dir / "events.jsonl"
                if not file_path.exists():
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                evt = json.loads(line)
                            except Exception:
                                continue

                            ts_str = evt.get("ts")
                            if ts_str:
                                try:
                                    ts_dt = datetime.fromisoformat(
                                        ts_str.replace("Z", "+00:00")
                                    )
                                except Exception:
                                    ts_dt = None
                                if ts_dt is not None:
                                    if ts_dt.tzinfo is None:
                                        ts_dt = ts_dt.replace(tzinfo=timezone.utc)
                                    else:
                                        ts_dt = ts_dt.astimezone(timezone.utc)
                                    if ts_dt < cutoff or ts_dt > now_utc:
                                        continue

                            if evt.get("event_type") != "scalping_monitor_cycle":
                                continue

                            events.append(evt)
                except Exception as e:
                    logger.warning(
                        "[ScalpingAPI] Failed to read scalping monitor events from %s: %s",
                        file_path,
                        e,
                        exc_info=True,
                    )

            return events

        def _compute_occupancy(window_days: int) -> Dict[str, Any]:
            events = _load_events(window_days)
            total_cycles = 0
            cycles_with_positions = 0
            total_active_positions = 0.0

            for evt in events:
                payload = evt.get("payload") or {}
                active_positions = payload.get("active_positions")
                try:
                    active_val = float(active_positions)
                except Exception:
                    continue

                total_cycles += 1
                total_active_positions += active_val
                if active_val > 0:
                    cycles_with_positions += 1

            occupancy_pct = (
                (cycles_with_positions / total_cycles) * 100.0
                if total_cycles > 0
                else 0.0
            )
            avg_active_positions = (
                total_active_positions / total_cycles if total_cycles > 0 else 0.0
            )

            return {
                "window_days": window_days,
                "cycles_total": total_cycles,
                "cycles_with_positions": cycles_with_positions,
                "occupancy_pct": round(occupancy_pct, 2),
                "avg_active_positions": round(avg_active_positions, 2),
            }

        last_day_metrics = _compute_occupancy(1)
        last_week_metrics = _compute_occupancy(7)

        return {
            "status": "success",
            "as_of_utc": now_utc.isoformat().replace("+00:00", "Z"),
            "last_day": last_day_metrics,
            "last_week": last_week_metrics,
        }

    except Exception as e:
        logger.error(
            "[ScalpingAPI] Failed to compute monitor occupancy metrics: %s",
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to compute monitor occupancy metrics: {str(e)}",
        )
