"""Support/Resistance (S/R) computation and caching service.

Computes pivot-based support/resistance levels (P, R1-R3, S1-S3) for
multiple timeframes and stores them in the existing cache
`cache/top_picks_runs.db` for fast reuse.

Timeframes:
- Y: Yearly (approx. last 252 trading days)
- M: Monthly (approx. last 22 trading days)
- W: Weekly (approx. last 5 trading days)
- D: Daily (last trading session)

All timestamps are stored in IST (Asia/Kolkata) to align with Indian
market hours and avoid unnecessary UTC/IST conversions in consumers.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd
from pytz import timezone as pytz_timezone

from .chart_data_service import chart_data_service

IST = pytz_timezone("Asia/Kolkata")


@dataclass
class SRLevels:
    symbol: str
    timeframe_scope: str
    p: float
    r1: float
    r2: float
    r3: float
    s1: float
    s2: float
    s3: float
    computed_at_ist: datetime

    def to_payload(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe_scope": self.timeframe_scope,
            "p": self.p,
            "r1": self.r1,
            "r2": self.r2,
            "r3": self.r3,
            "s1": self.s1,
            "s2": self.s2,
            "s3": self.s3,
            "computed_at_ist": self.computed_at_ist.isoformat(),
        }


class SupportResistanceService:
    """Compute and cache support/resistance levels per symbol/timeframe.

    Backed by the existing cache SQLite DB used for Top Picks runs,
    but with a dedicated table so it remains logically independent.
    """

    def __init__(self, db_path: str = "cache/top_picks_runs.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        # In-memory cache: (symbol, scope) -> SRLevels
        self._cache: Dict[Tuple[str, str], SRLevels] = {}

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS support_resistance_levels (
                    symbol TEXT NOT NULL,
                    timeframe_scope TEXT NOT NULL,
                    p REAL,
                    r1 REAL,
                    r2 REAL,
                    r3 REAL,
                    s1 REAL,
                    s2 REAL,
                    s3 REAL,
                    computed_at_ist TEXT NOT NULL,
                    PRIMARY KEY (symbol, timeframe_scope)
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sr_symbol_scope
                ON support_resistance_levels (symbol, timeframe_scope)
                """
            )
            conn.commit()
        finally:
            conn.close()

    async def get_levels(self, symbol: str, timeframe_scope: str) -> Optional[SRLevels]:
        """Return (and compute if needed) S/R levels for a symbol+scope.

        Args:
            symbol: NSE trading symbol (e.g., RELIANCE)
            timeframe_scope: One of {"Y", "M", "W", "D"}
        """

        if not symbol:
            return None

        sym = symbol.upper().strip()
        scope = timeframe_scope.upper().strip()
        if scope not in {"Y", "M", "W", "D"}:
            return None

        key = (sym, scope)
        now_ist = datetime.now(IST)

        # 1) In-memory cache
        cached = self._cache.get(key)
        if cached and not self._is_stale(cached.computed_at_ist, scope, now_ist):
            return cached

        # 2) SQLite cache
        db_levels = self._load_from_db(sym, scope)
        if db_levels and not self._is_stale(db_levels.computed_at_ist, scope, now_ist):
            self._cache[key] = db_levels
            return db_levels

        # 3) Compute fresh from chart data
        fresh = await self._compute_levels(sym, scope)
        if fresh is None:
            # If computation fails, fall back to whatever we had
            return db_levels or cached

        self._save_to_db(fresh)
        self._cache[key] = fresh
        return fresh

    def _is_stale(self, computed_at_ist: datetime, scope: str, now_ist: datetime) -> bool:
        """Decide if cached levels are stale for a given timeframe.

        We operate entirely in IST to stay aligned with Indian markets.
        """

        if computed_at_ist.tzinfo is None:
            computed_at_ist = IST.localize(computed_at_ist)

        if scope == "D":
            return computed_at_ist.date() != now_ist.date()
        if scope == "W":
            cw_year, cw_week, _ = computed_at_ist.isocalendar()
            nw_year, nw_week, _ = now_ist.isocalendar()
            return (cw_year, cw_week) != (nw_year, nw_week)
        if scope == "M":
            return (computed_at_ist.year, computed_at_ist.month) != (now_ist.year, now_ist.month)
        if scope == "Y":
            return computed_at_ist.year != now_ist.year
        return True

    def _load_from_db(self, symbol: str, scope: str) -> Optional[SRLevels]:
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT p, r1, r2, r3, s1, s2, s3, computed_at_ist
                FROM support_resistance_levels
                WHERE symbol = ? AND timeframe_scope = ?
                LIMIT 1
                """,
                (symbol, scope),
            )
            row = cur.fetchone()
        finally:
            conn.close()

        if not row:
            return None

        p, r1, r2, r3, s1, s2, s3, ts_str = row
        try:
            dt = datetime.fromisoformat(ts_str)
            if dt.tzinfo is None:
                dt = IST.localize(dt)
        except Exception:
            dt = datetime.now(IST)

        return SRLevels(
            symbol=symbol,
            timeframe_scope=scope,
            p=float(p),
            r1=float(r1),
            r2=float(r2),
            r3=float(r3),
            s1=float(s1),
            s2=float(s2),
            s3=float(s3),
            computed_at_ist=dt,
        )

    def _save_to_db(self, levels: SRLevels) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO support_resistance_levels (
                    symbol, timeframe_scope,
                    p, r1, r2, r3, s1, s2, s3,
                    computed_at_ist
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timeframe_scope) DO UPDATE SET
                    p = excluded.p,
                    r1 = excluded.r1,
                    r2 = excluded.r2,
                    r3 = excluded.r3,
                    s1 = excluded.s1,
                    s2 = excluded.s2,
                    s3 = excluded.s3,
                    computed_at_ist = excluded.computed_at_ist
                """,
                (
                    levels.symbol,
                    levels.timeframe_scope,
                    levels.p,
                    levels.r1,
                    levels.r2,
                    levels.r3,
                    levels.s1,
                    levels.s2,
                    levels.s3,
                    levels.computed_at_ist.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    async def _compute_levels(self, symbol: str, scope: str) -> Optional[SRLevels]:
        """Compute pivot levels from historical candles via chart_data_service.

        We currently fetch a 1Y chart and then slice an approximate
        number of trading days per timeframe:
        - Y: 252 days
        - M: 22 days
        - W: 5 days
        - D: 1 day
        """

        try:
            chart = await chart_data_service.fetch_chart_data(symbol, "1Y")
        except Exception:
            return None

        candles = (chart or {}).get("candles") or []
        if not candles:
            return None

        df = pd.DataFrame(candles)
        required = {"time", "open", "high", "low", "close"}
        if not required.issubset(df.columns):
            return None

        df = df.sort_values("time").reset_index(drop=True)

        window_map = {"Y": 252, "M": 22, "W": 5, "D": 1}
        window = window_map.get(scope, 22)
        if len(df) > window:
            df_win = df.tail(window)
        else:
            df_win = df

        if df_win.empty:
            return None

        high = float(df_win["high"].max())
        low = float(df_win["low"].min())
        close = float(df_win["close"].iloc[-1])

        if not np.isfinite(high) or not np.isfinite(low) or not np.isfinite(close):
            return None

        # Standard floor pivots
        p = (high + low + close) / 3.0
        r1 = 2 * p - low
        s1 = 2 * p - high
        r2 = p + (high - low)
        s2 = p - (high - low)
        r3 = high + 2 * (p - low)
        s3 = low - 2 * (high - p)

        now_ist = datetime.now(IST)
        return SRLevels(
            symbol=symbol,
            timeframe_scope=scope,
            p=float(p),
            r1=float(r1),
            r2=float(r2),
            r3=float(r3),
            s1=float(s1),
            s2=float(s2),
            s3=float(s3),
            computed_at_ist=now_ist,
        )


# Global instance used by TopPicksEngine and AutoMonitoringAgent
support_resistance_service = SupportResistanceService()
