import json
import asyncio
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from ..core.market_hours import now_ist, is_cash_market_open_ist, is_scalping_cycle_window_ist
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

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
from ..agents.trade_strategy_agent import TradeStrategyAgent
from ..agents.watchlist_intelligence_agent import WatchlistIntelligenceAgent
from ..agents.auto_monitoring_agent import AutoMonitoringAgent
from ..agents.personalization_agent import PersonalizationAgent
from .intelligent_insights import generate_batch_insights
from .top_picks_engine import get_universe_symbols
from .realtime_prices import enrich_picks_with_realtime_data
from .redis_client import set_json, get_json, acquire_lock, release_lock, LOCK_DISABLED_SENTINEL
from .top_picks_store import get_top_picks_store
from .event_logger import log_event
from .ai_recommendation_store import get_ai_recommendation_store
from .pick_logger import (
    log_pick_event,
    AgentContributionInput,
    async_compute_and_log_outcomes_for_date,
)

# Import recommendation system for actionable picks (no Hold/Neutral)
from ..utils.recommendation_system import (
    get_recommendation,
    filter_actionable_picks
)


TOP_PICKS_CACHE: Dict[str, Dict[str, Any]] = {}


IST_TZ = ZoneInfo("Asia/Kolkata")


STRICT_BACKFILL_MODES = {"Scalping", "Intraday", "Swing", "Options", "Futures"}


def _previous_trading_day(ref_date: date) -> date:
    """Return the previous trading day (Mon-Fri) for a given date.

    This is a simple calendar-based approximation that skips weekends but
    does not account for exchange holidays. It is sufficient to ensure we
    never surface Top Picks snapshots that are many sessions old (e.g. 9
    days), while still allowing Friday snapshots to show on a Monday
    morning when there is no fresh run yet.
    """

    one_day = timedelta(days=1)
    cur = ref_date - one_day
    # 0 = Monday, 6 = Sunday; treat Sat/Sun as non-trading
    while cur.weekday() >= 5:
        cur -= one_day
    return cur


def _is_within_last_trading_session(as_of_str: str | None) -> bool:
    """Return True if the given ISO timestamp is from today or the
    immediately preceding trading day in IST.

    Any payload older than this window is treated as too stale to
    backfill into the Top Five Picks UI for strict modes (Swing,
    Options, Futures).
    """

    if not isinstance(as_of_str, str) or not as_of_str:
        return False

    try:
        ts = datetime.fromisoformat(as_of_str.replace("Z", ""))
    except Exception:
        return False

    # Engine timestamps are stored in UTC; convert approximately to IST
    ist_ts = ts + timedelta(hours=5, minutes=30)
    as_of_date = ist_ts.date()

    ist_now = now_ist()
    today = ist_now.date()

    if as_of_date == today:
        return True

    prev_trading = _previous_trading_day(today)
    return as_of_date == prev_trading


def _cache_key(universe: str, mode: str) -> str:
    """Build cache key for a (universe, mode) pair."""
    return f"{universe.upper()}::{mode}"


class TopPicksScheduler:
    """Precomputes intraday top picks for key universes (e.g. Nifty50, BankNifty).

    Results are stored in TOP_PICKS_CACHE for instant UI access and also
    logged to disk for later performance analysis.
    """

    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler(timezone=IST_TZ)
        # Coordinator mirroring the 13-agent system in routers/agents.py
        self.coordinator = AgentCoordinator()
        self._init_agents()
        self.log_dir = Path(__file__).parent.parent.parent / "data" / "top_picks_intraday"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _init_agents(self) -> None:
        # 10 scoring agents
        self.coordinator.register_agent(TechnicalAgent(weight=0.20))
        self.coordinator.register_agent(PatternRecognitionAgent(weight=0.18))
        self.coordinator.register_agent(MarketRegimeAgent(weight=0.15))
        self.coordinator.register_agent(GlobalMarketAgent(weight=0.12))
        self.coordinator.register_agent(OptionsAgent(weight=0.12))
        self.coordinator.register_agent(SentimentAgent(weight=0.10))
        self.coordinator.register_agent(PolicyMacroAgent(weight=0.08))
        self.coordinator.register_agent(WatchlistIntelligenceAgent(weight=0.03))
        self.coordinator.register_agent(MicrostructureAgent(weight=0.01))
        self.coordinator.register_agent(RiskAgent(weight=0.01))

        # Super + utility agents
        self.coordinator.register_agent(TradeStrategyAgent(weight=0.00))
        self.coordinator.register_agent(AutoMonitoringAgent(weight=0.00))
        self.coordinator.register_agent(PersonalizationAgent(weight=0.00))

        self.coordinator.set_weights({
            'technical': 0.2111,
            'pattern_recognition': 0.19,
            'market_regime': 0.1583,
            'global': 0.12,
            'options': 0.12,
            'sentiment': 0.10,
            'policy': 0.08,
            'watchlist_intelligence': 0.00,
            'microstructure': 0.0106,
            'risk': 0.01,
            'trade_strategy': 0.00,
            'auto_monitoring': 0.00,
            'personalization': 0.00,
        })

    async def _compute_for_universe(self, universe: str, mode: str = "Intraday", top_n: int = 20, trigger: str = "scheduler", use_lock: bool = True) -> Dict[str, Any]:
        """Compute picks for a given (universe, mode) pair using TopPicksEngine.

        This delegates to generate_top_picks so that all mode-specific logic
        (agent selection, weighting, recommendations, AI insights, scalping
        exits, etc.) stays in one place.
        """

        # Hard cutoff: do not generate fresh intraday-style picks after 15:15 IST.
        # This applies to Scalping, Intraday, Options, Futures. Swing remains
        # unrestricted since it is multi-day. A special "backfill" trigger is
        # allowed to run after hours so that warm_top_picks can compute a last
        # trading-session snapshot when the backend starts late.
        if mode in {"Scalping", "Intraday", "Options", "Futures"}:
            ist_now = now_ist()
            minutes = ist_now.hour * 60 + ist_now.minute
            cutoff_minutes = 15 * 60 + 15  # 15:15 IST
            if minutes >= cutoff_minutes and trigger != "backfill":
                print(
                    f"[TopPicksScheduler] Skipping {mode} run for {universe} after 15:15 IST "
                    f"(IST {ist_now.hour:02d}:{ist_now.minute:02d}, trigger={trigger})"
                )
                # Prefer returning the last cached snapshot so user APIs still
                # have something to serve instead of empty deterministic data,
                # but clamp to at most the last trading session.
                cached = get_cached_top_picks(universe, mode)
                return cached or {}

        from .top_picks_engine import generate_top_picks

        lock_token = None
        lock_key = f"lock:top_picks:{universe.lower()}:{mode.lower()}"
        if use_lock:
            try:
                lock_token = acquire_lock(lock_key, ttl=900)
                if lock_token is None:
                    print(f"[TopPicksScheduler] Lock held for {universe}/{mode}, skipping run")
                    return TOP_PICKS_CACHE.get(_cache_key(universe, mode)) or {}
            except Exception as e:
                print(f"[TopPicksScheduler] Failed to acquire lock for {universe}/{mode}: {e}")

        try:
            print(f"[TopPicksScheduler] Computing {mode} picks for {universe} (top {top_n})...")
            start = datetime.utcnow()

            # Use the shared engine which already filters to actionable picks and
            # adds AI insights and (for Scalping) exit strategies.
            data = await generate_top_picks(
                universe=universe,
                top_n=top_n,
                mode=mode,
            )

            items = data.get("picks") or []

            elapsed_engine = None
            try:
                elapsed_engine = data.get("metadata", {}).get("analysis_time_seconds")
            except Exception:
                elapsed_engine = None

            elapsed = elapsed_engine if isinstance(elapsed_engine, (int, float)) else (datetime.utcnow() - start).total_seconds()

            payload = {
                "items": items,
                "as_of": data.get("generated_at") or datetime.utcnow().isoformat() + "Z",
                "universe": data.get("universe", universe),
                "mode": data.get("mode", mode),
                "elapsed_seconds": elapsed,
                "policy_version": (data.get("metadata") or {}).get("policy_version"),
            }

            # Best-effort: log each pick as a structured event for RL/analytics.
            try:
                ist_now = now_ist()
                trade_date = ist_now.date()

                for item in items:
                    symbol = str(item.get("symbol") or "").upper()
                    if not symbol:
                        continue

                    rec_text = str(item.get("recommendation") or "Hold")
                    direction = "SHORT" if "sell" in rec_text.lower() else "LONG"

                    # Prefer explicit entry_price when present (e.g. Scalping),
                    # fall back to technical price.
                    try:
                        signal_price = item.get("entry_price") or item.get("price")
                    except Exception:
                        signal_price = None
                    if not signal_price:
                        continue

                    exit_strategy = item.get("exit_strategy") or {}
                    rec_target = None
                    rec_stop = None
                    exit_profile_id = None
                    if isinstance(exit_strategy, dict):
                        try:
                            rec_target = exit_strategy.get("target_price")
                            rec_stop = exit_strategy.get("stop_loss_price")
                        except Exception:
                            rec_target = None
                            rec_stop = None

                        try:
                            strategy_profile = exit_strategy.get("strategy_profile") or {}
                            if isinstance(strategy_profile, dict):
                                sp_id = strategy_profile.get("id") or strategy_profile.get("name")
                                if sp_id:
                                    exit_profile_id = str(sp_id)
                        except Exception:
                            exit_profile_id = None

                        if exit_profile_id is None:
                            try:
                                scalp_type = exit_strategy.get("scalp_type")
                                if scalp_type:
                                    exit_profile_id = f"SCALP_{str(scalp_type).upper()}"
                            except Exception:
                                exit_profile_id = None

                    scores = item.get("scores") or {}
                    agent_contribs = []
                    if isinstance(scores, dict):
                        for agent_name, score_val in scores.items():
                            try:
                                s_val = float(score_val) if score_val is not None else None
                            except Exception:
                                s_val = None
                            agent_contribs.append(
                                AgentContributionInput(
                                    agent_name=str(agent_name),
                                    score=s_val,
                                    confidence=None,
                                    metadata=None,
                                )
                            )

                    extra_ctx = {
                        "rank": item.get("rank"),
                        "run_trigger": trigger,
                        "run_id": None,
                        "policy_version": payload.get("policy_version"),
                        "horizon": item.get("horizon"),
                    }

                    # Derive bandit context buckets from pick metadata. These
                    # are used by the RL bandit layer (initially for
                    # Scalping) to learn context-aware preferences over exit
                    # profiles.
                    try:
                        regime_bucket = str(item.get("regime_bucket") or "Unknown")
                    except Exception:
                        regime_bucket = "Unknown"
                    try:
                        vol_bucket = str(item.get("vol_bucket") or "Unknown")
                    except Exception:
                        vol_bucket = "Unknown"
                    try:
                        user_risk_bucket = str(item.get("user_risk_bucket") or "Moderate")
                    except Exception:
                        user_risk_bucket = "Moderate"

                    extra_ctx["regime_bucket"] = regime_bucket
                    extra_ctx["vol_bucket"] = vol_bucket
                    extra_ctx["user_risk_bucket"] = user_risk_bucket
                    extra_ctx["bandit_ctx"] = f"{payload['mode']}|{regime_bucket}|{vol_bucket}|{user_risk_bucket}"

                    # Optional intraday context: session segment and
                    # position-within-day value bucket. These are useful for
                    # contextual bandits (especially Intraday) and RL
                    # analytics but are logged for all modes when present.
                    try:
                        session_segment = item.get("session_segment")
                        if session_segment:
                            extra_ctx["session_segment"] = str(session_segment)
                    except Exception:
                        pass

                    try:
                        value_bucket = item.get("value_bucket")
                        if value_bucket:
                            extra_ctx["value_bucket"] = str(value_bucket)
                    except Exception:
                        pass

                    # Entry bandit: track which entry_action_id was used to
                    # surface this pick (primarily for Scalping mode).
                    try:
                        entry_action_id = item.get("entry_action_id")
                        if entry_action_id:
                            extra_ctx["entry_action_id"] = str(entry_action_id)
                    except Exception:
                        pass

                    if exit_profile_id:
                        extra_ctx["exit_profile_id"] = exit_profile_id

                    log_pick_event(
                        symbol=symbol,
                        direction=direction,
                        source=f"TOP_PICKS_{trigger}",
                        mode=payload["mode"],
                        signal_ts=datetime.utcnow(),
                        trade_date=trade_date,
                        signal_price=float(signal_price),
                        recommended_entry=float(signal_price),
                        recommended_target=float(rec_target) if rec_target is not None else None,
                        recommended_stop=float(rec_stop) if rec_stop is not None else None,
                        time_horizon=str(item.get("horizon") or payload["mode"]),
                        blend_score=float(item.get("score_blend", item.get("blend_score", 0.0)) or 0.0),
                        recommendation=rec_text,
                        confidence=str(item.get("confidence") or ""),
                        regime=None,
                        risk_profile_bucket=None,
                        mode_bucket=payload["mode"],
                        universe=str(payload["universe"]).upper(),
                        extra_context=extra_ctx,
                        agent_contributions=agent_contribs,
                    )
            except Exception as e:
                try:
                    print(f"[TopPicksScheduler] pick_logger logging failed for {universe}/{mode}: {e}")
                except Exception:
                    pass

            # Persist run to SQLite history (best-effort)
            run_id = None
            try:
                store = get_top_picks_store()
                run_id = store.store_run(data, trigger=trigger)
            except Exception as e:
                print(f"[TopPicksScheduler] Failed to persist top picks run: {e}")

            if run_id:
                payload["run_id"] = run_id

            # Best-effort: persist per-pick AI recommendations for analytics/RL.
            try:
                rec_store = get_ai_recommendation_store()
                inserted = rec_store.log_from_top_picks_payload(payload, source=trigger)
                if inserted:
                    print(f"[TopPicksScheduler] Logged {inserted} AI recommendations for {universe}/{mode} ({trigger})")
            except Exception as e:
                print(f"[TopPicksScheduler] Failed to log AI recommendations: {e}")

            try:
                log_event(
                    event_type="top_picks_scheduled",
                    source="top_picks_scheduler",
                    payload={
                        "universe": payload["universe"],
                        "mode": payload["mode"],
                        "trigger": trigger,
                        "elapsed_seconds": payload["elapsed_seconds"],
                        "items_count": len(payload["items"]),
                        "as_of": payload["as_of"],
                        "run_id": payload.get("run_id"),
                    },
                )
            except Exception:
                pass

            # Update in-memory cache
            key = _cache_key(universe, mode)
            TOP_PICKS_CACHE[key] = payload

            # Write to Redis cache (optional)
            try:
                set_json(f"top_picks:{universe.lower()}:{mode.lower()}", payload, ex=3600)
            except Exception as e:
                print(f"[TopPicksScheduler] Redis cache write failed: {e}")

            # Log to disk for analysis/debug (separate from TopPicksEngine history)
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            log_file = self.log_dir / f"picks_{universe}_{mode}_{ts}.json"
            try:
                with open(log_file, "w") as f:
                    json.dump(payload, f, indent=2)
                print(f"[TopPicksScheduler] Logged picks to {log_file}")
            except Exception as e:
                print(f"[TopPicksScheduler] Failed to log picks: {e}")

            # Broadcast update to WebSocket clients (non-blocking)
            try:
                from .websocket_manager import get_websocket_manager

                ws_manager = get_websocket_manager()
                message: Dict[str, Any] = {
                    "type": "top_picks_update",
                    **payload,
                }
                # Fire-and-forget to avoid blocking scheduler
                asyncio.create_task(ws_manager.broadcast_all(message))
                print(f"[TopPicksScheduler] Broadcast top_picks_update for {universe} ({mode}) to WebSocket clients")
            except Exception as e:
                print(f"[TopPicksScheduler] Failed to broadcast WebSocket update: {e}")

            return payload
        finally:
            if use_lock and lock_token not in (None, LOCK_DISABLED_SENTINEL):
                try:
                    release_lock(lock_key, lock_token)
                except Exception as e:
                    print(f"[TopPicksScheduler] Failed to release lock for {universe}/{mode}: {e}")

    async def _eod_outcomes_job(self) -> None:
        """Compute simple EOD outcomes for today's picks using pick_logger.

        This runs once after market close and backfills basic win/loss labels
        and return metrics for all pick_events rows for the trading date.
        """

        try:
            ist_now = now_ist()
            trade_date = ist_now.date()
            processed = await async_compute_and_log_outcomes_for_date(trade_date, evaluation_horizon="EOD")
            print(f"[TopPicksScheduler] EOD outcomes job processed {processed} picks for {trade_date}")
        except Exception as e:
            print(f"[TopPicksScheduler] EOD outcomes job failed: {e}")

    async def _scalping_cycle_job(self) -> None:
        """Periodic scalping cycle during market hours (IST)."""
        universes = ["nifty50", "banknifty"]

        ist_now = now_ist()
        market_open = is_scalping_cycle_window_ist(ist_now)

        if not market_open:
            print(
                f"[TopPicksScheduler] Skipping scalping cycle outside market window "
                f"(IST {ist_now.hour:02d}:{ist_now.minute:02d})"
            )
            return

        for u in universes:
            try:
                await self._compute_for_universe(u, mode="Scalping", trigger="scalping_cycle")
            except Exception as e:
                print(f"[TopPicksScheduler] Failed scalping cycle for {u}: {e}")

    async def refresh_all(self) -> None:
        # Legacy refresh of all universes/modes (kept for manual/debug use)
        universes = ["nifty50", "banknifty"]
        modes = ["Scalping", "Intraday", "Swing", "Options", "Futures"]

        for u in universes:
            for mode in modes:
                try:
                    await self._compute_for_universe(u, mode=mode)
                except Exception as e:
                    print(f"[TopPicksScheduler] Failed to compute picks for {u} / {mode}: {e}")

    def start(self) -> None:
        """Start scheduler with intraday refresh slots.

        Slots (IST): 08:00, 09:30, 11:30, 13:30, 15:15
        Schedule refreshes approximately every hour during market hours.
        """
        try:
            universes = ["nifty50", "banknifty"]

            # Pre-market analysis (staggered per mode by 3 minutes starting 08:00 IST, weekdays only)
            preopen_hour = 8
            mode_offsets = [
                ("Scalping", 0),
                ("Intraday", 3),
                ("Swing", 6),
                ("Options", 9),
                ("Futures", 12),
            ]
            for u in universes:
                for mode, minute in mode_offsets:
                    self.scheduler.add_job(
                        self._compute_for_universe,
                        CronTrigger(day_of_week="mon-fri", hour=str(preopen_hour), minute=str(minute), timezone=IST_TZ),
                        id=f"top_picks_preopen_{u}_{mode.lower()}",
                        replace_existing=True,
                        kwargs={"universe": u, "mode": mode, "trigger": "preopen"},
                    )

            # Scalping cycle: every 10 minutes during market hours (IST) on trading weekdays
            self.scheduler.add_job(
                self._scalping_cycle_job,
                CronTrigger(day_of_week="mon-fri", hour="9-15", minute="*/10", timezone=IST_TZ),
                id="top_picks_scalping_cycle",
                replace_existing=True,
            )

            # Hourly refresh for non-scalping modes, staggered by 3-minute offsets starting 10:03 IST (weekdays only)
            hourly_hours = "9-15"
            hourly_mode_offsets = [
                ("Intraday", 33),
                ("Swing", 36),
                ("Options", 39),
                ("Futures", 42),
            ]
            for u in universes:
                for mode, minute in hourly_mode_offsets:
                    self.scheduler.add_job(
                        self._compute_for_universe,
                        CronTrigger(day_of_week="mon-fri", hour=hourly_hours, minute=str(minute), timezone=IST_TZ),
                        id=f"top_picks_hourly_{u}_{mode.lower()}",
                        replace_existing=True,
                        kwargs={"universe": u, "mode": mode, "trigger": "hourly"},
                    )

            # End-of-day outcomes computation (16:00 IST, weekdays)
            self.scheduler.add_job(
                self._eod_outcomes_job,
                CronTrigger(day_of_week="mon-fri", hour="16", minute="0", timezone=IST_TZ),
                id="top_picks_eod_outcomes",
                replace_existing=True,
            )

            self.scheduler.start()
            print("[TopPicksScheduler] Started scheduler for intraday top picks with mode-staggered jobs")
        except Exception as e:
            print(f"[TopPicksScheduler] Failed to start scheduler: {e}")

    def stop(self) -> None:
        try:
            self.scheduler.shutdown()
            print("[TopPicksScheduler] Stopped scheduler for intraday top picks")
        except Exception as e:
            print(f"[TopPicksScheduler] Failed to stop scheduler: {e}")


_scheduler: TopPicksScheduler | None = None


def get_top_picks_scheduler() -> TopPicksScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = TopPicksScheduler()
    return _scheduler


async def start_top_picks_scheduler() -> None:
    scheduler = get_top_picks_scheduler()
    scheduler.start()


def stop_top_picks_scheduler() -> None:
    scheduler = get_top_picks_scheduler()
    scheduler.stop()


def get_cached_top_picks(universe: str, mode: str | None = None) -> Dict[str, Any] | None:
    """Get cached picks for a universe and (optionally) a specific mode.

    If mode is provided, returns only that (universe, mode) entry. If mode is
    omitted, falls back to Intraday first, then any available mode for the
    universe.
    """

    store = get_top_picks_store()

    if mode:
        key = _cache_key(universe, mode)
        cached = TOP_PICKS_CACHE.get(key)
        if isinstance(cached, dict):
            items = cached.get("items") or []
            as_of = cached.get("as_of") or cached.get("generated_at")
            # Treat zero-length caches as missing so that we can fall back to
            # older non-empty runs from Redis/SQLite instead of forcing
            # deterministic pseudo-scores.
            if (
                isinstance(items, list)
                and len(items) > 0
                and (mode not in STRICT_BACKFILL_MODES or _is_within_last_trading_session(as_of))
            ):
                return cached

        # 1) Try Redis rehydration
        try:
            redis_payload = get_json(f"top_picks:{universe.lower()}:{mode.lower()}")
        except Exception:
            redis_payload = None

        if isinstance(redis_payload, dict):
            items = redis_payload.get("items") or []
            as_of = redis_payload.get("as_of") or redis_payload.get("generated_at")
            if (
                isinstance(items, list)
                and len(items) > 0
                and (mode not in STRICT_BACKFILL_MODES or _is_within_last_trading_session(as_of))
            ):
                TOP_PICKS_CACHE[key] = redis_payload
                return redis_payload

        # 2) Try SQLite history as final fallback
        try:
            latest = store.get_latest_run_for(universe, mode)
        except Exception:
            latest = None

        if isinstance(latest, dict):
            items = latest.get("items") or []
            as_of = latest.get("as_of") or latest.get("generated_at")
            if (
                isinstance(items, list)
                and len(items) > 0
                and (mode not in STRICT_BACKFILL_MODES or _is_within_last_trading_session(as_of))
            ):
                TOP_PICKS_CACHE[key] = latest
                return latest

        return None

    # Backwards-compatible fallback when mode is not specified:
    # 1) Prefer Intraday if present or can be rehydrated
    intraday = get_cached_top_picks(universe, "Intraday")
    if intraday:
        return intraday

    # 2) Any cached mode for this universe (in-memory first)
    universe_prefix = f"{universe.upper()}::"
    for key, payload in TOP_PICKS_CACHE.items():
        if key.startswith(universe_prefix):
            return payload

    # 3) As a last resort, try SQLite for any mode for this universe
    try:
        # Attempt common modes in priority order
        for mode_name in ["Swing", "Intraday", "Scalping", "Options", "Futures"]:
            latest = store.get_latest_run_for(universe, mode_name)
            if isinstance(latest, dict) and latest.get("items"):
                TOP_PICKS_CACHE[_cache_key(universe, mode_name)] = latest
                return latest
    except Exception:
        pass

    return None


async def force_refresh_universe(universe: str, mode: str = "Intraday") -> Dict[str, Any]:
    """Force a recompute for a specific (universe, mode)."""
    scheduler = get_top_picks_scheduler()
    return await scheduler._compute_for_universe(universe, mode=mode, trigger="manual")


async def warm_top_picks(max_age_minutes: int = 60) -> None:
    scheduler = get_top_picks_scheduler()
    universes = ["nifty50", "banknifty"]
    modes = ["Scalping", "Intraday", "Swing", "Options", "Futures"]
    now = datetime.utcnow()
    ist_now = now_ist()
    market_window = is_cash_market_open_ist(ist_now)
    print(f"[TopPicksScheduler] Warmup start (IST {ist_now.isoformat()}, market_window={market_window})")

    store = get_top_picks_store()

    for u in universes:
        for mode in modes:
            try:
                cached = get_cached_top_picks(u, mode)
                as_of = None
                age_minutes = None
                if isinstance(cached, dict):
                    as_of = cached.get("as_of") or cached.get("generated_at")
                    if isinstance(as_of, str):
                        try:
                            ts = datetime.fromisoformat(as_of.replace("Z", ""))
                            age_minutes = (now - ts).total_seconds() / 60.0
                        except Exception:
                            age_minutes = None

                # Per-mode freshness threshold: Scalping is much stricter
                stale_threshold = 10 if mode == "Scalping" else max_age_minutes

                fresh = cached is not None and age_minutes is not None and age_minutes <= stale_threshold
                if fresh:
                    print(f"[TopPicksScheduler] Warmup skip {u}/{mode}: cache {age_minutes:.1f} min old (threshold={stale_threshold}m)")
                    continue

                if not market_window:
                    # When markets are closed we never want to generate **new**
                    # scalping runs after-hours. Instead, hydrate from the last
                    # in-session snapshot in history so users see the final
                    # session view without confusing late timestamps like
                    # 21:27 IST.
                    if mode == "Scalping":
                        try:
                            hist = store.get_latest_run_for(u, mode)
                        except Exception:
                            hist = None

                        if isinstance(hist, dict) and hist.get("items"):
                            TOP_PICKS_CACHE[_cache_key(u, mode)] = hist
                            print(
                                f"[TopPicksScheduler] Warmup hydrate {u}/{mode} from history "
                                f"(market closed, no fresh scalping compute)"
                            )
                        else:
                            print(
                                f"[TopPicksScheduler] Warmup skip compute for {u}/{mode}: "
                                f"market closed and no historical scalping snapshot"
                            )
                        continue

                    if cached is None:
                        print(f"[TopPicksScheduler] Warmup backfill {u}/{mode}: no snapshot found, computing once even though market is closed")
                        await scheduler._compute_for_universe(u, mode=mode, trigger="backfill", use_lock=False)
                        continue

                    is_prev_session = False
                    if isinstance(as_of, str):
                        try:
                            ts = datetime.fromisoformat(as_of.replace("Z", ""))
                            is_prev_session = ts.date() < ist_now.date()
                        except Exception:
                            is_prev_session = False

                    needs_backfill = age_minutes is None or age_minutes > stale_threshold or is_prev_session
                    if needs_backfill:
                        print(
                            f"[TopPicksScheduler] Warmup backfill {u}/{mode}: snapshot stale or from previous session "
                            f"(age={age_minutes}, threshold={stale_threshold}m, prev_session={is_prev_session}), computing once even though market is closed"
                        )
                        await scheduler._compute_for_universe(u, mode=mode, trigger="backfill", use_lock=False)
                    else:
                        print(f"[TopPicksScheduler] Warmup skip compute for {u}/{mode}: market closed, using last snapshot")
                    continue

                print(f"[TopPicksScheduler] Warmup compute {u}/{mode} (stale or missing cache)")
                await scheduler._compute_for_universe(u, mode=mode, trigger="warmup")
            except Exception as e:
                print(f"[TopPicksScheduler] Warmup error for {u}/{mode}: {e}")
