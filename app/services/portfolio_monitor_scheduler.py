import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from ..core.market_hours import now_ist, is_cash_market_open_ist
from .redis_client import set_json
from .event_logger import log_event
from ..db import SessionLocal
from ..models import PortfolioSnapshot

logger = logging.getLogger(__name__)

# Scheduler instance
_portfolio_task: Optional[asyncio.Task] = None
_running = False


def _is_market_open_ist() -> bool:
    """Return True if current time is within market hours (IST 9:15-15:30)."""
    ist_now = now_ist()
    return is_cash_market_open_ist(ist_now)


def _normalize_positions(positions: Dict[str, Any], holdings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize Zerodha positions + holdings into a unified list.

    We treat Zerodha `net` positions as the primary source and add
    holdings only for symbols not already present in positions.
    """
    normalized: List[Dict[str, Any]] = []
    seen_symbols = set()

    net_positions = positions.get("net", []) if positions else []

    # Normalize net positions
    for pos in net_positions:
        try:
            symbol = pos.get("tradingsymbol") or pos.get("symbol")
            if not symbol:
                continue

            quantity = pos.get("quantity") or pos.get("net_quantity") or 0
            try:
                quantity = float(quantity)
            except Exception:
                quantity = 0.0

            if quantity == 0:
                continue

            direction = "LONG" if quantity > 0 else "SHORT"
            entry_price = pos.get("average_price") or 0
            try:
                entry_price = float(entry_price)
            except Exception:
                entry_price = 0.0

            product = pos.get("product") or ""
            if product == "MIS":
                mode = "Intraday"
            elif product == "CNC":
                mode = "Swing"
            elif product == "NRML":
                mode = "Futures/Options"
            else:
                mode = product or "Unknown"

            normalized.append(
                {
                    "symbol": symbol,
                    "quantity": abs(quantity),
                    "direction": direction,
                    "entry_price": entry_price,
                    "product": product,
                    "mode": mode,
                    "exchange": pos.get("exchange") or "NSE",
                    "instrument_token": pos.get("instrument_token"),
                    "source": "zerodha_positions",
                }
            )
            seen_symbols.add(symbol)
        except Exception as e:
            logger.error("[PortfolioScheduler] Failed to normalize position: %s", e, exc_info=True)

    # Add holdings not already covered by positions
    for h in holdings or []:
        try:
            symbol = h.get("tradingsymbol") or h.get("symbol")
            if not symbol or symbol in seen_symbols:
                continue

            quantity = h.get("quantity") or 0
            try:
                quantity = float(quantity)
            except Exception:
                quantity = 0.0

            if quantity == 0:
                continue

            entry_price = h.get("average_price") or 0
            try:
                entry_price = float(entry_price)
            except Exception:
                entry_price = 0.0

            normalized.append(
                {
                    "symbol": symbol,
                    "quantity": abs(quantity),
                    "direction": "LONG",
                    "entry_price": entry_price,
                    "product": h.get("product") or "CNC",
                    "mode": "Swing",
                    "exchange": h.get("exchange") or "NSE",
                    "instrument_token": h.get("instrument_token"),
                    "source": "zerodha_holdings",
                }
            )
        except Exception as e:
            logger.error("[PortfolioScheduler] Failed to normalize holding: %s", e, exc_info=True)

    return normalized


async def _run_portfolio_cycle() -> None:
    """Single portfolio monitoring cycle.

    - Fetch Zerodha positions + holdings
    - Enrich with live prices (ticks -> chart)
    - Run AutoMonitoringAgent per symbol
    - Cache result in Redis and broadcast via WebSocket
    """
    try:
        from ..services.zerodha_service import zerodha_service
        from ..services.zerodha_websocket import get_zerodha_websocket
        from ..services.chart_data_service import chart_data_service
        from ..agents.auto_monitoring_agent import auto_monitoring_agent
        from .websocket_manager import get_websocket_manager
    except Exception as e:
        logger.error("[PortfolioScheduler] Import error: %s", e, exc_info=True)
        return

    positions = {}
    holdings: List[Dict[str, Any]] = []
    try:
        positions = zerodha_service.get_positions()
    except Exception as e:
        logger.error("[PortfolioScheduler] Failed to fetch positions: %s", e, exc_info=True)
    try:
        holdings = zerodha_service.get_holdings()
    except Exception as e:
        logger.error("[PortfolioScheduler] Failed to fetch holdings: %s", e, exc_info=True)

    normalized = _normalize_positions(positions, holdings)

    if not normalized:
        logger.info("[PortfolioScheduler] No open positions/holdings to monitor")
        payload = {
            "as_of": datetime.utcnow().isoformat() + "Z",
            "positions": [],
            "summary": {
                "positions": 0,
                "net_exposure": 0.0,
                "gross_exposure": 0.0,
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "avg_health_score": 100.0,
            },
        }
        try:
            set_json("portfolio:monitor:positions:last", payload, ex=600)
        except Exception as e:
            logger.error("[PortfolioScheduler] Failed to cache empty portfolio: %s", e, exc_info=True)
        return

    logger.info("[PortfolioScheduler] Monitoring %d portfolio entries", len(normalized))

    zerodha_ws = get_zerodha_websocket()

    # Best-effort subscribe to all symbols so ticks are available if WS is running
    symbols = sorted({p["symbol"] for p in normalized if p.get("symbol")})
    if symbols:
        try:
            zerodha_ws.subscribe(symbols)
        except Exception as e:
            logger.warning("[PortfolioScheduler] Failed to subscribe symbols for ticks: %s", e)

    positions_out: List[Dict[str, Any]] = []
    urgency_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    health_scores: List[float] = []
    net_exposure = 0.0
    gross_exposure = 0.0

    for pos in normalized:
        symbol = pos.get("symbol")
        if not symbol:
            continue

        quantity = float(pos.get("quantity") or 0)
        if quantity <= 0:
            continue

        entry_price = float(pos.get("entry_price") or 0.0)
        direction = pos.get("direction") or "LONG"

        current_price = 0.0
        price_source = "unknown"

        # 1) Try Zerodha WS tick cache
        try:
            try:
                tick = zerodha_ws.get_latest_tick(symbol)
            except Exception:
                tick = None

            if tick:
                last_price = tick.get("last_price") or tick.get("last_traded_price")
                if isinstance(last_price, (int, float)) and last_price > 0:
                    current_price = float(last_price)
                    price_source = "tick"
        except Exception as e:
            logger.error("[PortfolioScheduler] Tick lookup failed for %s: %s", symbol, e, exc_info=True)

        # 2) Fallback to chart data service
        if current_price <= 0:
            try:
                chart = await chart_data_service.fetch_chart_data(symbol, "1M")
                if chart and isinstance(chart, dict):
                    cur = chart.get("current", {})
                    price = cur.get("price")
                    if isinstance(price, (int, float)) and price > 0:
                        current_price = float(price)
                        price_source = "chart"
            except Exception as e:
                logger.error("[PortfolioScheduler] Chart data fetch failed for %s: %s", symbol, e, exc_info=True)

        if current_price <= 0:
            logger.debug("[PortfolioScheduler] No valid price for %s, skipping", symbol)
            continue

        # Compute P&L
        return_pct = 0.0
        if entry_price > 0:
            sign = 1.0 if direction == "LONG" else -1.0
            try:
                return_pct = ((current_price - entry_price) / entry_price) * 100.0 * sign
            except ZeroDivisionError:
                return_pct = 0.0

        # Exposure
        gross_exposure += abs(current_price * quantity)
        net_exposure += current_price * quantity * (1.0 if direction == "LONG" else -1.0)

        # Run AutoMonitoringAgent
        alerts: List[Dict[str, Any]] = []
        health_score = 100.0
        urgency = "LOW"

        try:
            monitoring_result = await auto_monitoring_agent.analyze(
                symbol=symbol,
                context={
                    "source": "portfolio",
                    "position": {
                        "entry_price": entry_price,
                        "stop_loss": pos.get("stop_loss"),
                        "target": pos.get("target"),
                        "quantity": quantity,
                        "direction": direction,
                    },
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
            logger.error("[PortfolioScheduler] AutoMonitoringAgent failed for %s: %s", symbol, e, exc_info=True)

        urgency_counts[urgency] = urgency_counts.get(urgency, 0) + 1
        health_scores.append(health_score)

        positions_out.append(
            {
                **pos,
                "current_price": round(current_price, 2),
                "price_source": price_source,
                "return_pct": round(return_pct, 2),
                "health_score": round(health_score, 1),
                "urgency": urgency,
                "alerts": alerts[:5],  # top few alerts
            }
        )

    avg_health = sum(health_scores) / len(health_scores) if health_scores else 100.0

    payload = {
        "as_of": datetime.utcnow().isoformat() + "Z",
        "positions": positions_out,
        "summary": {
            "positions": len(positions_out),
            "net_exposure": round(net_exposure, 2),
            "gross_exposure": round(gross_exposure, 2),
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
        set_json("portfolio:monitor:positions:last", payload, ex=600)
        logger.info("[PortfolioScheduler] Cached portfolio snapshot (%d positions)", len(positions_out))
    except Exception as e:
        logger.error("[PortfolioScheduler] Failed to cache portfolio snapshot: %s", e, exc_info=True)

    # 2. Write to PostgreSQL for historical tracking
    try:
        db = SessionLocal()
        try:
            summary = payload.get("summary", {})
            snapshot = PortfolioSnapshot(
                snapshot_type="positions",
                total_positions=summary.get("positions"),
                total_value=summary.get("gross_exposure"),
                total_pnl=summary.get("net_exposure"),
                total_pnl_pct=None,  # Can calculate if needed
                positions_json=positions_out,
                metadata_json=summary,
                snapshot_at=datetime.utcnow()
            )
            db.add(snapshot)
            db.commit()
            logger.info("[PortfolioScheduler] Saved portfolio snapshot to PostgreSQL")
        except Exception as e:
            db.rollback()
            logger.error("[PortfolioScheduler] Failed to save to PostgreSQL: %s", e, exc_info=True)
        finally:
            db.close()
    except Exception as e:
        logger.error("[PortfolioScheduler] PostgreSQL connection failed: %s", e, exc_info=True)

    try:
        ws_manager = get_websocket_manager()
        message = {
            "type": "portfolio_monitor_update",
            "scope": "positions",
            **payload,
        }
        asyncio.create_task(ws_manager.broadcast_all(message))
        logger.info("[PortfolioScheduler] Broadcast portfolio_monitor_update to WebSocket clients")
    except Exception as e:
        logger.error("[PortfolioScheduler] Failed to broadcast portfolio update: %s", e, exc_info=True)

    try:
        log_event(
            event_type="portfolio_positions_cycle",
            source="portfolio_monitor_scheduler",
            payload=payload["summary"],
        )
    except Exception as e:
        logger.warning("[PortfolioScheduler] Failed to log portfolio positions summary: %s", e, exc_info=True)


async def _run_watchlist_cycle() -> None:
    try:
        from ..services.watchlist_service import watchlist_service
        from ..services.zerodha_websocket import get_zerodha_websocket
        from ..services.chart_data_service import chart_data_service
        from ..agents.auto_monitoring_agent import auto_monitoring_agent
        from .websocket_manager import get_websocket_manager
    except Exception as e:
        logger.error("[PortfolioScheduler] Watchlist import error: %s", e, exc_info=True)
        return

    entries = watchlist_service.get_active_entries()
    if not entries:
        payload = {
            "as_of": datetime.utcnow().isoformat() + "Z",
            "entries": [],
            "summary": {
                "entries": 0,
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "avg_health_score": 100.0,
            },
        }
        try:
            set_json("portfolio:monitor:watchlist:last", payload, ex=600)
        except Exception as e:
            logger.error("[PortfolioScheduler] Failed to cache empty watchlist: %s", e, exc_info=True)
        try:
            log_event(
                event_type="portfolio_watchlist_cycle",
                source="portfolio_monitor_scheduler",
                payload=payload["summary"],
            )
        except Exception as e:
            logger.warning("[PortfolioScheduler] Failed to log empty watchlist summary: %s", e, exc_info=True)
        return

    logger.info("[PortfolioScheduler] Monitoring %d watchlist entries", len(entries))

    zerodha_ws = get_zerodha_websocket()
    symbols = sorted({e.get("symbol") for e in entries if e.get("symbol")})
    if symbols:
        try:
            zerodha_ws.subscribe(symbols)
        except Exception as e:
            logger.warning("[PortfolioScheduler] Failed to subscribe watchlist symbols: %s", e)

    entries_out = []
    urgency_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    health_scores: list[float] = []

    for item in entries:
        symbol = item.get("symbol")
        if not symbol:
            continue

        desired_entry = item.get("desired_entry")
        try:
            desired_entry_val = float(desired_entry) if desired_entry is not None else 0.0
        except Exception:
            desired_entry_val = 0.0

        current_price = 0.0
        price_source = "unknown"

        try:
            try:
                tick = zerodha_ws.get_latest_tick(symbol)
            except Exception:
                tick = None
            if tick:
                last_price = tick.get("last_price") or tick.get("last_traded_price")
                if isinstance(last_price, (int, float)) and last_price > 0:
                    current_price = float(last_price)
                    price_source = "tick"
        except Exception as e:
            logger.error("[PortfolioScheduler] Watchlist tick lookup failed for %s: %s", symbol, e, exc_info=True)

        if current_price <= 0:
            try:
                chart = await chart_data_service.fetch_chart_data(symbol, "1M")
                if chart and isinstance(chart, dict):
                    cur = chart.get("current", {})
                    price = cur.get("price")
                    if isinstance(price, (int, float)) and price > 0:
                        current_price = float(price)
                        price_source = "chart"
            except Exception as e:
                logger.error("[PortfolioScheduler] Watchlist chart fetch failed for %s: %s", symbol, e, exc_info=True)

        if current_price <= 0:
            continue

        distance_to_entry_pct = 0.0
        if desired_entry_val > 0:
            try:
                distance_to_entry_pct = ((current_price - desired_entry_val) / desired_entry_val) * 100.0
            except ZeroDivisionError:
                distance_to_entry_pct = 0.0

        alerts = []
        health_score = 100.0
        urgency = "LOW"

        try:
            monitoring_result = await auto_monitoring_agent.analyze(
                symbol=symbol,
                context={
                    "source": "watchlist",
                    "position": {
                        "entry_price": desired_entry_val,
                        "stop_loss": item.get("stop_loss"),
                        "target": item.get("target"),
                        "quantity": 1,
                        "direction": "LONG",
                    },
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
            logger.error("[PortfolioScheduler] AutoMonitoringAgent failed for watchlist %s: %s", symbol, e, exc_info=True)

        urgency_counts[urgency] = urgency_counts.get(urgency, 0) + 1
        health_scores.append(health_score)

        entries_out.append(
            {
                **item,
                "current_price": round(current_price, 2),
                "price_source": price_source,
                "distance_to_entry_pct": round(distance_to_entry_pct, 2),
                "health_score": round(health_score, 1),
                "urgency": urgency,
                "alerts": alerts[:5],
            }
        )

    avg_health = sum(health_scores) / len(health_scores) if health_scores else 100.0

    payload = {
        "as_of": datetime.utcnow().isoformat() + "Z",
        "entries": entries_out,
        "summary": {
            "entries": len(entries_out),
            "critical": urgency_counts.get("CRITICAL", 0),
            "high": urgency_counts.get("HIGH", 0),
            "medium": urgency_counts.get("MEDIUM", 0),
            "low": urgency_counts.get("LOW", 0),
            "avg_health_score": round(avg_health, 1),
        },
    }

    try:
        set_json("portfolio:monitor:watchlist:last", payload, ex=600)
        logger.info("[PortfolioScheduler] Cached watchlist snapshot (%d entries)", len(entries_out))
    except Exception as e:
        logger.error("[PortfolioScheduler] Failed to cache watchlist snapshot: %s", e, exc_info=True)

    try:
        ws_manager = get_websocket_manager()
        message = {
            "type": "portfolio_monitor_update",
            "scope": "watchlist",
            **payload,
        }
        asyncio.create_task(ws_manager.broadcast_all(message))
        logger.info("[PortfolioScheduler] Broadcast watchlist portfolio_monitor_update to WebSocket clients")
    except Exception as e:
        logger.error("[PortfolioScheduler] Failed to broadcast watchlist update: %s", e, exc_info=True)


async def portfolio_monitor_loop() -> None:
    """Main portfolio monitoring loop (every 5 minutes during market hours)."""
    global _running

    logger.info("[PortfolioScheduler] Starting portfolio monitor scheduler")

    while _running:
        try:
            if _is_market_open_ist():
                logger.info("[PortfolioScheduler] Market open - running portfolio and watchlist monitor")
                await _run_portfolio_cycle()
                await _run_watchlist_cycle()
            else:
                ist_now = now_ist()
                logger.debug(
                    "[PortfolioScheduler] Market closed (IST %02d:%02d), skipping portfolio monitoring",
                    ist_now.hour,
                    ist_now.minute,
                )

            # Wait 5 minutes
            await asyncio.sleep(300)
        except asyncio.CancelledError:
            logger.info("[PortfolioScheduler] Scheduler cancelled")
            break
        except Exception as e:
            logger.error("[PortfolioScheduler] Unexpected error: %s", e, exc_info=True)
            await asyncio.sleep(60)


async def start_portfolio_monitor() -> None:
    """Start the portfolio monitor scheduler (called on app startup)."""
    global _portfolio_task, _running

    if _running:
        logger.warning("[PortfolioScheduler] Already running")
        return

    _running = True
    _portfolio_task = asyncio.create_task(portfolio_monitor_loop())
    logger.info("[PortfolioScheduler] Scheduler started - monitoring every 5 minutes")


def stop_portfolio_monitor() -> None:
    """Stop the portfolio monitor scheduler (called on app shutdown)."""
    global _portfolio_task, _running

    if not _running:
        return

    _running = False

    if _portfolio_task and not _portfolio_task.done():
        _portfolio_task.cancel()
        logger.info("[PortfolioScheduler] Scheduler stopped")
