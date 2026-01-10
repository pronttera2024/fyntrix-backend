from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, TypedDict

from .chart_data_service import chart_data_service


class Candle(TypedDict):
    time: float  # epoch seconds (UTC)
    open: float
    high: float
    low: float
    close: float


@dataclass
class ExitSimulationResult:
    symbol: str
    pick_uuid: str
    exit_ts: datetime
    exit_price: float
    ret_close_pct: float
    max_runup_pct: float
    max_drawdown_pct: float
    hit_target: bool
    hit_stop: bool
    hit_trailing: bool
    time_exit: bool
    exit_reason: str
    bars_held: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "pick_uuid": self.pick_uuid,
            "exit_ts": self.exit_ts.isoformat().replace("+00:00", "Z"),
            "exit_price": self.exit_price,
            "ret_close_pct": self.ret_close_pct,
            "max_runup_pct": self.max_runup_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "hit_target": self.hit_target,
            "hit_stop": self.hit_stop,
            "hit_trailing": self.hit_trailing,
            "time_exit": self.time_exit,
            "exit_reason": self.exit_reason,
            "bars_held": self.bars_held,
        }


def _direction_sign(direction: str) -> float:
    return 1.0 if str(direction).upper() == "LONG" else -1.0


def simulate_exit_for_pick(
    *,
    symbol: str,
    pick_uuid: str,
    direction: Literal["LONG", "SHORT"],
    entry_price: float,
    entry_ts: datetime,
    horizon_end_ts: datetime,
    exit_profile: Dict[str, Any],
    candles: List[Candle],
) -> Optional[ExitSimulationResult]:
    """Simulate how a given exit profile would behave for a single pick.

    This is a pure function: all data (entry context, price path, profile)
    is passed in, and it returns a summary of the simulated trade.
    """

    if entry_price <= 0:
        return None

    if entry_ts.tzinfo is None:
        entry_ts = entry_ts.replace(tzinfo=timezone.utc)
    else:
        entry_ts = entry_ts.astimezone(timezone.utc)

    if horizon_end_ts.tzinfo is None:
        horizon_end_ts = horizon_end_ts.replace(tzinfo=timezone.utc)
    else:
        horizon_end_ts = horizon_end_ts.astimezone(timezone.utc)

    start_ts = entry_ts.timestamp()
    end_ts = horizon_end_ts.timestamp()

    path: List[Candle] = [
        c for c in candles
        if isinstance(c.get("time"), (int, float)) and start_ts <= float(c["time"]) <= end_ts
    ]
    if not path:
        return None

    path = sorted(path, key=lambda c: float(c["time"]))

    sign = _direction_sign(direction)

    # --- Configure stop / target from profile ---
    stop_cfg = (exit_profile.get("stop") or {}) if isinstance(exit_profile, dict) else {}
    stop_type = str(stop_cfg.get("type") or "percent")
    stop_val = float(stop_cfg.get("value") or 0.0)

    stop_price: Optional[float]
    if stop_type == "price" and stop_val > 0:
        stop_price = stop_val
    elif stop_type in ("percent", "atr_multiple") and stop_val > 0:
        # ATR-based distances are not available here yet; treat value as percent.
        dist = entry_price * (stop_val / 100.0)
        stop_price = entry_price - dist if sign > 0 else entry_price + dist
    else:
        stop_price = None

    target_cfg = (exit_profile.get("target") or {}) if isinstance(exit_profile, dict) else {}
    target_type = str(target_cfg.get("type") or "percent")
    target_val = target_cfg.get("value")
    target_price: Optional[float] = None
    if target_val is not None:
        tv = float(target_val)
        if target_type == "price" and tv > 0:
            target_price = tv
        elif target_type == "percent" and tv > 0:
            dist = entry_price * (tv / 100.0)
            target_price = entry_price + dist if sign > 0 else entry_price - dist
        elif target_type == "rr_multiple" and tv > 0 and stop_price is not None:
            stop_dist = abs(entry_price - stop_price)
            dist = stop_dist * tv
            target_price = entry_price + dist if sign > 0 else entry_price - dist

    trailing_cfg = (exit_profile.get("trailing") or {}) if isinstance(exit_profile, dict) else {}
    trailing_enabled = bool(trailing_cfg.get("enabled"))
    activation_type = str(trailing_cfg.get("activation_type") or "percent")
    activation_val = float(trailing_cfg.get("activation_value") or 0.0)
    trail_type = str(trailing_cfg.get("trail_type") or "percent")
    trail_val = float(trailing_cfg.get("trail_value") or 0.0)

    time_stop_cfg = (exit_profile.get("time_stop") or {}) if isinstance(exit_profile, dict) else {}
    time_stop_enabled = bool(time_stop_cfg.get("enabled"))
    max_hold_minutes = time_stop_cfg.get("max_hold_minutes")
    max_hold_minutes_f: Optional[float] = float(max_hold_minutes) if max_hold_minutes is not None else None

    priority_cfg = (exit_profile.get("exit_priority") or {}) if isinstance(exit_profile, dict) else {}
    order = priority_cfg.get("order") or ["STOP", "TRAIL", "TARGET", "TIME"]
    priority_order = [str(x).upper() for x in order]

    # --- Simulation state ---
    best_price = entry_price
    worst_price = entry_price
    exit_ts: Optional[datetime] = None
    exit_price: Optional[float] = None
    hit_target = False
    hit_stop = False
    hit_trailing = False
    time_exit = False
    exit_reason = "NONE"

    trailing_active = False
    trailing_stop_price: Optional[float] = None
    bars_held = 0

    for c in path:
        bars_held += 1
        t = float(c["time"])
        bar_ts = datetime.fromtimestamp(t, tz=timezone.utc)
        high = float(c["high"])
        low = float(c["low"])
        close = float(c["close"])

        if sign > 0:
            best_price = max(best_price, high)
            worst_price = min(worst_price, low)
        else:
            best_price = min(best_price, low)
            worst_price = max(worst_price, high)

        # Activate trailing based on unrealized profit
        if trailing_enabled and not trailing_active:
            if sign > 0:
                unrealized_pct = (high - entry_price) / entry_price * 100.0
            else:
                unrealized_pct = (entry_price - low) / entry_price * 100.0

            if activation_val > 0:
                if activation_type == "percent" and unrealized_pct >= activation_val:
                    trailing_active = True
                elif activation_type == "rr_multiple" and stop_price is not None:
                    stop_dist_pct = abs(entry_price - stop_price) / entry_price * 100.0
                    if stop_dist_pct > 0 and unrealized_pct / stop_dist_pct >= activation_val:
                        trailing_active = True

            if trailing_active:
                # Initialize trailing at current bar extremum
                if sign > 0:
                    if trail_type == "percent" and trail_val > 0:
                        trailing_stop_price = high * (1.0 - trail_val / 100.0)
                else:
                    if trail_type == "percent" and trail_val > 0:
                        trailing_stop_price = low * (1.0 + trail_val / 100.0)

        # Update trailing stop when active
        if trailing_active and trailing_stop_price is not None and trail_val > 0:
            if sign > 0:
                if high > best_price and trail_type == "percent":
                    trailing_stop_price = high * (1.0 - trail_val / 100.0)
            else:
                if low < best_price and trail_type == "percent":
                    trailing_stop_price = low * (1.0 + trail_val / 100.0)

        # Check exit conditions in configured priority
        for ev in priority_order:
            if ev == "STOP" and stop_price is not None:
                if (sign > 0 and low <= stop_price) or (sign < 0 and high >= stop_price):
                    exit_ts = bar_ts
                    exit_price = stop_price
                    hit_stop = True
                    exit_reason = "STOP"
                    break

            if ev == "TRAIL" and trailing_active and trailing_stop_price is not None:
                if (sign > 0 and low <= trailing_stop_price) or (sign < 0 and high >= trailing_stop_price):
                    exit_ts = bar_ts
                    exit_price = trailing_stop_price
                    hit_trailing = True
                    exit_reason = "TRAIL"
                    break

            if ev == "TARGET" and target_price is not None:
                if (sign > 0 and high >= target_price) or (sign < 0 and low <= target_price):
                    exit_ts = bar_ts
                    exit_price = target_price
                    hit_target = True
                    exit_reason = "TARGET"
                    break

            if ev == "TIME" and time_stop_enabled and max_hold_minutes_f is not None:
                minutes_held = (bar_ts - entry_ts).total_seconds() / 60.0
                if minutes_held >= max_hold_minutes_f:
                    exit_ts = bar_ts
                    exit_price = close
                    time_exit = True
                    exit_reason = "TIME"
                    break

        if exit_ts is not None:
            break

    # If no explicit exit before horizon end, exit at last bar close
    if exit_ts is None or exit_price is None:
        last = path[-1]
        t = float(last["time"])
        exit_ts = datetime.fromtimestamp(t, tz=timezone.utc)
        exit_price = float(last["close"])

    # Compute metrics
    if sign > 0:
        max_runup_pct = (best_price - entry_price) / entry_price * 100.0
        max_drawdown_pct = (worst_price - entry_price) / entry_price * 100.0
    else:
        max_runup_pct = (entry_price - best_price) / entry_price * 100.0
        max_drawdown_pct = (entry_price - worst_price) / entry_price * 100.0

    ret_close_pct = (exit_price - entry_price) / entry_price * 100.0 * sign

    return ExitSimulationResult(
        symbol=symbol,
        pick_uuid=pick_uuid,
        exit_ts=exit_ts,
        exit_price=exit_price,
        ret_close_pct=ret_close_pct,
        max_runup_pct=max_runup_pct,
        max_drawdown_pct=max_drawdown_pct,
        hit_target=hit_target,
        hit_stop=hit_stop,
        hit_trailing=hit_trailing,
        time_exit=time_exit,
        exit_reason=exit_reason,
        bars_held=bars_held,
    )


class ExitPolicyEvaluator:
    """Offline helper to evaluate exit profiles over historical picks.

    This operates directly on the pick_events / pick_outcomes tables in
    cache/ai_recommendations.db and uses ChartDataService for price paths.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "cache" / "ai_recommendations.db"
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def fetch_picks_with_outcomes(
        self,
        *,
        start_date: date,
        end_date: date,
        mode: Optional[str] = None,
        evaluation_horizon: str = "EOD",
    ) -> List[Dict[str, Any]]:
        """Return pick_events joined with pick_outcomes for a date range."""

        conn = self._connect()
        cursor = conn.cursor()
        try:
            sql = (
                "SELECT e.pick_uuid, e.symbol, e.direction, e.signal_price, e.signal_ts, "
                "e.mode, e.universe, o.horizon_end_ts "
                "FROM pick_events e "
                "LEFT JOIN pick_outcomes o ON e.pick_uuid = o.pick_uuid "
                "  AND o.evaluation_horizon = ? "
                "WHERE e.trade_date >= ? AND e.trade_date <= ?"
            )
            params: List[Any] = [evaluation_horizon, start_date.isoformat(), end_date.isoformat()]
            if mode:
                sql += " AND e.mode = ?"
                params.append(str(mode))

            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
        finally:
            conn.close()

        results: List[Dict[str, Any]] = []
        for pick_uuid, symbol, direction, signal_price, signal_ts, mode_val, universe, horizon_end_ts in rows:
            results.append(
                {
                    "pick_uuid": str(pick_uuid),
                    "symbol": str(symbol),
                    "direction": str(direction),
                    "signal_price": float(signal_price),
                    "signal_ts": str(signal_ts),
                    "mode": str(mode_val),
                    "universe": str(universe),
                    "horizon_end_ts": str(horizon_end_ts) if horizon_end_ts else None,
                }
            )
        return results

    async def evaluate_profile_for_picks(
        self,
        *,
        exit_profile: Dict[str, Any],
        start_date: date,
        end_date: date,
        mode: Optional[str] = None,
        timeframe: str = "1D",
        evaluation_horizon: str = "EOD",
    ) -> Dict[str, Any]:
        """Evaluate a single exit profile over historical picks.

        This is intentionally simple and intended for offline experimentation.
        """

        picks = self.fetch_picks_with_outcomes(
            start_date=start_date,
            end_date=end_date,
            mode=mode,
            evaluation_horizon=evaluation_horizon,
        )
        if not picks:
            return {
                "trades": 0,
                "avg_ret_close_pct": 0.0,
                "avg_max_drawdown_pct": 0.0,
                "win_rate": 0.0,
                "results": [],
            }

        # Fetch price paths per symbol once per evaluation
        symbols = sorted({p["symbol"] for p in picks})
        symbol_candles: Dict[str, List[Candle]] = {}

        for sym in symbols:
            try:
                data = await chart_data_service.fetch_chart_data(sym, timeframe)
                raw = (data or {}).get("candles") or []
                candles: List[Candle] = []
                for c in raw:
                    try:
                        candles.append(
                            Candle(
                                time=float(c.get("time")),
                                open=float(c.get("open")),
                                high=float(c.get("high")),
                                low=float(c.get("low")),
                                close=float(c.get("close")),
                            )
                        )
                    except Exception:
                        continue
                if candles:
                    symbol_candles[sym] = candles
            except Exception:
                continue

        results: List[Dict[str, Any]] = []
        total_ret = 0.0
        total_dd = 0.0
        wins = 0
        trades = 0

        for p in picks:
            sym = p["symbol"]
            candles = symbol_candles.get(sym)
            if not candles:
                continue

            try:
                entry_price = float(p["signal_price"])
            except Exception:
                continue

            try:
                entry_ts = datetime.fromisoformat(str(p["signal_ts"]).replace("Z", "+00:00"))
            except Exception:
                entry_ts = datetime.now(timezone.utc)

            horizon_raw = p.get("horizon_end_ts")
            if horizon_raw:
                try:
                    horizon_end_ts = datetime.fromisoformat(str(horizon_raw).replace("Z", "+00:00"))
                except Exception:
                    horizon_end_ts = entry_ts
            else:
                horizon_end_ts = entry_ts

            sim = simulate_exit_for_pick(
                symbol=sym,
                pick_uuid=p["pick_uuid"],
                direction="LONG" if p["direction"].upper() == "LONG" else "SHORT",
                entry_price=entry_price,
                entry_ts=entry_ts,
                horizon_end_ts=horizon_end_ts,
                exit_profile=exit_profile,
                candles=candles,
            )
            if sim is None:
                continue

            trades += 1
            total_ret += sim.ret_close_pct
            total_dd += sim.max_drawdown_pct
            if sim.ret_close_pct > 0:
                wins += 1

            results.append(sim.to_dict())

        if trades == 0:
            return {
                "trades": 0,
                "avg_ret_close_pct": 0.0,
                "avg_max_drawdown_pct": 0.0,
                "win_rate": 0.0,
                "results": [],
            }

        return {
            "trades": trades,
            "avg_ret_close_pct": total_ret / trades,
            "avg_max_drawdown_pct": total_dd / trades,
            "win_rate": wins / trades,
            "results": results,
        }
