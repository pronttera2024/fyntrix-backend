"""
ORM-based Pick Logger Service
Converts raw SQLite operations to SQLAlchemy ORM
"""

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, date, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, or_, func, desc
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.config.database import get_db
from app.models.trading import PickEvent, PickAgentContribution, PickOutcome, RlPolicy

from pytz import timezone as pytz_timezone


# Default per-mode evaluation settings used by RL trainers when
# config["evaluation"][mode] is missing or incomplete. These windows
# are shared between exit-profile evaluation and bandit trainers so
# that both see a comparable sample of recent trades.
_DEFAULT_RL_EVAL_BY_MODE: Dict[str, Dict[str, Any]] = {
    "Scalping": {
        "lookback_days": 90,
        "timeframe": "1D",
        "evaluation_horizon": "SCALPING",
    },
    "Intraday": {
        "lookback_days": 60,
        "timeframe": "15m",
        "evaluation_horizon": "EOD",
    },
    "Swing": {
        "lookback_days": 180,
        "timeframe": "1D",
        "evaluation_horizon": "EOD",
    },
    "Options": {
        "lookback_days": 60,
        "timeframe": "5m",
        "evaluation_horizon": "EOD",
    },
    "Futures": {
        "lookback_days": 60,
        "timeframe": "5m",
        "evaluation_horizon": "EOD",
    },
    "default": {
        "lookback_days": 90,
        "timeframe": "1D",
        "evaluation_horizon": "EOD",
    },
}


@dataclass
class AgentContributionInput:
    agent_name: str
    score: Optional[float] = None
    confidence: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


def _to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def log_pick_event(
    *,
    symbol: str,
    direction: str,
    source: str,
    mode: str,
    signal_ts: datetime,
    trade_date: date,
    signal_price: float,
    recommended_entry: Optional[float] = None,
    recommended_target: Optional[float] = None,
    recommended_stop: Optional[float] = None,
    time_horizon: Optional[str] = None,
    blend_score: Optional[float] = None,
    recommendation: Optional[str] = None,
    confidence: Optional[str] = None,
    regime: Optional[str] = None,
    risk_profile_bucket: Optional[str] = None,
    mode_bucket: Optional[str] = None,
    universe: Optional[str] = None,
    extra_context: Optional[Dict[str, Any]] = None,
    agent_contributions: Optional[List[AgentContributionInput]] = None,
) -> str:
    """Insert a pick_events row (and optional agent contributions) using ORM.

    Returns the generated pick_uuid string. Best-effort only: any failure is
    logged to stdout but does not raise back into the main trading flow.
    """

    pick_uuid = uuid.uuid4().hex

    try:
        db = next(get_db())

        # Create the pick event
        pick_event = PickEvent(
            pick_uuid=pick_uuid,
            symbol=str(symbol).upper(),
            direction=str(direction).upper(),
            source=str(source),
            mode=str(mode),
            signal_ts=signal_ts,
            trade_date=trade_date,
            signal_price=float(signal_price),
            recommended_entry=float(recommended_entry) if recommended_entry is not None else None,
            recommended_target=float(recommended_target) if recommended_target is not None else None,
            recommended_stop=float(recommended_stop) if recommended_stop is not None else None,
            time_horizon=time_horizon,
            blend_score=float(blend_score) if blend_score is not None else None,
            recommendation=recommendation,
            confidence=confidence,
            regime=regime,
            risk_profile_bucket=risk_profile_bucket,
            mode_bucket=mode_bucket,
            universe=universe,
            extra_context=extra_context,
        )

        db.add(pick_event)

        # Add agent contributions if provided
        if agent_contributions:
            for contrib in agent_contributions:
                try:
                    agent_contrib = PickAgentContribution(
                        pick_uuid=pick_uuid,
                        agent_name=contrib.agent_name,
                        score=float(contrib.score) if contrib.score is not None else None,
                        confidence=contrib.confidence,
                        metadata=contrib.metadata,
                    )
                    db.add(agent_contrib)
                except Exception as e:
                    print(f"[PickLogger] Failed to create agent contribution for {contrib.agent_name}: {e}")
                    continue

        db.commit()

    except Exception as e:
        try:
            db.rollback()
            print(f"[PickLogger] Failed to log pick event for {symbol}: {e}")
        except Exception:
            pass

def log_scalping_exit_outcome(exit_data: Dict[str, Any], evaluation_horizon: str = "SCALPING") -> Optional[str]:
    """Best-effort hook to map a scalping exit into pick_outcomes using ORM.

    Attempts to locate the corresponding pick_events row for the
    (symbol, trade_date, mode='Scalping') combination using entry_time
    and entry_price as hints. Returns the matched pick_uuid, or None if
    no suitable pick is found.
    """

    symbol = str(exit_data.get("symbol") or "").upper()
    if not symbol:
        return None

    try:
        entry_time_raw = exit_data.get("entry_time")
        if not entry_time_raw:
            return None
        entry_dt = datetime.fromisoformat(str(entry_time_raw).replace("Z", "+00:00"))
        if entry_dt.tzinfo is None:
            entry_dt = entry_dt.replace(tzinfo=timezone.utc)
        else:
            entry_dt = entry_dt.astimezone(timezone.utc)
        trade_date = entry_dt.date()
    except Exception:
        return None

    try:
        entry_price = float(exit_data.get("entry_price"))
        if entry_price <= 0:
            entry_price = None
    except Exception:
        entry_price = None

    try:
        db = next(get_db())

        # Find matching pick events using ORM
        pick_events = db.query(PickEvent).filter(
            and_(
                PickEvent.symbol == symbol,
                PickEvent.mode == "Scalping",
                PickEvent.trade_date == trade_date
            )
        ).all()

        if not pick_events:
            return None

        best_pick_uuid: Optional[str] = None
        best_score: Optional[float] = None

        for pick_event in pick_events:
            time_diff_min: Optional[float] = None
            if pick_event.signal_ts is not None:
                time_diff_min = abs((entry_dt - pick_event.signal_ts).total_seconds()) / 60.0

            price_diff_pct: Optional[float] = None
            try:
                sp_val = float(pick_event.signal_price)
                if sp_val > 0 and entry_price is not None:
                    price_diff_pct = abs(entry_price - sp_val) / sp_val * 100.0
            except Exception:
                price_diff_pct = None

            score_components: list[float] = []
            if time_diff_min is not None:
                score_components.append(min(time_diff_min, 120.0))
            if price_diff_pct is not None:
                score_components.append(min(price_diff_pct * 5.0, 200.0))

            if not score_components:
                continue

            score = sum(score_components)
            if best_score is None or score < best_score:
                best_score = score
                best_pick_uuid = pick_event.pick_uuid

        if best_pick_uuid is None:
            return None

    except Exception as e:
        print(f"[PickLogger] Failed to find matching pick for {symbol}: {e}")
        return None

    try:
        exit_price = float(exit_data.get("exit_price"))
    except Exception:
        exit_price = None

    try:
        ret_close_pct = float(exit_data.get("return_pct"))
    except Exception:
        ret_close_pct = None

    outcome_label: Optional[str] = None
    if ret_close_pct is not None:
        if ret_close_pct > 0.5:
            outcome_label = "WIN"
        elif ret_close_pct < -0.5:
            outcome_label = "LOSS"
        else:
            outcome_label = "BREAKEVEN"

    capture_ratio: Optional[float] = None
    try:
        if ret_close_pct is not None:
            if ret_close_pct > 0:
                capture_ratio = 1.0
            elif ret_close_pct < 0:
                capture_ratio = 0.0
    except Exception:
        capture_ratio = None

    exit_time_raw = exit_data.get("exit_time")
    try:
        exit_dt = datetime.fromisoformat(str(exit_time_raw).replace("Z", "+00:00")) if exit_time_raw else datetime.utcnow()
        if exit_dt.tzinfo is None:
            exit_dt = exit_dt.replace(tzinfo=timezone.utc)
        else:
            exit_dt = exit_dt.astimezone(timezone.utc)
    except Exception:
        exit_dt = datetime.utcnow().replace(tzinfo=timezone.utc)

    exit_reason = str(exit_data.get("exit_reason") or "").upper() or None

    notes_dict: Dict[str, Any] = {
        "exit_reason": exit_reason,
        "capture_ratio": capture_ratio,
    }
    try:
        notes_json = json.dumps(notes_dict, default=str)
    except Exception:
        notes_json = exit_reason

    log_pick_outcome(
        pick_uuid=best_pick_uuid,
        evaluation_horizon=evaluation_horizon,
        horizon_end_ts=exit_dt,
        price_close=exit_price,
        price_high=None,
        price_low=None,
        ret_close_pct=ret_close_pct,
        max_runup_pct=None,
        max_drawdown_pct=None,
        benchmark_symbol=None,
        benchmark_ret_pct=None,
        ret_vs_benchmark_pct=None,
        hit_target=True if exit_reason == "TARGET_HIT" else None,
        hit_stop=True if exit_reason == "STOP_LOSS" else None,
        outcome_label=outcome_label,
        notes=notes_json,
    )

    return best_pick_uuid


async def async_compute_and_log_outcomes_for_date(
    trade_date: date,
    evaluation_horizon: str = "EOD",
) -> int:
    """Compute simple EOD outcomes for all picks on a given trade_date using ORM.

    This uses ChartDataService to get intraday candles for each symbol and
    derives close, high, low, run-up, and drawdown relative to the
    signal_price. For now we skip benchmark-based alpha; that can be added
    later once a consistent index data source is wired in.
    """

    from .chart_data_service import chart_data_service

    ist = pytz_timezone("Asia/Kolkata")

    benchmark_symbol = "NIFTY"
    benchmark_ret_pct: Optional[float] = None

    try:
        bench_data = await chart_data_service.fetch_chart_data(benchmark_symbol, "1D")
        bench_candles = (bench_data or {}).get("candles") or []
        if bench_candles:
            bench_trade_date_str = trade_date.isoformat()
            bench_candles_for_day: List[Dict[str, Any]] = []
            for c in bench_candles:
                try:
                    ts_raw = int(c.get("time"))
                    dt_utc = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
                    dt_ist = dt_utc.astimezone(ist)
                    if dt_ist.date().isoformat() == bench_trade_date_str:
                        bench_candles_for_day.append(c)
                except Exception:
                    continue

            if not bench_candles_for_day:
                bench_candles_for_day = bench_candles

            bench_closes = [
                float(c.get("close"))
                for c in bench_candles_for_day
                if c.get("close") is not None
            ]

            if bench_closes:
                open_px = bench_closes[0]
                close_px = bench_closes[-1]
                if open_px > 0:
                    benchmark_ret_pct = (close_px - open_px) / open_px * 100.0
    except Exception:
        benchmark_ret_pct = None

    try:
        db = next(get_db())

        # Get all pick events for the trade date using ORM
        pick_events = db.query(PickEvent).filter(
            PickEvent.trade_date == trade_date
        ).all()

        processed = 0

        for pick_event in pick_events:
            # Skip if an outcome already exists for this horizon
            existing_outcome = db.query(PickOutcome).filter(
                and_(
                    PickOutcome.pick_uuid == pick_event.pick_uuid,
                    PickOutcome.evaluation_horizon == evaluation_horizon
                )
            ).first()

            if existing_outcome:
                continue

            try:
                data = await chart_data_service.fetch_chart_data(pick_event.symbol, "1D")
            except Exception as e:
                try:
                    print(f"[PickLogger] Failed to fetch chart data for {pick_event.symbol}: {e}")
                except Exception:
                    pass
                continue

            candles = data.get("candles") or []
            if not candles:
                continue

            # Filter candles to the specific trade_date in IST if possible
            candles_for_day: List[Dict[str, Any]] = []
            for c in candles:
                try:
                    ts_raw = int(c.get("time"))
                    dt_utc = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
                    dt_ist = dt_utc.astimezone(ist)
                    if dt_ist.date().isoformat() == pick_event.trade_date.isoformat():
                        candles_for_day.append(c)
                except Exception:
                    continue

            if not candles_for_day:
                candles_for_day = candles

            highs = [float(c.get("high")) for c in candles_for_day if c.get("high") is not None]
            lows = [float(c.get("low")) for c in candles_for_day if c.get("low") is not None]
            closes = [float(c.get("close")) for c in candles_for_day if c.get("close") is not None]

            if not closes:
                continue

            price_close = closes[-1]
            price_high = max(highs) if highs else price_close
            price_low = min(lows) if lows else price_close

            try:
                sp = float(pick_event.signal_price)
                if sp <= 0:
                    continue
            except Exception:
                continue

            sign = 1.0 if str(pick_event.direction).upper() == "LONG" else -1.0

            ret_close_pct = (price_close - sp) / sp * 100.0 * sign

            if sign > 0:
                best = price_high
                worst = price_low
            else:
                best = price_low
                worst = price_high

            max_runup_pct = (best - sp) / sp * 100.0 * sign
            max_drawdown_pct = (worst - sp) / sp * 100.0 * sign

            hit_target: Optional[bool] = None
            hit_stop: Optional[bool] = None

            try:
                if pick_event.recommended_target is not None:
                    t_val = float(pick_event.recommended_target)
                    if sign > 0:
                        hit_target = any(float(c.get("high", 0.0)) >= t_val for c in candles_for_day)
                    else:
                        hit_target = any(float(c.get("low", 0.0)) <= t_val for c in candles_for_day)
            except Exception:
                hit_target = None

            try:
                if pick_event.recommended_stop is not None:
                    s_val = float(pick_event.recommended_stop)
                    if sign > 0:
                        hit_stop = any(float(c.get("low", 0.0)) <= s_val for c in candles_for_day)
                    else:
                        hit_stop = any(float(c.get("high", 0.0)) >= s_val for c in candles_for_day)
            except Exception:
                hit_stop = None

            outcome_label: Optional[str] = None
            if ret_close_pct is not None:
                if ret_close_pct > 0.5:
                    outcome_label = "WIN"
                elif ret_close_pct < -0.5:
                    outcome_label = "LOSS"
                else:
                    outcome_label = "BREAKEVEN"

            capture_ratio: Optional[float] = None
            try:
                if max_runup_pct is not None and max_runup_pct > 0:
                    if ret_close_pct is not None and ret_close_pct > 0:
                        capture_ratio = max(0.0, min(ret_close_pct / max_runup_pct, 1.0))
                    else:
                        capture_ratio = 0.0
            except Exception:
                capture_ratio = None

            notes_dict: Dict[str, Any] = {"capture_ratio": capture_ratio}
            try:
                notes_json = json.dumps(notes_dict, default=str)
            except Exception:
                notes_json = None

            horizon_end_ts = datetime.now(timezone.utc)

            log_pick_outcome(
                pick_uuid=pick_event.pick_uuid,
                evaluation_horizon=evaluation_horizon,
                horizon_end_ts=horizon_end_ts,
                price_close=price_close,
                price_high=price_high,
                price_low=price_low,
                ret_close_pct=ret_close_pct,
                max_runup_pct=max_runup_pct,
                max_drawdown_pct=max_drawdown_pct,
                benchmark_symbol=benchmark_symbol if benchmark_ret_pct is not None else None,
                benchmark_ret_pct=benchmark_ret_pct,
                ret_vs_benchmark_pct=(
                    ret_close_pct - benchmark_ret_pct
                    if benchmark_ret_pct is not None and ret_close_pct is not None
                    else None
                ),
                hit_target=hit_target,
                hit_stop=hit_stop,
                outcome_label=outcome_label,
                notes=notes_json,
            )

            processed += 1

        return processed

    except Exception as e:
        print(f"[PickLogger] Failed to compute outcomes for {trade_date}: {e}")
        return 0


def compute_and_log_outcomes_for_date(
    trade_date: date,
    evaluation_horizon: str = "EOD",
) -> int:
    """Synchronous wrapper for async_compute_and_log_outcomes_for_date.

    Useful for CLI/one-off jobs. In async contexts (e.g. schedulers), prefer
    calling async_compute_and_log_outcomes_for_date directly.
    """

    return asyncio.run(async_compute_and_log_outcomes_for_date(trade_date, evaluation_horizon))


def create_rl_policy(
    *,
    name: str,
    config: Dict[str, Any],
    description: Optional[str] = None,
    status: str = "DRAFT",
) -> str:
    """Create a new RL policy row using ORM and return its policy_id."""

    policy_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)

    try:
        config_json = json.dumps(config or {}, default=str)
    except Exception:
        config_json = "{}"

    try:
        db = next(get_db())

        rl_policy = RlPolicy(
            policy_id=policy_id,
            name=name,
            description=description,
            status=status,
            config_json=config_json,
            created_at=now,
            updated_at=now,
        )

        db.add(rl_policy)
        db.commit()
        db.refresh(rl_policy)

        return policy_id

    except Exception as e:
        try:
            db.rollback()
            print(f"[PickLogger] Failed to create RL policy {name}: {e}")
        except Exception:
            pass
        raise


def set_active_rl_policy(policy_id: str) -> None:
    """Mark a policy as ACTIVE and retire any currently active one using ORM."""

    now = datetime.now(timezone.utc)

    try:
        db = next(get_db())

        # Retire existing active policies
        db.query(RlPolicy).filter(RlPolicy.status == "ACTIVE").update({
            "status": "RETIRED",
            "deactivated_at": now,
            "updated_at": now
        })

        # Activate the requested policy
        db.query(RlPolicy).filter(RlPolicy.policy_id == policy_id).update({
            "status": "ACTIVE",
            "activated_at": now,
            "updated_at": now
        })

        db.commit()

    except Exception as e:
        try:
            db.rollback()
            print(f"[PickLogger] Failed to set active RL policy {policy_id}: {e}")
        except Exception:
            pass


def get_active_rl_policy() -> Optional[Dict[str, Any]]:
    """Return the currently ACTIVE RL policy config, if any using ORM."""

    try:
        db = next(get_db())

        rl_policy = db.query(RlPolicy).filter(
            RlPolicy.status == "ACTIVE"
        ).order_by(desc(RlPolicy.activated_at)).first()

        if not rl_policy:
            return None

        try:
            config = json.loads(rl_policy.config_json or "{}")
        except Exception:
            config = {}

        try:
            metrics = json.loads(rl_policy.metrics_json) if rl_policy.metrics_json else None
        except Exception:
            metrics = None

        return {
            "policy_id": rl_policy.policy_id,
            "name": rl_policy.name,
            "description": rl_policy.description,
            "status": rl_policy.status,
            "config": config,
            "metrics": metrics,
            "created_at": _to_iso(rl_policy.created_at) if rl_policy.created_at else None,
            "updated_at": _to_iso(rl_policy.updated_at) if rl_policy.updated_at else None,
            "activated_at": _to_iso(rl_policy.activated_at) if rl_policy.activated_at else None,
            "deactivated_at": _to_iso(rl_policy.deactivated_at) if rl_policy.deactivated_at else None,
        }

    except Exception as e:
        print(f"[PickLogger] Failed to get active RL policy: {e}")
        return None


def log_pick_outcome(
    *,
    pick_uuid: str,
    evaluation_horizon: str,
    horizon_end_ts: datetime,
    price_close: Optional[float],
    price_high: Optional[float],
    price_low: Optional[float],
    ret_close_pct: Optional[float],
    max_runup_pct: Optional[float],
    max_drawdown_pct: Optional[float],
    benchmark_symbol: Optional[str] = None,
    benchmark_ret_pct: Optional[float] = None,
    ret_vs_benchmark_pct: Optional[float] = None,
    hit_target: Optional[bool] = None,
    hit_stop: Optional[bool] = None,
    outcome_label: Optional[str] = None,
    notes: Optional[str] = None,
) -> None:
    """Insert or update a pick_outcomes row using ORM."""
    try:
        db = next(get_db())

        # Try to find existing outcome first
        existing_outcome = db.query(PickOutcome).filter(
            and_(
                PickOutcome.pick_uuid == pick_uuid,
                PickOutcome.evaluation_horizon == evaluation_horizon
            )
        ).first()

        if existing_outcome:
            # Update existing outcome
            existing_outcome.horizon_end_ts = horizon_end_ts
            existing_outcome.price_close = float(price_close) if price_close is not None else None
            existing_outcome.price_high = float(price_high) if price_high is not None else None
            existing_outcome.price_low = float(price_low) if price_low is not None else None
            existing_outcome.ret_close_pct = float(ret_close_pct) if ret_close_pct is not None else None
            existing_outcome.max_runup_pct = float(max_runup_pct) if max_runup_pct is not None else None
            existing_outcome.max_drawdown_pct = float(max_drawdown_pct) if max_drawdown_pct is not None else None
            existing_outcome.benchmark_symbol = benchmark_symbol
            existing_outcome.benchmark_ret_pct = float(benchmark_ret_pct) if benchmark_ret_pct is not None else None
            existing_outcome.ret_vs_benchmark_pct = float(ret_vs_benchmark_pct) if ret_vs_benchmark_pct is not None else None
            existing_outcome.hit_target = hit_target
            existing_outcome.hit_stop = hit_stop
            existing_outcome.outcome_label = outcome_label
            existing_outcome.notes = notes
        else:
            # Create new outcome
            outcome = PickOutcome(
                pick_uuid=pick_uuid,
                evaluation_horizon=evaluation_horizon,
                horizon_end_ts=horizon_end_ts,
                price_close=float(price_close) if price_close is not None else None,
                price_high=float(price_high) if price_high is not None else None,
                price_low=float(price_low) if price_low is not None else None,
                ret_close_pct=float(ret_close_pct) if ret_close_pct is not None else None,
                max_runup_pct=float(max_runup_pct) if max_runup_pct is not None else None,
                max_drawdown_pct=float(max_drawdown_pct) if max_drawdown_pct is not None else None,
                benchmark_symbol=benchmark_symbol,
                benchmark_ret_pct=float(benchmark_ret_pct) if benchmark_ret_pct is not None else None,
                ret_vs_benchmark_pct=float(ret_vs_benchmark_pct) if ret_vs_benchmark_pct is not None else None,
                hit_target=hit_target,
                hit_stop=hit_stop,
                outcome_label=outcome_label,
                notes=notes,
            )
            db.add(outcome)

        db.commit()

    except Exception as e:
        try:
            db.rollback()
            print(f"[PickLogger] Failed to log pick outcome for {pick_uuid}: {e}")
        except Exception:
            pass
