"""Offline backtest job for ARISE Top Picks.

This module is intentionally **not** wired into any FastAPI router or
runtime service. It is meant to be invoked manually (e.g. from a script
or notebook) to compute potential P&L KPIs for historical
recommendations.

Data flow:
- Reads historical Top Picks runs from TopPicksStore (top_picks_runs.db)
- For each pick, fetches OHLC candles via chart_data_service
- Simulates three potential outcomes per pick:
  - TP1-based potential return
  - MFE-based potential return (respecting SL)
  - Ladder-exit potential return (partial exits at TP levels)
- Writes results into a dedicated SQLite database
  (cache/top_picks_backtest.db) that is not used by production flows.

This avoids any impact on live APIs or user-facing services.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .top_picks_store import get_top_picks_store
from .chart_data_service import chart_data_service
from .policy_store import get_policy_store


DB_PATH = Path("cache/top_picks_backtest.db")


@dataclass
class BacktestResult:
    symbol: str
    universe: str
    mode: str
    generated_at_utc: str
    run_id: str
    recommendation: str
    direction: str
    score_blend: float
    entry_price: float
    stop_loss_price: Optional[float]
    target_price: Optional[float]
    horizon_days: int
    potential_return_tp1: Optional[float]
    potential_return_mfe: Optional[float]
    potential_return_ladder: Optional[float]
    meta: Dict[str, Any]


class BacktestStore:
    """SQLite storage for offline Top Picks backtest results.

    Uses a dedicated DB file separate from production stores.
    """

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS picks_backtest (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                universe TEXT NOT NULL,
                mode TEXT NOT NULL,
                generated_at_utc TEXT NOT NULL,
                recommendation TEXT,
                direction TEXT,
                score_blend REAL,
                entry_price REAL,
                stop_loss_price REAL,
                target_price REAL,
                horizon_days INTEGER,
                potential_return_tp1 REAL,
                potential_return_mfe REAL,
                potential_return_ladder REAL,
                meta TEXT
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_bt_symbol_date
            ON picks_backtest (symbol, generated_at_utc DESC)
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_bt_mode_date
            ON picks_backtest (mode, generated_at_utc DESC)
            """
        )

        conn.commit()
        conn.close()

    def insert_result(self, result: BacktestResult) -> None:
        import json

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO picks_backtest (
                run_id,
                symbol,
                universe,
                mode,
                generated_at_utc,
                recommendation,
                direction,
                score_blend,
                entry_price,
                stop_loss_price,
                target_price,
                horizon_days,
                potential_return_tp1,
                potential_return_mfe,
                potential_return_ladder,
                meta
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.run_id,
                result.symbol,
                result.universe,
                result.mode,
                result.generated_at_utc,
                result.recommendation,
                result.direction,
                result.score_blend,
                result.entry_price,
                result.stop_loss_price,
                result.target_price,
                result.horizon_days,
                result.potential_return_tp1,
                result.potential_return_mfe,
                result.potential_return_ladder,
                json.dumps(result.meta or {}),
            ),
        )

        conn.commit()
        conn.close()


def _parse_iso_utc(ts: str) -> datetime:
    """Parse an ISO8601 timestamp as naive UTC datetime."""
    return datetime.fromisoformat(ts.replace("Z", ""))


def _mode_horizon_days(mode: str) -> int:
    """Get evaluation horizon (in days) for a trading mode.

    Uses PolicyStore horizons when available, with reasonable defaults.
    """
    policy_store = get_policy_store()
    mp = policy_store.get_mode_policy(mode)
    if mp.horizon_days:
        try:
            days = int(mp.horizon_days)
            if days > 0:
                return days
        except Exception:
            pass

    mode_key = (mode or "").title()
    defaults = {
        "Scalping": 1,
        "Intraday": 1,
        "Futures": 5,
        "Swing": 7,
        "Options": 5,
    }
    return defaults.get(mode_key, 5)


def _timeframe_for_horizon(days: int) -> str:
    """Map horizon (days) to chart_data_service timeframe string."""
    if days <= 1:
        return "1D"
    if days <= 7:
        return "1W"
    if days <= 30:
        return "1M"
    return "1Y"


def _direction_from_pick(pick: Dict[str, Any]) -> str:
    es = pick.get("exit_strategy") or {}
    direction = str(es.get("direction") or "").upper()
    if direction in ("LONG", "SHORT"):
        return direction

    rec = str(pick.get("recommendation") or "").lower()
    if "sell" in rec:
        return "SHORT"
    return "LONG"


def _entry_stop_target_from_pick(pick: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    es = pick.get("exit_strategy") or {}

    entry = es.get("entry_price")
    sl = es.get("stop_loss_price")
    target = es.get("target_price")

    if entry is None:
        entry = pick.get("entry_price") or pick.get("last_price") or pick.get("price")

    try:
        entry_f = float(entry) if entry is not None else None
    except Exception:
        entry_f = None

    def _to_float(val: Any) -> Optional[float]:
        if val is None:
            return None
        try:
            return float(val)
        except Exception:
            return None

    sl_f = _to_float(sl)
    target_f = _to_float(target)

    return entry_f, sl_f, target_f


def _filter_window_candles(
    candles: List[Dict[str, Any]],
    entry_ts: int,
    horizon_ts: int,
) -> List[Dict[str, Any]]:
    """Restrict candles to (entry_ts, horizon_ts]."""
    return [c for c in candles if entry_ts < int(c.get("time", 0)) <= horizon_ts]


def _simulate_tp1(
    direction: str,
    entry: float,
    sl: Optional[float],
    target: Optional[float],
    candles: List[Dict[str, Any]],
) -> Optional[float]:
    """TP1-based potential return.

    Follows a simple rule:
    - Exit at SL if hit before TP1
    - Else exit at TP1 if hit
    - Else exit at last close in window
    """
    if entry <= 0 or not candles:
        return None

    direction = direction.upper()
    sl_f = sl if sl is not None and sl > 0 else None
    target_f = target if target is not None and target > 0 else None

    exit_price: Optional[float] = None

    if direction == "LONG":
        for c in candles:
            low = float(c["low"])
            high = float(c["high"])
            if sl_f is not None and low <= sl_f:
                exit_price = sl_f
                break
            if target_f is not None and high >= target_f:
                exit_price = target_f
                break
        if exit_price is None:
            exit_price = float(candles[-1]["close"])
        return (exit_price - entry) / entry

    # SHORT
    for c in candles:
        low = float(c["low"])
        high = float(c["high"])
        if sl_f is not None and high >= sl_f:
            exit_price = sl_f
            break
        if target_f is not None and low <= target_f:
            exit_price = target_f
            break
    if exit_price is None:
        exit_price = float(candles[-1]["close"])
    return (entry - exit_price) / entry


def _simulate_mfe(
    direction: str,
    entry: float,
    sl: Optional[float],
    candles: List[Dict[str, Any]],
) -> Optional[float]:
    """MFE-based potential return (respecting SL).

    - If SL is hit, exit at SL
    - Otherwise exit at maximum favourable price within window
    """
    if entry <= 0 or not candles:
        return None

    direction = direction.upper()
    sl_f = sl if sl is not None and sl > 0 else None

    if direction == "LONG":
        max_price = entry
        for c in candles:
            low = float(c["low"])
            high = float(c["high"])
            if sl_f is not None and low <= sl_f:
                return (sl_f - entry) / entry
            if high > max_price:
                max_price = high
        return (max_price - entry) / entry

    # SHORT
    min_price = entry
    for c in candles:
        low = float(c["low"])
        high = float(c["high"])
        if sl_f is not None and high >= sl_f:
            return (entry - sl_f) / entry
        if low < min_price:
            min_price = low
    return (entry - min_price) / entry


def _derive_ladder_targets(
    direction: str,
    entry: float,
    sl: Optional[float],
    target: Optional[float],
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Derive T1/T2/T3 prices for ladder exit.

    - T1: use provided target (if any)
    - T2/T3: simple multiples of risk distance when possible
    """
    if entry <= 0:
        return None, None, None

    direction = direction.upper()
    sl_f = sl if sl is not None and sl > 0 else None
    t1 = target if target is not None and target > 0 else None

    if sl_f is None or t1 is None:
        return t1, None, None

    risk = abs(entry - sl_f)
    rr1 = abs(t1 - entry)
    if risk <= 0 or rr1 <= 0:
        return t1, None, None

    base_rr = rr1 / risk
    t2_rr = base_rr * 1.5
    t3_rr = base_rr * 2.0

    if direction == "LONG":
        t2 = entry + t2_rr * risk
        t3 = entry + t3_rr * risk
    else:
        t2 = entry - t2_rr * risk
        t3 = entry - t3_rr * risk

    return t1, t2, t3


def _simulate_ladder(
    direction: str,
    entry: float,
    sl: Optional[float],
    target: Optional[float],
    candles: List[Dict[str, Any]],
) -> Optional[float]:
    """Ladder-exit potential return with simple 50/30/20 allocation.

    - 50% at T1
    - 30% at T2
    - 20% at T3
    - SL applied to remaining size when hit
    """
    if entry <= 0 or not candles:
        return None

    direction = direction.upper()
    sl_f = sl if sl is not None and sl > 0 else None

    t1, t2, t3 = _derive_ladder_targets(direction, entry, sl_f, target)
    if t1 is None:
        # Fall back to TP1-based if we cannot derive a ladder
        return _simulate_tp1(direction, entry, sl_f, target, candles)

    remaining = 1.0
    realized_returns: List[Tuple[float, float]] = []  # (weight, return)

    def _apply_fill(weight: float, price: float) -> None:
        nonlocal remaining
        if weight <= 0 or remaining <= 0:
            return
        fill_weight = min(weight, remaining)
        if direction == "LONG":
            r = (price - entry) / entry
        else:
            r = (entry - price) / entry
        realized_returns.append((fill_weight, r))
        remaining -= fill_weight

    # Walk candles in time order
    for c in candles:
        if remaining <= 0:
            break
        low = float(c["low"])
        high = float(c["high"])

        # SL always has priority for remaining size
        if sl_f is not None:
            if direction == "LONG" and low <= sl_f:
                _apply_fill(remaining, sl_f)
                break
            if direction == "SHORT" and high >= sl_f:
                _apply_fill(remaining, sl_f)
                break

        # Take profits at targets when touched
        if direction == "LONG":
            if t1 is not None and high >= t1:
                _apply_fill(0.5, t1)
            if t2 is not None and high >= t2:
                _apply_fill(0.3, t2)
            if t3 is not None and high >= t3:
                _apply_fill(0.2, t3)
        else:
            if t1 is not None and low <= t1:
                _apply_fill(0.5, t1)
            if t2 is not None and low <= t2:
                _apply_fill(0.3, t2)
            if t3 is not None and low <= t3:
                _apply_fill(0.2, t3)

    # Any remaining size exits at final close
    if remaining > 0:
        last_close = float(candles[-1]["close"])
        _apply_fill(remaining, last_close)

    if not realized_returns:
        return None

    total_weight = sum(w for w, _ in realized_returns)
    if total_weight <= 0:
        return None

    weighted_sum = sum(w * r for w, r in realized_returns)
    return weighted_sum / total_weight


async def _backtest_pick(
    run_id: str,
    universe: str,
    mode: str,
    generated_at_utc: str,
    pick: Dict[str, Any],
    store: BacktestStore,
) -> None:
    """Backtest a single pick and persist result.

    Soft-fails on data issues; does not raise to caller.
    """
    try:
        symbol = str(pick.get("symbol") or "").upper()
        if not symbol:
            return

        direction = _direction_from_pick(pick)
        entry, sl, target = _entry_stop_target_from_pick(pick)
        if entry is None or entry <= 0:
            return

        score_blend = 0.0
        try:
            score_blend = float(pick.get("score_blend", pick.get("blend_score", 0.0)) or 0.0)
        except Exception:
            score_blend = 0.0

        recommendation = str(pick.get("recommendation") or "")

        # Time window
        run_dt = _parse_iso_utc(generated_at_utc)
        horizon_days = _mode_horizon_days(mode)
        horizon_end = run_dt + timedelta(days=horizon_days)
        entry_ts = int(run_dt.timestamp())
        horizon_ts = int(horizon_end.timestamp())

        timeframe = _timeframe_for_horizon(horizon_days)

        # Fetch candles
        try:
            chart = await chart_data_service.fetch_chart_data(symbol, timeframe)
        except Exception:
            return

        candles = chart.get("candles") or []
        if not candles:
            return

        window_candles = _filter_window_candles(candles, entry_ts, horizon_ts)
        if not window_candles:
            return

        r_tp1 = _simulate_tp1(direction, entry, sl, target, window_candles)
        r_mfe = _simulate_mfe(direction, entry, sl, window_candles)
        r_ladder = _simulate_ladder(direction, entry, sl, target, window_candles)

        meta: Dict[str, Any] = {
            "data_source": chart.get("data_source"),
            "timeframe": timeframe,
            "horizon_end_utc": horizon_end.isoformat() + "Z",
        }

        result = BacktestResult(
            symbol=symbol,
            universe=universe,
            mode=mode,
            generated_at_utc=generated_at_utc,
            run_id=run_id,
            recommendation=recommendation,
            direction=direction,
            score_blend=score_blend,
            entry_price=entry,
            stop_loss_price=sl,
            target_price=target,
            horizon_days=horizon_days,
            potential_return_tp1=r_tp1,
            potential_return_mfe=r_mfe,
            potential_return_ladder=r_ladder,
            meta=meta,
        )

        store.insert_result(result)

    except Exception:
        # Backtest is analytics-only; never break caller
        import traceback

        traceback.print_exc()


async def run_backtest_for_range(
    universe: Optional[str] = None,
    mode: Optional[str] = None,
    start_utc: Optional[str] = None,
    end_utc: Optional[str] = None,
    max_runs: int = 500,
) -> None:
    """Run offline backtest for a range of historical Top Picks runs.

    This function is safe to call from a one-off script or notebook. It does
    not affect any production tables or services.
    """
    store = BacktestStore()
    tps = get_top_picks_store()

    runs = tps.query_runs(
        universe=universe,
        mode=mode,
        start_utc=start_utc,
        end_utc=end_utc,
        limit=max_runs,
    )

    # Process from oldest to newest for reproducibility
    for run in reversed(runs):
        run_id = str(run.get("run_id") or "")
        universe_val = str(run.get("universe") or "").lower()
        mode_val = str(run.get("mode") or "").title()
        generated_at_utc = str(run.get("generated_at_utc") or datetime.utcnow().isoformat())
        payload = run.get("payload") or {}
        picks = payload.get("picks") or []

        for pick in picks:
            await _backtest_pick(run_id, universe_val, mode_val, generated_at_utc, pick, store)


def run_backtest_sync(
    universe: Optional[str] = None,
    mode: Optional[str] = None,
    start_utc: Optional[str] = None,
    end_utc: Optional[str] = None,
    max_runs: int = 500,
) -> None:
    """Synchronous helper to run the backtest job with asyncio.run()."""
    import asyncio

    asyncio.run(
        run_backtest_for_range(
            universe=universe,
            mode=mode,
            start_utc=start_utc,
            end_utc=end_utc,
            max_runs=max_runs,
        )
    )


def summarize_backtest_results(
    universe: Optional[str] = None,
    mode: Optional[str] = None,
    start_utc: Optional[str] = None,
    end_utc: Optional[str] = None,
) -> None:
    """Print average potential returns per universe/mode from backtest DB.

    This is a read-only analytics helper; it does not modify any data or
    interact with production services.
    """

    if not DB_PATH.exists():
        print(f"[backtest] No backtest DB found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    where_clauses: List[str] = []
    params: List[Any] = []

    if universe:
        where_clauses.append("universe = ?")
        params.append(str(universe).lower())

    if mode:
        where_clauses.append("mode = ?")
        params.append(str(mode).title())

    # Time filters on generated_at_utc (ISO8601 strings)
    if start_utc:
        try:
            start_dt = datetime.fromisoformat(start_utc.replace("Z", ""))
            where_clauses.append("generated_at_utc >= ?")
            params.append(start_dt.isoformat())
        except Exception:
            pass

    if end_utc:
        try:
            end_dt = datetime.fromisoformat(end_utc.replace("Z", ""))
            where_clauses.append("generated_at_utc <= ?")
            params.append(end_dt.isoformat())
        except Exception:
            pass

    where_sql = ""
    if where_clauses:
        where_sql = " WHERE " + " AND ".join(where_clauses)

    sql = (
        "SELECT universe, mode, "
        "COUNT(*) AS n, "
        "AVG(potential_return_tp1) AS avg_tp1, "
        "AVG(potential_return_mfe) AS avg_mfe, "
        "AVG(potential_return_ladder) AS avg_ladder "
        "FROM picks_backtest" + where_sql + " GROUP BY universe, mode "
        "ORDER BY universe, mode"
    )

    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("[backtest] No backtest rows match the filters.")
        return

    print("\n=== Top Picks Backtest Summary ===")
    if universe:
        print(f"Universe filter: {universe}")
    if mode:
        print(f"Mode filter: {mode}")
    if start_utc or end_utc:
        print(f"Time window: {start_utc or '-inf'} -> {end_utc or '+inf'}")
    print("(Returns shown as %; averages ignore missing values)\n")

    header = f"{'Universe':<10} {'Mode':<10} {'N':>6} {'Avg TP1%':>10} {'Avg MFE%':>10} {'Avg Ladder%':>12}"
    print(header)
    print("-" * len(header))

    for universe_val, mode_val, n, avg_tp1, avg_mfe, avg_ladder in rows:
        def _pct(x: Optional[float]) -> str:
            if x is None:
                return "   n/a"
            return f"{x * 100:8.2f}"

        line = (
            f"{universe_val:<10} {mode_val:<10} "
            f"{int(n):6d} {_pct(avg_tp1):>10} {_pct(avg_mfe):>10} {_pct(avg_ladder):>12}"
        )
        print(line)

