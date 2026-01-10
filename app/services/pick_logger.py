import asyncio
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from pytz import timezone as pytz_timezone

# Reuse the same DB file as ai_recommendations so analytics / RL data
# lives together. This will migrate cleanly to Postgres later.
_DB_PATH = Path(__file__).parent.parent.parent / "cache" / "ai_recommendations.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


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


def _init_db() -> None:
    """Initialize SQLite tables for pick events, outcomes, and RL policies.

    This is designed to be SQLite-first but maps cleanly to Postgres later
    (schema will be recreated there with native types / JSONB).
    """

    conn = sqlite3.connect(_DB_PATH)
    cursor = conn.cursor()

    # Core pick events table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pick_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pick_uuid TEXT NOT NULL UNIQUE,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            source TEXT NOT NULL,
            mode TEXT NOT NULL,
            signal_ts TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            signal_price REAL NOT NULL,
            recommended_entry REAL,
            recommended_target REAL,
            recommended_stop REAL,
            time_horizon TEXT,
            blend_score REAL,
            recommendation TEXT,
            confidence TEXT,
            regime TEXT,
            risk_profile_bucket TEXT,
            mode_bucket TEXT,
            universe TEXT,
            extra_context TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pick_events_trade_date
        ON pick_events (trade_date)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pick_events_symbol_date
        ON pick_events (symbol, trade_date)
        """
    )

    # Per-agent contributions for introspection
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pick_agent_contributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pick_uuid TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            score REAL,
            confidence TEXT,
            metadata TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pick_agent_contrib_pick_uuid
        ON pick_agent_contributions (pick_uuid)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pick_agent_contrib_agent
        ON pick_agent_contributions (agent_name)
        """
    )

    # Realised outcomes per pick / horizon
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pick_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pick_uuid TEXT NOT NULL,
            evaluation_horizon TEXT NOT NULL,
            horizon_end_ts TEXT NOT NULL,
            price_close REAL,
            price_high REAL,
            price_low REAL,
            ret_close_pct REAL,
            max_runup_pct REAL,
            max_drawdown_pct REAL,
            benchmark_symbol TEXT,
            benchmark_ret_pct REAL,
            ret_vs_benchmark_pct REAL,
            hit_target INTEGER,
            hit_stop INTEGER,
            outcome_label TEXT,
            notes TEXT,
            UNIQUE(pick_uuid, evaluation_horizon)
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pick_outcomes_label
        ON pick_outcomes (outcome_label)
        """
    )

    # RL policy registry (meta-strategy configs)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS rl_policies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            policy_id TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            status TEXT NOT NULL,
            config_json TEXT NOT NULL,
            metrics_json TEXT,
            activated_at TEXT,
            deactivated_at TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_rl_policies_status
        ON rl_policies (status)
        """
    )

    conn.commit()
    conn.close()


_init_db()


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
    """Insert a pick_events row (and optional agent contributions).

    Returns the generated pick_uuid string. Best-effort only: any failure is
    logged to stdout but does not raise back into the main trading flow.
    """

    pick_uuid = uuid.uuid4().hex

    try:
        payload_json = json.dumps(extra_context or {}, default=str)
    except Exception:
        payload_json = "{}"

    try:
        conn = sqlite3.connect(_DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO pick_events (
                pick_uuid,
                symbol,
                direction,
                source,
                mode,
                signal_ts,
                trade_date,
                signal_price,
                recommended_entry,
                recommended_target,
                recommended_stop,
                time_horizon,
                blend_score,
                recommendation,
                confidence,
                regime,
                risk_profile_bucket,
                mode_bucket,
                universe,
                extra_context
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pick_uuid,
                str(symbol).upper(),
                str(direction).upper(),
                str(source),
                str(mode),
                _to_iso(signal_ts),
                trade_date.isoformat(),
                float(signal_price),
                float(recommended_entry) if recommended_entry is not None else None,
                float(recommended_target) if recommended_target is not None else None,
                float(recommended_stop) if recommended_stop is not None else None,
                time_horizon,
                float(blend_score) if blend_score is not None else None,
                recommendation,
                confidence,
                regime,
                risk_profile_bucket,
                mode_bucket,
                universe,
                payload_json,
            ),
        )

        if agent_contributions:
            for contrib in agent_contributions:
                try:
                    meta_json = json.dumps(contrib.metadata or {}, default=str)
                except Exception:
                    meta_json = "{}"
                cursor.execute(
                    """
                    INSERT INTO pick_agent_contributions (
                        pick_uuid,
                        agent_name,
                        score,
                        confidence,
                        metadata
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        pick_uuid,
                        contrib.agent_name,
                        float(contrib.score) if contrib.score is not None else None,
                        contrib.confidence,
                        meta_json,
                    ),
                )

        conn.commit()
        conn.close()
    except Exception as e:
        try:
            print(f"[PickLogger] Failed to log pick event for {symbol}: {e}")
        except Exception:
            pass

    return pick_uuid


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
    """Insert or update a pick_outcomes row for the given pick/horizon."""

    ts_str = _to_iso(horizon_end_ts)

    try:
        conn = sqlite3.connect(_DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO pick_outcomes (
                pick_uuid,
                evaluation_horizon,
                horizon_end_ts,
                price_close,
                price_high,
                price_low,
                ret_close_pct,
                max_runup_pct,
                max_drawdown_pct,
                benchmark_symbol,
                benchmark_ret_pct,
                ret_vs_benchmark_pct,
                hit_target,
                hit_stop,
                outcome_label,
                notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(pick_uuid, evaluation_horizon) DO UPDATE SET
                horizon_end_ts = excluded.horizon_end_ts,
                price_close = excluded.price_close,
                price_high = excluded.price_high,
                price_low = excluded.price_low,
                ret_close_pct = excluded.ret_close_pct,
                max_runup_pct = excluded.max_runup_pct,
                max_drawdown_pct = excluded.max_drawdown_pct,
                benchmark_symbol = excluded.benchmark_symbol,
                benchmark_ret_pct = excluded.benchmark_ret_pct,
                ret_vs_benchmark_pct = excluded.ret_vs_benchmark_pct,
                hit_target = excluded.hit_target,
                hit_stop = excluded.hit_stop,
                outcome_label = excluded.outcome_label,
                notes = excluded.notes
            """,
            (
                pick_uuid,
                evaluation_horizon,
                ts_str,
                float(price_close) if price_close is not None else None,
                float(price_high) if price_high is not None else None,
                float(price_low) if price_low is not None else None,
                float(ret_close_pct) if ret_close_pct is not None else None,
                float(max_runup_pct) if max_runup_pct is not None else None,
                float(max_drawdown_pct) if max_drawdown_pct is not None else None,
                benchmark_symbol,
                float(benchmark_ret_pct) if benchmark_ret_pct is not None else None,
                float(ret_vs_benchmark_pct) if ret_vs_benchmark_pct is not None else None,
                1 if hit_target else 0 if hit_target is not None else None,
                1 if hit_stop else 0 if hit_stop is not None else None,
                outcome_label,
                notes,
            ),
        )

        conn.commit()
        conn.close()
    except Exception as e:
        try:
            print(f"[PickLogger] Failed to log pick outcome for {pick_uuid}: {e}")
        except Exception:
            pass


def log_scalping_exit_outcome(exit_data: Dict[str, Any], evaluation_horizon: str = "SCALPING") -> Optional[str]:
    """Best-effort hook to map a scalping exit into pick_outcomes.

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
        trade_date = entry_dt.date().isoformat()
    except Exception:
        return None

    try:
        entry_price = float(exit_data.get("entry_price"))
        if entry_price <= 0:
            entry_price = None  # type: ignore[assignment]
    except Exception:
        entry_price = None  # type: ignore[assignment]

    conn = sqlite3.connect(_DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT pick_uuid, signal_price, signal_ts
            FROM pick_events
            WHERE symbol = ?
              AND mode = 'Scalping'
              AND trade_date = ?
            """,
            (symbol, trade_date),
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    if not rows:
        return None

    best_pick_uuid: Optional[str] = None
    best_score: Optional[float] = None

    for pick_uuid, signal_price, signal_ts_str in rows:
        try:
            ts = datetime.fromisoformat(str(signal_ts_str).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)
        except Exception:
            ts = None  # type: ignore[assignment]

        time_diff_min: Optional[float] = None
        if ts is not None:
            time_diff_min = abs((entry_dt - ts).total_seconds()) / 60.0

        price_diff_pct: Optional[float] = None
        try:
            sp_val = float(signal_price)
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
            best_pick_uuid = str(pick_uuid)

    if best_pick_uuid is None:
        return None

    try:
        exit_price = float(exit_data.get("exit_price"))
    except Exception:
        exit_price = None  # type: ignore[assignment]

    try:
        ret_close_pct = float(exit_data.get("return_pct"))
    except Exception:
        ret_close_pct = None  # type: ignore[assignment]

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
    """Compute simple EOD outcomes for all picks on a given trade_date.

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

    conn = sqlite3.connect(_DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT pick_uuid, symbol, direction, signal_price, signal_ts, trade_date,
               recommended_target, recommended_stop
        FROM pick_events
        WHERE trade_date = ?
        """,
        (trade_date.isoformat(),),
    )
    rows = cursor.fetchall()
    conn.close()

    processed = 0

    for (
        pick_uuid,
        symbol,
        direction,
        signal_price,
        signal_ts_str,
        trade_date_str,
        rec_target,
        rec_stop,
    ) in rows:
        # Skip if an outcome already exists for this horizon
        conn = sqlite3.connect(_DB_PATH)
        c2 = conn.cursor()
        c2.execute(
            "SELECT 1 FROM pick_outcomes WHERE pick_uuid = ? AND evaluation_horizon = ? LIMIT 1",
            (pick_uuid, evaluation_horizon),
        )
        already = c2.fetchone()
        conn.close()
        if already:
            continue

        try:
            data = await chart_data_service.fetch_chart_data(symbol, "1D")
        except Exception as e:
            try:
                print(f"[PickLogger] Failed to fetch chart data for {symbol}: {e}")
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
                if dt_ist.date().isoformat() == trade_date_str:
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
            sp = float(signal_price)
            if sp <= 0:
                continue
        except Exception:
            continue

        sign = 1.0 if str(direction).upper() == "LONG" else -1.0

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
            if rec_target is not None:
                t_val = float(rec_target)
                if sign > 0:
                    hit_target = any(float(c.get("high", 0.0)) >= t_val for c in candles_for_day)
                else:
                    hit_target = any(float(c.get("low", 0.0)) <= t_val for c in candles_for_day)
        except Exception:
            hit_target = None

        try:
            if rec_stop is not None:
                s_val = float(rec_stop)
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
            pick_uuid=pick_uuid,
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
    """Create a new RL policy row and return its policy_id."""

    policy_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    now_iso = _to_iso(now)

    try:
        config_json = json.dumps(config or {}, default=str)
    except Exception:
        config_json = "{}"

    conn = sqlite3.connect(_DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO rl_policies (
            policy_id,
            name,
            description,
            created_at,
            updated_at,
            status,
            config_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            policy_id,
            name,
            description,
            now_iso,
            now_iso,
            status,
            config_json,
        ),
    )
    conn.commit()
    conn.close()
    return policy_id


def set_active_rl_policy(policy_id: str) -> None:
    """Mark a policy as ACTIVE and retire any currently active one."""

    now_iso = _to_iso(datetime.now(timezone.utc))

    conn = sqlite3.connect(_DB_PATH)
    cursor = conn.cursor()

    # Retire existing active policies
    cursor.execute(
        """
        UPDATE rl_policies
        SET status = 'RETIRED', deactivated_at = ?
        WHERE status = 'ACTIVE'
        """,
        (now_iso,),
    )

    # Activate the requested policy
    cursor.execute(
        """
        UPDATE rl_policies
        SET status = 'ACTIVE', activated_at = ?, updated_at = ?
        WHERE policy_id = ?
        """,
        (now_iso, now_iso, policy_id),
    )

    conn.commit()
    conn.close()


def get_active_rl_policy() -> Optional[Dict[str, Any]]:
    """Return the currently ACTIVE RL policy config, if any."""

    conn = sqlite3.connect(_DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT policy_id, name, description, status, config_json, metrics_json,
               created_at, updated_at, activated_at, deactivated_at
        FROM rl_policies
        WHERE status = 'ACTIVE'
        ORDER BY activated_at DESC
        LIMIT 1
        """
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    (
        policy_id,
        name,
        description,
        status,
        config_json,
        metrics_json,
        created_at,
        updated_at,
        activated_at,
        deactivated_at,
    ) = row

    try:
        config = json.loads(config_json or "{}")
    except Exception:
        config = {}

    try:
        metrics = json.loads(metrics_json) if metrics_json else None
    except Exception:
        metrics = None

    return {
        "policy_id": policy_id,
        "name": name,
        "description": description,
        "status": status,
        "config": config,
        "metrics": metrics,
        "created_at": created_at,
        "updated_at": updated_at,
        "activated_at": activated_at,
        "deactivated_at": deactivated_at,
    }


async def evaluate_exit_profiles_for_mode(
    *,
    policy_id: str,
    mode: str,
    start_date: date,
    end_date: date,
    timeframe: str = "1D",
    evaluation_horizon: str = "EOD",
) -> None:
    """Evaluate all configured exit profiles for a mode and persist metrics.

    This reads rl_policies.config_json.modes[mode].exits.profiles, runs
    ExitPolicyEvaluator over the requested date range, and writes into
    metrics_json.exit_profiles[mode] and best_exit_profiles[mode].
    """

    mode_key = str(mode)

    try:
        conn = sqlite3.connect(_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT config_json, metrics_json FROM rl_policies WHERE policy_id = ?",
            (policy_id,),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return

        config_json, metrics_json_str = row
        try:
            config = json.loads(config_json or "{}")
        except Exception:
            config = {}

        try:
            metrics = json.loads(metrics_json_str) if metrics_json_str else {}
        except Exception:
            metrics = {}

        modes_cfg = config.get("modes") or {}
        mode_cfg = modes_cfg.get(mode_key) or modes_cfg.get(mode_key.lower()) or {}
        exits_cfg = mode_cfg.get("exits") or {}
        profiles = exits_cfg.get("profiles") or {}
        if not isinstance(profiles, dict) or not profiles:
            conn.close()
            return

        from .exit_policy_evaluator import ExitPolicyEvaluator

        evaluator = ExitPolicyEvaluator(_DB_PATH)

        profiling_results: Dict[str, Dict[str, Any]] = {}
        best_id: Optional[str] = None
        best_score: Optional[float] = None

        for profile_id, profile_cfg in profiles.items():
            try:
                eval_res = await evaluator.evaluate_profile_for_picks(
                    exit_profile=profile_cfg,
                    start_date=start_date,
                    end_date=end_date,
                    mode=mode_key,
                    timeframe=timeframe,
                    evaluation_horizon=evaluation_horizon,
                )
            except Exception:
                continue

            trades = int(eval_res.get("trades") or 0)
            avg_ret = float(eval_res.get("avg_ret_close_pct") or 0.0)
            avg_dd = float(eval_res.get("avg_max_drawdown_pct") or 0.0)
            win_rate = float(eval_res.get("win_rate") or 0.0)
            results_list = eval_res.get("results") or []

            if trades <= 0:
                profiling_results[profile_id] = {
                    "trades": 0,
                    "avg_ret_close_pct": 0.0,
                    "avg_max_drawdown_pct": 0.0,
                    "win_rate": 0.0,
                    "hit_target_rate": 0.0,
                    "hit_stop_rate": 0.0,
                    "avg_capture_ratio": 0.0,
                    "score": 0.0,
                }
                continue

            hit_target_count = 0
            hit_stop_count = 0
            capture_sum = 0.0

            for r in results_list:
                try:
                    if r.get("hit_target"):
                        hit_target_count += 1
                    if r.get("hit_stop"):
                        hit_stop_count += 1

                    max_runup = float(r.get("max_runup_pct") or 0.0)
                    ret_close = float(r.get("ret_close_pct") or 0.0)
                    if max_runup > 0 and ret_close > 0:
                        ratio = ret_close / max_runup
                        if ratio < 0:
                            ratio = 0.0
                        if ratio > 1:
                            ratio = 1.0
                        capture_sum += ratio
                except Exception:
                    continue

            hit_target_rate = hit_target_count / trades if trades > 0 else 0.0
            hit_stop_rate = hit_stop_count / trades if trades > 0 else 0.0
            avg_capture_ratio = capture_sum / trades if trades > 0 else 0.0

            # Simple composite score balancing return, capture quality,
            # drawdown, and stop-out frequency.
            w_ret = 1.0
            w_cap = 0.5
            w_dd = -0.5
            w_stop = -0.3

            score = (
                w_ret * avg_ret
                + w_cap * avg_capture_ratio
                + w_dd * avg_dd
                + w_stop * hit_stop_rate * 100.0
            )

            profiling_results[profile_id] = {
                "trades": trades,
                "avg_ret_close_pct": avg_ret,
                "avg_max_drawdown_pct": avg_dd,
                "win_rate": win_rate,
                "hit_target_rate": hit_target_rate,
                "hit_stop_rate": hit_stop_rate,
                "avg_capture_ratio": avg_capture_ratio,
                "score": score,
            }

            if best_score is None or score > best_score:
                best_score = score
                best_id = profile_id

        # If nothing evaluated successfully, do not overwrite metrics.
        if not profiling_results:
            conn.close()
            return

        if not isinstance(metrics, dict):
            metrics = {}

        metrics.setdefault("exit_profiles", {})
        metrics["exit_profiles"][mode_key] = profiling_results

        metrics.setdefault("best_exit_profiles", {})
        if best_id is not None:
            metrics["best_exit_profiles"][mode_key] = {
                "id": best_id,
                "criterion": "score",
            }

        metrics.setdefault("last_evaluated_at_by_mode", {})
        metrics["last_evaluated_at_by_mode"][mode_key] = _to_iso(datetime.now(timezone.utc))
        metrics.setdefault("sample_by_mode", {})
        metrics["sample_by_mode"][mode_key] = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "mode": mode_key,
            "evaluation_horizon": evaluation_horizon,
            "timeframe": timeframe,
        }

        try:
            metrics_json_out = json.dumps(metrics, default=str)
        except Exception:
            metrics_json_out = None

        now_iso = _to_iso(datetime.now(timezone.utc))
        cursor.execute(
            "UPDATE rl_policies SET metrics_json = ?, updated_at = ? WHERE policy_id = ?",
            (metrics_json_out, now_iso, policy_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        try:
            print(
                f"[RL] Failed to evaluate exit profiles for policy {policy_id} "
                f"mode={mode_key}: {e}"
            )
        except Exception:
            pass


async def evaluate_scalping_exit_profiles_for_policy(
    policy_id: str,
    start_date: date,
    end_date: date,
) -> None:
    """Backward-compatible helper that delegates to evaluate_exit_profiles_for_mode.

    Kept for existing callers; uses mode="Scalping", timeframe="1D", and
    evaluation_horizon="SCALPING" for historical scalping exits.
    """

    await evaluate_exit_profiles_for_mode(
        policy_id=policy_id,
        mode="Scalping",
        start_date=start_date,
        end_date=end_date,
        timeframe="1D",
        evaluation_horizon="SCALPING",
    )


async def update_scalping_bandit_from_realized_picks(
    *,
    policy_id: str,
    start_date: date,
    end_date: date,
) -> None:
    """Update metrics.bandit.Scalping.contexts from realised scalping picks.

    This trainer helper reads pick_events and pick_outcomes for Scalping mode
    with evaluation_horizon="SCALPING", derives bandit_ctx and
    exit_profile_id from extra_context, computes a scalar reward per pick,
    and performs an incremental mean update of Q-values per (ctx, action).
    """

    try:
        conn = sqlite3.connect(_DB_PATH)
        cursor = conn.cursor()

        # Load existing metrics_json for the policy.
        cursor.execute(
            "SELECT metrics_json FROM rl_policies WHERE policy_id = ?",
            (policy_id,),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return

        metrics_json_str = row[0]
        try:
            metrics = json.loads(metrics_json_str) if metrics_json_str else {}
        except Exception:
            metrics = {}

        if not isinstance(metrics, dict):
            metrics = {}

        bandit_all = metrics.get("bandit") or {}
        if not isinstance(bandit_all, dict):
            bandit_all = {}

        scalp_bandit = bandit_all.get("Scalping") or {}
        if not isinstance(scalp_bandit, dict):
            scalp_bandit = {}

        contexts = scalp_bandit.get("contexts") or {}
        if not isinstance(contexts, dict):
            contexts = {}

        # Helper to compute a bounded reward from realised trade metrics.
        def _clamp(x: float, lo: float, hi: float) -> float:
            return lo if x < lo else hi if x > hi else x

        def _compute_reward(
            ret_close_pct: Optional[float],
            max_runup_pct: Optional[float],
            max_drawdown_pct: Optional[float],
            hit_stop: Optional[bool],
            capture_ratio: Optional[float],
        ) -> Optional[float]:
            try:
                r = float(ret_close_pct) if ret_close_pct is not None else 0.0
            except Exception:
                r = 0.0
            try:
                dd = float(max_drawdown_pct) if max_drawdown_pct is not None else 0.0
            except Exception:
                dd = 0.0
            try:
                cap = float(capture_ratio) if capture_ratio is not None else 0.0
            except Exception:
                cap = 0.0

            base_ret = _clamp(r / 2.0, -1.0, 1.0)  # +/-2% → +/-1
            dd_pen = _clamp(max(0.0, -dd) / 4.0, 0.0, 1.0)  # -4% DD → 1
            stop_pen = 1.0 if hit_stop else 0.0

            reward = 0.5 * base_ret + 0.3 * cap - 0.1 * dd_pen - 0.1 * stop_pen
            return float(_clamp(reward, -1.5, 1.5))

        # Fetch realised scalping picks with outcomes in the date range.
        cursor.execute(
            """
            SELECT e.extra_context,
                   o.ret_close_pct,
                   o.max_runup_pct,
                   o.max_drawdown_pct,
                   o.hit_stop,
                   o.hit_target,
                   o.notes
            FROM pick_events e
            JOIN pick_outcomes o
              ON e.pick_uuid = o.pick_uuid
            WHERE e.mode = 'Scalping'
              AND o.evaluation_horizon = 'SCALPING'
              AND e.trade_date >= ? AND e.trade_date <= ?
            """,
            (start_date.isoformat(), end_date.isoformat()),
        )
        rows = cursor.fetchall()

        for (
            extra_context_json,
            ret_close_pct,
            max_runup_pct,
            max_drawdown_pct,
            hit_stop,
            _hit_target,
            notes,
        ) in rows:
            try:
                extra_ctx = json.loads(extra_context_json or "{}")
            except Exception:
                extra_ctx = {}

            if not isinstance(extra_ctx, dict):
                continue

            action = extra_ctx.get("exit_profile_id")
            if not action:
                continue
            action = str(action)

            ctx = extra_ctx.get("bandit_ctx")
            if not ctx:
                regime_bucket = extra_ctx.get("regime_bucket", "Unknown")
                vol_bucket = extra_ctx.get("vol_bucket", "Unknown")
                user_risk_bucket = extra_ctx.get("user_risk_bucket", "Moderate")
                ctx = f"Scalping|{regime_bucket}|{vol_bucket}|{user_risk_bucket}"

            # Extract capture_ratio from notes JSON when present.
            capture_ratio: Optional[float] = None
            if notes:
                try:
                    n_obj = json.loads(notes)
                    if isinstance(n_obj, dict) and "capture_ratio" in n_obj:
                        capture_ratio = float(n_obj.get("capture_ratio") or 0.0)
                except Exception:
                    capture_ratio = None

            reward = _compute_reward(
                ret_close_pct=ret_close_pct,
                max_runup_pct=max_runup_pct,
                max_drawdown_pct=max_drawdown_pct,
                hit_stop=bool(hit_stop) if hit_stop is not None else False,
                capture_ratio=capture_ratio,
            )
            if reward is None:
                continue

            ctx_state = contexts.get(ctx)
            if not isinstance(ctx_state, dict):
                ctx_state = {"actions": {}}
                contexts[ctx] = ctx_state

            actions_state = ctx_state.get("actions") or {}
            if not isinstance(actions_state, dict):
                actions_state = {}
            action_state = actions_state.get(action) or {}
            try:
                n_old = int(action_state.get("n") or 0)
            except Exception:
                n_old = 0
            try:
                q_old = float(action_state.get("q") or 0.0)
            except Exception:
                q_old = 0.0

            n_new = n_old + 1
            q_new = q_old + (reward - q_old) / float(n_new)

            action_state = {
                "n": n_new,
                "q": q_new,
                "last_update": _to_iso(datetime.now(timezone.utc)),
            }
            actions_state[action] = action_state
            ctx_state["actions"] = actions_state
            contexts[ctx] = ctx_state

        # Persist updated bandit state back into metrics_json.
        scalp_bandit["contexts"] = contexts
        bandit_all["Scalping"] = scalp_bandit
        metrics["bandit"] = bandit_all

        try:
            metrics_out = json.dumps(metrics, default=str)
        except Exception:
            metrics_out = None

        now_iso = _to_iso(datetime.now(timezone.utc))
        cursor.execute(
            "UPDATE rl_policies SET metrics_json = ?, updated_at = ? WHERE policy_id = ?",
            (metrics_out, now_iso, policy_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        try:
            print(f"[RL][Bandit] Failed to update Scalping bandit state for {policy_id}: {e}")
        except Exception:
            pass


async def update_scalping_entry_bandit_from_realized_picks(
    *,
    policy_id: str,
    start_date: date,
    end_date: date,
) -> None:
    """Update metrics.entry_bandit.Scalping.contexts from realised scalping picks.

    This trainer helper reads pick_events and pick_outcomes for Scalping mode
    using a chosen evaluation horizon (typically "EOD" for entry quality),
    derives bandit_ctx and entry_action_id from extra_context, computes a
    scalar reward per pick, and performs an incremental mean update of
    Q-values per (ctx, action) for the entry bandit.
    """

    evaluation_horizon = "EOD"

    try:
        conn = sqlite3.connect(_DB_PATH)
        cursor = conn.cursor()

        # Load existing metrics_json for the policy.
        cursor.execute(
            "SELECT metrics_json FROM rl_policies WHERE policy_id = ?",
            (policy_id,),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return

        metrics_json_str = row[0]
        try:
            metrics = json.loads(metrics_json_str) if metrics_json_str else {}
        except Exception:
            metrics = {}

        if not isinstance(metrics, dict):
            metrics = {}

        entry_all = metrics.get("entry_bandit") or {}
        if not isinstance(entry_all, dict):
            entry_all = {}

        scalping_entry = entry_all.get("Scalping") or {}
        if not isinstance(scalping_entry, dict):
            scalping_entry = {}

        contexts = scalping_entry.get("contexts") or {}
        if not isinstance(contexts, dict):
            contexts = {}

        def _clamp(x: float, lo: float, hi: float) -> float:
            return lo if x < lo else hi if x > hi else x

        def _compute_reward(
            ret_close_pct: Optional[float],
            max_drawdown_pct: Optional[float],
            hit_stop: Optional[bool],
        ) -> Optional[float]:
            try:
                r = float(ret_close_pct) if ret_close_pct is not None else 0.0
            except Exception:
                r = 0.0
            try:
                dd = float(max_drawdown_pct) if max_drawdown_pct is not None else 0.0
            except Exception:
                dd = 0.0

            base_ret = _clamp(r / 2.0, -1.0, 1.0)
            dd_pen = _clamp(max(0.0, -dd) / 4.0, 0.0, 1.0)
            stop_pen = 1.0 if hit_stop else 0.0

            reward = 0.6 * base_ret - 0.2 * dd_pen - 0.2 * stop_pen
            return float(_clamp(reward, -1.5, 1.5))

        cursor.execute(
            """
            SELECT e.extra_context,
                   o.ret_close_pct,
                   o.max_drawdown_pct,
                   o.hit_stop
            FROM pick_events e
            JOIN pick_outcomes o
              ON e.pick_uuid = o.pick_uuid
            WHERE e.mode = 'Scalping'
              AND o.evaluation_horizon = ?
              AND e.trade_date >= ? AND e.trade_date <= ?
            """,
            (evaluation_horizon, start_date.isoformat(), end_date.isoformat()),
        )
        rows = cursor.fetchall()

        for (
            extra_context_json,
            ret_close_pct,
            max_drawdown_pct,
            hit_stop,
        ) in rows:
            try:
                extra_ctx = json.loads(extra_context_json or "{}")
            except Exception:
                extra_ctx = {}

            if not isinstance(extra_ctx, dict):
                continue

            action = extra_ctx.get("entry_action_id")
            if not action:
                continue
            action = str(action)

            ctx = extra_ctx.get("bandit_ctx")
            if not ctx:
                regime_bucket = extra_ctx.get("regime_bucket", "Unknown")
                vol_bucket = extra_ctx.get("vol_bucket", "Unknown")
                user_risk_bucket = extra_ctx.get("user_risk_bucket", "Moderate")
                ctx = f"Scalping|{regime_bucket}|{vol_bucket}|{user_risk_bucket}"

            reward = _compute_reward(
                ret_close_pct=ret_close_pct,
                max_drawdown_pct=max_drawdown_pct,
                hit_stop=bool(hit_stop) if hit_stop is not None else False,
            )
            if reward is None:
                continue

            ctx_state = contexts.get(ctx)
            if not isinstance(ctx_state, dict):
                ctx_state = {"actions": {}}
                contexts[ctx] = ctx_state

            actions_state = ctx_state.get("actions") or {}
            if not isinstance(actions_state, dict):
                actions_state = {}
            action_state = actions_state.get(action) or {}
            try:
                n_old = int(action_state.get("n") or 0)
            except Exception:
                n_old = 0
            try:
                q_old = float(action_state.get("q") or 0.0)
            except Exception:
                q_old = 0.0

            n_new = n_old + 1
            q_new = q_old + (reward - q_old) / float(n_new)

            action_state = {
                "n": n_new,
                "q": q_new,
                "last_update": _to_iso(datetime.now(timezone.utc)),
            }
            actions_state[action] = action_state
            ctx_state["actions"] = actions_state
            contexts[ctx] = ctx_state

        scalping_entry["contexts"] = contexts
        entry_all["Scalping"] = scalping_entry
        metrics["entry_bandit"] = entry_all

        try:
            metrics_out = json.dumps(metrics, default=str)
        except Exception:
            metrics_out = None

        now_iso = _to_iso(datetime.now(timezone.utc))
        cursor.execute(
            "UPDATE rl_policies SET metrics_json = ?, updated_at = ? WHERE policy_id = ?",
            (metrics_out, now_iso, policy_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        try:
            print(f"[RL][Bandit][Entry] Failed to update Scalping entry bandit state for {policy_id}: {e}")
        except Exception:
            pass


async def update_intraday_bandit_from_realized_picks(
    *,
    policy_id: str,
    start_date: date,
    end_date: date,
) -> None:
    """Update metrics.bandit.Intraday.contexts from realised Intraday picks.

    This mirrors update_scalping_bandit_from_realized_picks but operates on
    Intraday mode with evaluation_horizon="EOD" and uses a richer context
    key that incorporates session_segment and value_bucket where available:

        "Intraday|{regime_bucket}|{vol_bucket}|{user_risk_bucket}|
         {session_segment}|{value_bucket}"
    """

    try:
        conn = sqlite3.connect(_DB_PATH)
        cursor = conn.cursor()

        # Load existing metrics_json for the policy.
        cursor.execute(
            "SELECT metrics_json FROM rl_policies WHERE policy_id = ?",
            (policy_id,),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return

        metrics_json_str = row[0]
        try:
            metrics = json.loads(metrics_json_str) if metrics_json_str else {}
        except Exception:
            metrics = {}

        if not isinstance(metrics, dict):
            metrics = {}

        bandit_all = metrics.get("bandit") or {}
        if not isinstance(bandit_all, dict):
            bandit_all = {}

        intraday_bandit = bandit_all.get("Intraday") or {}
        if not isinstance(intraday_bandit, dict):
            intraday_bandit = {}

        contexts = intraday_bandit.get("contexts") or {}
        if not isinstance(contexts, dict):
            contexts = {}

        # Helper to compute a bounded reward from realised trade metrics.
        def _clamp(x: float, lo: float, hi: float) -> float:
            return lo if x < lo else hi if x > hi else x

        def _compute_reward(
            ret_close_pct: Optional[float],
            max_runup_pct: Optional[float],
            max_drawdown_pct: Optional[float],
            hit_stop: Optional[bool],
            capture_ratio: Optional[float],
        ) -> Optional[float]:
            try:
                r = float(ret_close_pct) if ret_close_pct is not None else 0.0
            except Exception:
                r = 0.0
            try:
                dd = float(max_drawdown_pct) if max_drawdown_pct is not None else 0.0
            except Exception:
                dd = 0.0
            try:
                cap = float(capture_ratio) if capture_ratio is not None else 0.0
            except Exception:
                cap = 0.0

            base_ret = _clamp(r / 2.0, -1.0, 1.0)
            dd_pen = _clamp(max(0.0, -dd) / 4.0, 0.0, 1.0)
            stop_pen = 1.0 if hit_stop else 0.0

            reward = 0.5 * base_ret + 0.3 * cap - 0.1 * dd_pen - 0.1 * stop_pen
            return float(_clamp(reward, -1.5, 1.5))

        # Fetch realised Intraday picks with outcomes in the date range.
        cursor.execute(
            """
            SELECT e.extra_context,
                   o.ret_close_pct,
                   o.max_runup_pct,
                   o.max_drawdown_pct,
                   o.hit_stop,
                   o.hit_target,
                   o.notes
            FROM pick_events e
            JOIN pick_outcomes o
              ON e.pick_uuid = o.pick_uuid
            WHERE e.mode = 'Intraday'
              AND o.evaluation_horizon = 'EOD'
              AND e.trade_date >= ? AND e.trade_date <= ?
            """,
            (start_date.isoformat(), end_date.isoformat()),
        )
        rows = cursor.fetchall()

        for (
            extra_context_json,
            ret_close_pct,
            max_runup_pct,
            max_drawdown_pct,
            hit_stop,
            _hit_target,
            notes,
        ) in rows:
            try:
                extra_ctx = json.loads(extra_context_json or "{}")
            except Exception:
                extra_ctx = {}

            if not isinstance(extra_ctx, dict):
                continue

            action = extra_ctx.get("exit_profile_id")
            if not action:
                continue
            action = str(action)

            # Build an Intraday-specific context key incorporating
            # regime/vol/risk plus session_segment and value_bucket.
            regime_bucket = extra_ctx.get("regime_bucket", "Unknown")
            vol_bucket = extra_ctx.get("vol_bucket", "Unknown")
            user_risk_bucket = extra_ctx.get("user_risk_bucket", "Moderate")
            session_segment = extra_ctx.get("session_segment") or "Unknown"
            value_bucket = extra_ctx.get("value_bucket") or "Unknown"
            ctx = (
                f"Intraday|{regime_bucket}|{vol_bucket}|{user_risk_bucket}|"
                f"{session_segment}|{value_bucket}"
            )

            # Extract capture_ratio from notes JSON when present.
            capture_ratio: Optional[float] = None
            if notes:
                try:
                    n_obj = json.loads(notes)
                    if isinstance(n_obj, dict) and "capture_ratio" in n_obj:
                        capture_ratio = float(n_obj.get("capture_ratio") or 0.0)
                except Exception:
                    capture_ratio = None

            reward = _compute_reward(
                ret_close_pct=ret_close_pct,
                max_runup_pct=max_runup_pct,
                max_drawdown_pct=max_drawdown_pct,
                hit_stop=bool(hit_stop) if hit_stop is not None else False,
                capture_ratio=capture_ratio,
            )
            if reward is None:
                continue

            ctx_state = contexts.get(ctx)
            if not isinstance(ctx_state, dict):
                ctx_state = {"actions": {}}
                contexts[ctx] = ctx_state

            actions_state = ctx_state.get("actions") or {}
            if not isinstance(actions_state, dict):
                actions_state = {}
            action_state = actions_state.get(action) or {}
            try:
                n_old = int(action_state.get("n") or 0)
            except Exception:
                n_old = 0
            try:
                q_old = float(action_state.get("q") or 0.0)
            except Exception:
                q_old = 0.0

            n_new = n_old + 1
            q_new = q_old + (reward - q_old) / float(n_new)

            action_state = {
                "n": n_new,
                "q": q_new,
                "last_update": _to_iso(datetime.now(timezone.utc)),
            }
            actions_state[action] = action_state
            ctx_state["actions"] = actions_state
            contexts[ctx] = ctx_state

        # Persist updated bandit state back into metrics_json.
        intraday_bandit["contexts"] = contexts
        bandit_all["Intraday"] = intraday_bandit
        metrics["bandit"] = bandit_all

        try:
            metrics_out = json.dumps(metrics, default=str)
        except Exception:
            metrics_out = None

        now_iso = _to_iso(datetime.now(timezone.utc))
        cursor.execute(
            "UPDATE rl_policies SET metrics_json = ?, updated_at = ? WHERE policy_id = ?",
            (metrics_out, now_iso, policy_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        try:
            print(f"[RL][Bandit] Failed to update Intraday bandit state for {policy_id}: {e}")
        except Exception:
            pass


async def update_intraday_entry_bandit_from_realized_picks(
    *,
    policy_id: str,
    start_date: date,
    end_date: date,
) -> None:
    """Update metrics.entry_bandit.Intraday.contexts from realised Intraday picks.

    This mirrors update_scalping_entry_bandit_from_realized_picks but operates
    on Intraday mode and uses evaluation_horizon="EOD". The context key
    focuses on the same coarse market buckets used online by the entry
    bandit, while session_segment and value_bucket remain available in
    extra_context for analysis:

        "Intraday|{regime_bucket}|{vol_bucket}|{user_risk_bucket}"
    """

    evaluation_horizon = "EOD"

    try:
        conn = sqlite3.connect(_DB_PATH)
        cursor = conn.cursor()

        # Load existing metrics_json for the policy.
        cursor.execute(
            "SELECT metrics_json FROM rl_policies WHERE policy_id = ?",
            (policy_id,),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return

        metrics_json_str = row[0]
        try:
            metrics = json.loads(metrics_json_str) if metrics_json_str else {}
        except Exception:
            metrics = {}

        if not isinstance(metrics, dict):
            metrics = {}

        entry_all = metrics.get("entry_bandit") or {}
        if not isinstance(entry_all, dict):
            entry_all = {}

        intraday_entry = entry_all.get("Intraday") or {}
        if not isinstance(intraday_entry, dict):
            intraday_entry = {}

        contexts = intraday_entry.get("contexts") or {}
        if not isinstance(contexts, dict):
            contexts = {}

        def _clamp(x: float, lo: float, hi: float) -> float:
            return lo if x < lo else hi if x > hi else x

        def _compute_reward(
            ret_close_pct: Optional[float],
            max_drawdown_pct: Optional[float],
            hit_stop: Optional[bool],
        ) -> Optional[float]:
            try:
                r = float(ret_close_pct) if ret_close_pct is not None else 0.0
            except Exception:
                r = 0.0
            try:
                dd = float(max_drawdown_pct) if max_drawdown_pct is not None else 0.0
            except Exception:
                dd = 0.0

            base_ret = _clamp(r / 2.0, -1.0, 1.0)
            dd_pen = _clamp(max(0.0, -dd) / 4.0, 0.0, 1.0)
            stop_pen = 1.0 if hit_stop else 0.0

            reward = 0.6 * base_ret - 0.2 * dd_pen - 0.2 * stop_pen
            return float(_clamp(reward, -1.5, 1.5))

        cursor.execute(
            """
            SELECT e.extra_context,
                   o.ret_close_pct,
                   o.max_drawdown_pct,
                   o.hit_stop
            FROM pick_events e
            JOIN pick_outcomes o
              ON e.pick_uuid = o.pick_uuid
            WHERE e.mode = 'Intraday'
              AND o.evaluation_horizon = ?
              AND e.trade_date >= ? AND e.trade_date <= ?
            """,
            (evaluation_horizon, start_date.isoformat(), end_date.isoformat()),
        )
        rows = cursor.fetchall()

        for (
            extra_context_json,
            ret_close_pct,
            max_drawdown_pct,
            hit_stop,
        ) in rows:
            try:
                extra_ctx = json.loads(extra_context_json or "{}")
            except Exception:
                extra_ctx = {}

            if not isinstance(extra_ctx, dict):
                continue

            action = extra_ctx.get("entry_action_id")
            if not action:
                continue
            action = str(action)

            # Entry bandit context focuses on the coarse market buckets used
            # at selection time. Finer-grained fields like session_segment and
            # value_bucket are still available in extra_context for analysis.
            regime_bucket = extra_ctx.get("regime_bucket", "Unknown")
            vol_bucket = extra_ctx.get("vol_bucket", "Unknown")
            user_risk_bucket = extra_ctx.get("user_risk_bucket", "Moderate")
            ctx = f"Intraday|{regime_bucket}|{vol_bucket}|{user_risk_bucket}"

            reward = _compute_reward(
                ret_close_pct=ret_close_pct,
                max_drawdown_pct=max_drawdown_pct,
                hit_stop=bool(hit_stop) if hit_stop is not None else False,
            )
            if reward is None:
                continue

            ctx_state = contexts.get(ctx)
            if not isinstance(ctx_state, dict):
                ctx_state = {"actions": {}}
                contexts[ctx] = ctx_state

            actions_state = ctx_state.get("actions") or {}
            if not isinstance(actions_state, dict):
                actions_state = {}
            action_state = actions_state.get(action) or {}
            try:
                n_old = int(action_state.get("n") or 0)
            except Exception:
                n_old = 0
            try:
                q_old = float(action_state.get("q") or 0.0)
            except Exception:
                q_old = 0.0

            n_new = n_old + 1
            q_new = q_old + (reward - q_old) / float(n_new)

            action_state = {
                "n": n_new,
                "q": q_new,
                "last_update": _to_iso(datetime.now(timezone.utc)),
            }
            actions_state[action] = action_state
            ctx_state["actions"] = actions_state
            contexts[ctx] = ctx_state

        intraday_entry["contexts"] = contexts
        entry_all["Intraday"] = intraday_entry
        metrics["entry_bandit"] = entry_all

        try:
            metrics_out = json.dumps(metrics, default=str)
        except Exception:
            metrics_out = None

        now_iso = _to_iso(datetime.now(timezone.utc))
        cursor.execute(
            "UPDATE rl_policies SET metrics_json = ?, updated_at = ? WHERE policy_id = ?",
            (metrics_out, now_iso, policy_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        try:
            print(
                f"[RL][Bandit][Entry] Failed to update Intraday entry bandit state for {policy_id}: {e}"
            )
        except Exception:
            pass


async def _update_generic_exit_bandit_from_realized_picks(
    *,
    policy_id: str,
    start_date: date,
    end_date: date,
    mode: str,
    evaluation_horizon: str = "EOD",
) -> None:
    """Generic helper to update metrics.bandit[mode].contexts for non-Scalping modes."""

    try:
        conn = sqlite3.connect(_DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT metrics_json FROM rl_policies WHERE policy_id = ?",
            (policy_id,),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return

        metrics_json_str = row[0]
        try:
            metrics = json.loads(metrics_json_str) if metrics_json_str else {}
        except Exception:
            metrics = {}

        if not isinstance(metrics, dict):
            metrics = {}

        bandit_all = metrics.get("bandit") or {}
        if not isinstance(bandit_all, dict):
            bandit_all = {}

        mode_bandit = bandit_all.get(mode) or {}
        if not isinstance(mode_bandit, dict):
            mode_bandit = {}

        contexts = mode_bandit.get("contexts") or {}
        if not isinstance(contexts, dict):
            contexts = {}

        def _clamp(x: float, lo: float, hi: float) -> float:
            return lo if x < lo else hi if x > hi else x

        def _compute_reward(
            ret_close_pct: Optional[float],
            max_runup_pct: Optional[float],
            max_drawdown_pct: Optional[float],
            hit_stop: Optional[bool],
            capture_ratio: Optional[float],
        ) -> Optional[float]:
            try:
                r = float(ret_close_pct) if ret_close_pct is not None else 0.0
            except Exception:
                r = 0.0
            try:
                mdd = float(max_drawdown_pct) if max_drawdown_pct is not None else 0.0
            except Exception:
                mdd = 0.0
            try:
                cap = float(capture_ratio) if capture_ratio is not None else 0.0
            except Exception:
                cap = 0.0

            base_ret = _clamp(r / 2.0, -1.0, 1.0)
            dd_pen = _clamp(max(0.0, -mdd) / 4.0, 0.0, 1.0)
            stop_pen = 1.0 if hit_stop else 0.0

            reward = 0.5 * base_ret + 0.3 * cap - 0.1 * dd_pen - 0.1 * stop_pen
            return float(_clamp(reward, -1.5, 1.5))

        cursor.execute(
            """
            SELECT e.extra_context,
                   o.ret_close_pct,
                   o.max_runup_pct,
                   o.max_drawdown_pct,
                   o.hit_stop,
                   o.hit_target,
                   o.notes
            FROM pick_events e
            JOIN pick_outcomes o
              ON e.pick_uuid = o.pick_uuid
            WHERE e.mode = ?
              AND o.evaluation_horizon = ?
              AND e.trade_date >= ? AND e.trade_date <= ?
            """,
            (mode, evaluation_horizon, start_date.isoformat(), end_date.isoformat()),
        )
        rows = cursor.fetchall()

        for (
            extra_context_json,
            ret_close_pct,
            max_runup_pct,
            max_drawdown_pct,
            hit_stop,
            _hit_target,
            notes,
        ) in rows:
            try:
                extra_ctx = json.loads(extra_context_json or "{}")
            except Exception:
                extra_ctx = {}

            if not isinstance(extra_ctx, dict):
                continue

            action = extra_ctx.get("exit_profile_id")
            if not action:
                continue
            action = str(action)

            ctx = extra_ctx.get("bandit_ctx")
            if not ctx:
                regime_bucket = extra_ctx.get("regime_bucket", "Unknown")
                vol_bucket = extra_ctx.get("vol_bucket", "Unknown")
                user_risk_bucket = extra_ctx.get("user_risk_bucket", "Moderate")
                ctx = f"{mode}|{regime_bucket}|{vol_bucket}|{user_risk_bucket}"

            capture_ratio: Optional[float] = None
            if notes:
                try:
                    n_obj = json.loads(notes)
                    if isinstance(n_obj, dict) and "capture_ratio" in n_obj:
                        capture_ratio = float(n_obj.get("capture_ratio") or 0.0)
                except Exception:
                    capture_ratio = None

            reward = _compute_reward(
                ret_close_pct=ret_close_pct,
                max_runup_pct=max_runup_pct,
                max_drawdown_pct=max_drawdown_pct,
                hit_stop=bool(hit_stop) if hit_stop is not None else False,
                capture_ratio=capture_ratio,
            )
            if reward is None:
                continue

            ctx_state = contexts.get(ctx)
            if not isinstance(ctx_state, dict):
                ctx_state = {"actions": {}}
                contexts[ctx] = ctx_state

            actions_state = ctx_state.get("actions") or {}
            if not isinstance(actions_state, dict):
                actions_state = {}
            action_state = actions_state.get(action) or {}
            try:
                n_old = int(action_state.get("n") or 0)
            except Exception:
                n_old = 0
            try:
                q_old = float(action_state.get("q") or 0.0)
            except Exception:
                q_old = 0.0

            n_new = n_old + 1
            q_new = q_old + (reward - q_old) / float(n_new)

            action_state = {
                "n": n_new,
                "q": q_new,
                "last_update": _to_iso(datetime.now(timezone.utc)),
            }
            actions_state[action] = action_state
            ctx_state["actions"] = actions_state
            contexts[ctx] = ctx_state

        mode_bandit["contexts"] = contexts
        bandit_all[mode] = mode_bandit
        metrics["bandit"] = bandit_all

        try:
            metrics_out = json.dumps(metrics, default=str)
        except Exception:
            metrics_out = None

        now_iso = _to_iso(datetime.now(timezone.utc))
        cursor.execute(
            "UPDATE rl_policies SET metrics_json = ?, updated_at = ? WHERE policy_id = ?",
            (metrics_out, now_iso, policy_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        try:
            print(f"[RL][Bandit] Failed to update {mode} bandit state for {policy_id}: {e}")
        except Exception:
            pass


async def _update_generic_entry_bandit_from_realized_picks(
    *,
    policy_id: str,
    start_date: date,
    end_date: date,
    mode: str,
    evaluation_horizon: str = "EOD",
) -> None:
    """Generic helper to update metrics.entry_bandit[mode].contexts for non-Scalping modes."""

    try:
        conn = sqlite3.connect(_DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT metrics_json FROM rl_policies WHERE policy_id = ?",
            (policy_id,),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return

        metrics_json_str = row[0]
        try:
            metrics = json.loads(metrics_json_str) if metrics_json_str else {}
        except Exception:
            metrics = {}

        if not isinstance(metrics, dict):
            metrics = {}

        entry_all = metrics.get("entry_bandit") or {}
        if not isinstance(entry_all, dict):
            entry_all = {}

        mode_entry = entry_all.get(mode) or {}
        if not isinstance(mode_entry, dict):
            mode_entry = {}

        contexts = mode_entry.get("contexts") or {}
        if not isinstance(contexts, dict):
            contexts = {}

        def _clamp(x: float, lo: float, hi: float) -> float:
            return lo if x < lo else hi if x > hi else x

        def _compute_reward(
            ret_close_pct: Optional[float],
            max_drawdown_pct: Optional[float],
            hit_stop: Optional[bool],
        ) -> Optional[float]:
            try:
                r = float(ret_close_pct) if ret_close_pct is not None else 0.0
            except Exception:
                r = 0.0
            try:
                dd = float(max_drawdown_pct) if max_drawdown_pct is not None else 0.0
            except Exception:
                dd = 0.0

            base_ret = _clamp(r / 2.0, -1.0, 1.0)
            dd_pen = _clamp(max(0.0, -dd) / 4.0, 0.0, 1.0)
            stop_pen = 1.0 if hit_stop else 0.0

            reward = 0.6 * base_ret - 0.2 * dd_pen - 0.2 * stop_pen
            return float(_clamp(reward, -1.5, 1.5))

        cursor.execute(
            """
            SELECT e.extra_context,
                   o.ret_close_pct,
                   o.max_drawdown_pct,
                   o.hit_stop
            FROM pick_events e
            JOIN pick_outcomes o
              ON e.pick_uuid = o.pick_uuid
            WHERE e.mode = ?
              AND o.evaluation_horizon = ?
              AND e.trade_date >= ? AND e.trade_date <= ?
            """,
            (mode, evaluation_horizon, start_date.isoformat(), end_date.isoformat()),
        )
        rows = cursor.fetchall()

        for (
            extra_context_json,
            ret_close_pct,
            max_drawdown_pct,
            hit_stop,
        ) in rows:
            try:
                extra_ctx = json.loads(extra_context_json or "{}")
            except Exception:
                extra_ctx = {}

            if not isinstance(extra_ctx, dict):
                continue

            action = extra_ctx.get("entry_action_id")
            if not action:
                continue
            action = str(action)

            ctx = extra_ctx.get("bandit_ctx")
            if not ctx:
                regime_bucket = extra_ctx.get("regime_bucket", "Unknown")
                vol_bucket = extra_ctx.get("vol_bucket", "Unknown")
                user_risk_bucket = extra_ctx.get("user_risk_bucket", "Moderate")
                ctx = f"{mode}|{regime_bucket}|{vol_bucket}|{user_risk_bucket}"

            reward = _compute_reward(
                ret_close_pct=ret_close_pct,
                max_drawdown_pct=max_drawdown_pct,
                hit_stop=bool(hit_stop) if hit_stop is not None else False,
            )
            if reward is None:
                continue

            ctx_state = contexts.get(ctx)
            if not isinstance(ctx_state, dict):
                ctx_state = {"actions": {}}
                contexts[ctx] = ctx_state

            actions_state = ctx_state.get("actions") or {}
            if not isinstance(actions_state, dict):
                actions_state = {}
            action_state = actions_state.get(action) or {}
            try:
                n_old = int(action_state.get("n") or 0)
            except Exception:
                n_old = 0
            try:
                q_old = float(action_state.get("q") or 0.0)
            except Exception:
                q_old = 0.0

            n_new = n_old + 1
            q_new = q_old + (reward - q_old) / float(n_new)

            action_state = {
                "n": n_new,
                "q": q_new,
                "last_update": _to_iso(datetime.now(timezone.utc)),
            }
            actions_state[action] = action_state
            ctx_state["actions"] = actions_state
            contexts[ctx] = ctx_state

        mode_entry["contexts"] = contexts
        entry_all[mode] = mode_entry
        metrics["entry_bandit"] = entry_all

        try:
            metrics_out = json.dumps(metrics, default=str)
        except Exception:
            metrics_out = None

        now_iso = _to_iso(datetime.now(timezone.utc))
        cursor.execute(
            "UPDATE rl_policies SET metrics_json = ?, updated_at = ? WHERE policy_id = ?",
            (metrics_out, now_iso, policy_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        try:
            print(
                f"[RL][Bandit][Entry] Failed to update {mode} entry bandit state for {policy_id}: {e}"
            )
        except Exception:
            pass


async def run_rl_exit_trainer_for_policy(
    policy_id: Optional[str] = None,
    *,
    as_of: Optional[date] = None,
) -> Optional[str]:
    """Run exit-profile evaluations for all modes that define exits in a policy.

    This helper reads rl_policies.config_json, determines which modes have
    an "exits.profiles" block, and calls evaluate_exit_profiles_for_mode for
    each of them using per-mode evaluation settings from config["evaluation"].

    It is intended to be used by offline jobs / scripts and does not expose
    any HTTP surface by itself.
    """

    if as_of is None:
        as_of = date.today()

    # Resolve policy and config
    config: Dict[str, Any]
    resolved_policy_id: Optional[str] = policy_id

    if resolved_policy_id is None:
        active = get_active_rl_policy()
        if not active:
            return None
        resolved_policy_id = str(active.get("policy_id"))
        config = active.get("config") or {}
    else:
        conn = sqlite3.connect(_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT config_json FROM rl_policies WHERE policy_id = ?",
            (resolved_policy_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        cfg_raw = row[0]
        try:
            config = json.loads(cfg_raw or "{}")
        except Exception:
            config = {}

    if not isinstance(config, dict):
        return resolved_policy_id

    evaluation_cfg = config.get("evaluation") or {}
    modes_cfg = config.get("modes") or {}
    if not isinstance(modes_cfg, dict) or not modes_cfg:
        return resolved_policy_id

    # Evaluate each mode that has exits.profiles defined
    for mode_name, mode_cfg in modes_cfg.items():
        if not isinstance(mode_cfg, dict):
            continue

        exits_cfg = mode_cfg.get("exits") or {}
        profiles = exits_cfg.get("profiles") or {}
        if not isinstance(profiles, dict) or not profiles:
            continue

        eval_cfg = evaluation_cfg.get(mode_name) or {}
        defaults = _DEFAULT_RL_EVAL_BY_MODE.get(
            mode_name, _DEFAULT_RL_EVAL_BY_MODE["default"]
        )

        try:
            lookback_days = int(eval_cfg.get("lookback_days", defaults["lookback_days"]))
        except Exception:
            lookback_days = int(defaults["lookback_days"])
        if lookback_days <= 0:
            continue

        timeframe = str(eval_cfg.get("timeframe", defaults["timeframe"]))
        evaluation_horizon = str(
            eval_cfg.get("evaluation_horizon", defaults["evaluation_horizon"])
        )

        # Use completed sessions only: exclude the as_of date itself.
        end_date = as_of - timedelta(days=1)
        start_date = end_date - timedelta(days=lookback_days - 1)

        try:
            await evaluate_exit_profiles_for_mode(
                policy_id=resolved_policy_id,
                mode=mode_name,
                start_date=start_date,
                end_date=end_date,
                timeframe=timeframe,
                evaluation_horizon=evaluation_horizon,
            )
        except Exception as e:
            try:
                print(
                    f"[RL] Trainer failed for policy {resolved_policy_id} "
                    f"mode={mode_name}: {e}"
                )
            except Exception:
                pass

    return resolved_policy_id


async def run_rl_exit_trainer_for_active_policy(
    *,
    as_of: Optional[date] = None,
) -> Optional[str]:
    """Convenience helper to train exits for the currently ACTIVE policy."""

    return await run_rl_exit_trainer_for_policy(None, as_of=as_of)


async def run_all_rl_trainers_for_policy(
    policy_id: Optional[str] = None,
    *,
    as_of: Optional[date] = None,
) -> Optional[str]:
    """Run exit-profile and bandit trainers for Scalping and Intraday.

    This helper is intended for nightly/offline jobs. It will:

    - Resolve the target rl_policies row (or use the ACTIVE one when
      policy_id is None).
    - Run exit-profile evaluation for all modes that define
      config.modes[mode].exits.profiles via run_rl_exit_trainer_for_policy.
    - For Scalping and Intraday, run both exit-bandit and entry-bandit
      trainers over the same lookback window implied by
      _DEFAULT_RL_EVAL_BY_MODE (or config["evaluation"][mode] when
      provided).
    """

    if as_of is None:
        as_of = date.today()

    # First run exit-profile trainers; this also resolves policy/config.
    resolved_policy_id = await run_rl_exit_trainer_for_policy(policy_id, as_of=as_of)
    if not resolved_policy_id:
        return None

    # Load config to determine evaluation windows.
    conn = sqlite3.connect(_DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT config_json FROM rl_policies WHERE policy_id = ?",
        (resolved_policy_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return resolved_policy_id

    cfg_raw = row[0]
    try:
        config = json.loads(cfg_raw or "{}")
    except Exception:
        config = {}

    if not isinstance(config, dict):
        return resolved_policy_id

    evaluation_cfg = config.get("evaluation") or {}

    async def _train_for_mode(mode_name: str) -> None:
        mode_eval_cfg = evaluation_cfg.get(mode_name) or {}
        defaults = _DEFAULT_RL_EVAL_BY_MODE.get(
            mode_name, _DEFAULT_RL_EVAL_BY_MODE["default"]
        )

        try:
            lookback_days = int(mode_eval_cfg.get("lookback_days", defaults["lookback_days"]))
        except Exception:
            lookback_days = int(defaults["lookback_days"])
        if lookback_days <= 0:
            return

        end_date = as_of - timedelta(days=1)
        start_date = end_date - timedelta(days=lookback_days - 1)

        try:
            if mode_name == "Scalping":
                await update_scalping_bandit_from_realized_picks(
                    policy_id=resolved_policy_id,
                    start_date=start_date,
                    end_date=end_date,
                )
                await update_scalping_entry_bandit_from_realized_picks(
                    policy_id=resolved_policy_id,
                    start_date=start_date,
                    end_date=end_date,
                )
            elif mode_name == "Intraday":
                await update_intraday_bandit_from_realized_picks(
                    policy_id=resolved_policy_id,
                    start_date=start_date,
                    end_date=end_date,
                )
                await update_intraday_entry_bandit_from_realized_picks(
                    policy_id=resolved_policy_id,
                    start_date=start_date,
                    end_date=end_date,
                )
            elif mode_name in ("Swing", "Options", "Futures"):
                await _update_generic_exit_bandit_from_realized_picks(
                    policy_id=resolved_policy_id,
                    start_date=start_date,
                    end_date=end_date,
                    mode=mode_name,
                )
                await _update_generic_entry_bandit_from_realized_picks(
                    policy_id=resolved_policy_id,
                    start_date=start_date,
                    end_date=end_date,
                    mode=mode_name,
                )
        except Exception as e:
            try:
                print(
                    f"[RL] Bandit trainer failed for policy {resolved_policy_id} "
                    f"mode={mode_name}: {e}"
                )
            except Exception:
                pass

    # Run bandit trainers sequentially per mode; small number so no
    # need for additional concurrency complexity here.
    for mode_name in ("Scalping", "Intraday", "Swing", "Options", "Futures"):
        await _train_for_mode(mode_name)

    return resolved_policy_id


async def run_all_rl_trainers_for_active_policy(
    *,
    as_of: Optional[date] = None,
) -> Optional[str]:
    """Convenience wrapper to run all RL trainers for the ACTIVE policy."""

    return await run_all_rl_trainers_for_policy(None, as_of=as_of)

