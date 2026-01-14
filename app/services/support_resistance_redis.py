"""Support/Resistance (S/R) computation and caching service using Redis.

Computes pivot-based support/resistance levels (P, R1-R3, S1-S3) for
multiple timeframes and stores them in Redis for fast reuse.

Timeframes:
- Y: Yearly (approx. last 252 trading days)
- M: Monthly (approx. last 22 trading days)
- W: Weekly (approx. last 5 trading days)
- D: Daily (last trading session)

All timestamps are stored in IST (Asia/Kolkata) to align with Indian
market hours and avoid unnecessary UTC/IST conversions in consumers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
from pytz import timezone as pytz_timezone

from .chart_data_service import chart_data_service
from .redis_client import get_json, set_json

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

    @classmethod
    def from_payload(cls, data: Dict[str, Any]) -> "SRLevels":
        """Create SRLevels from Redis payload"""
        computed_at = datetime.fromisoformat(data["computed_at_ist"])
        if computed_at.tzinfo is None:
            computed_at = IST.localize(computed_at)
        
        return cls(
            symbol=data["symbol"],
            timeframe_scope=data["timeframe_scope"],
            p=data["p"],
            r1=data["r1"],
            r2=data["r2"],
            r3=data["r3"],
            s1=data["s1"],
            s2=data["s2"],
            s3=data["s3"],
            computed_at_ist=computed_at,
        )


class SupportResistanceService:
    """Compute and cache support/resistance levels per symbol/timeframe using Redis."""

    def __init__(self) -> None:
        # Redis key prefix for S/R levels
        self.key_prefix = "sr:levels"

    def _make_redis_key(self, symbol: str, scope: str) -> str:
        """Generate Redis key for S/R levels"""
        return f"{self.key_prefix}:{symbol}:{scope}"

    def _should_recompute(self, levels: Optional[SRLevels], scope: str) -> bool:
        """Check if cached levels are stale and need recomputation"""
        if levels is None:
            return True

        now_ist = datetime.now(IST)
        age = now_ist - levels.computed_at_ist

        # Recompute thresholds based on scope
        thresholds = {
            "Y": timedelta(days=7),   # Yearly: recompute weekly
            "M": timedelta(days=1),   # Monthly: recompute daily
            "W": timedelta(hours=6),  # Weekly: recompute every 6 hours
            "D": timedelta(hours=1),  # Daily: recompute hourly
        }

        threshold = thresholds.get(scope, timedelta(hours=1))
        return age > threshold

    async def get_levels(self, symbol: str, scope: str = "D") -> Optional[SRLevels]:
        """Get S/R levels for symbol and timeframe scope.
        
        Returns cached levels if fresh, otherwise computes new levels.
        
        Args:
            symbol: Stock symbol
            scope: Timeframe scope (Y/M/W/D)
            
        Returns:
            SRLevels object or None if computation fails
        """
        # Try to get from Redis
        redis_key = self._make_redis_key(symbol, scope)
        cached_data = get_json(redis_key)
        
        if cached_data:
            try:
                levels = SRLevels.from_payload(cached_data)
                
                # Check if still fresh
                if not self._should_recompute(levels, scope):
                    return levels
            except Exception:
                pass  # Cache corrupted, recompute

        # Compute new levels
        levels = await self._compute_levels(symbol, scope)
        
        if levels:
            # Cache in Redis with appropriate TTL
            ttl_map = {
                "Y": 7 * 24 * 3600,   # 7 days
                "M": 24 * 3600,       # 1 day
                "W": 6 * 3600,        # 6 hours
                "D": 3600,            # 1 hour
            }
            ttl = ttl_map.get(scope, 3600)
            
            set_json(redis_key, levels.to_payload(), ex=ttl)
        
        return levels

    async def _compute_levels(self, symbol: str, scope: str) -> Optional[SRLevels]:
        """Compute S/R levels from historical data"""
        # Map scope to number of days
        scope_days = {
            "Y": 252,  # ~1 year
            "M": 22,   # ~1 month
            "W": 5,    # ~1 week
            "D": 1,    # 1 day
        }
        days = scope_days.get(scope, 1)

        try:
            # Fetch historical data
            df = await chart_data_service.get_ohlc(
                symbol=symbol,
                interval="1d",
                days=days + 5  # Extra buffer
            )

            if df is None or df.empty or len(df) < days:
                return None

            # Use last N days
            df = df.tail(days)

            # Calculate pivot point and S/R levels
            high = df["high"].max()
            low = df["low"].min()
            close = df["close"].iloc[-1]

            # Standard pivot calculation
            p = (high + low + close) / 3
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

        except Exception as e:
            print(f"[SR] Failed to compute levels for {symbol}/{scope}: {e}")
            return None

    async def get_score(
        self,
        symbol: str,
        current_price: float,
        scope: str = "D",
    ) -> float:
        """Calculate S/R score based on current price position.
        
        Returns a score from 0-100 based on how close the price is to
        support (higher score) or resistance (lower score).
        """
        levels = await self.get_levels(symbol, scope)
        if not levels:
            return 50.0  # Neutral if no levels

        # Determine position relative to levels
        if current_price >= levels.r3:
            return 10.0  # Very overbought
        elif current_price >= levels.r2:
            return 25.0  # Overbought
        elif current_price >= levels.r1:
            return 40.0  # Above pivot
        elif current_price >= levels.p:
            return 55.0  # Near pivot (bullish)
        elif current_price >= levels.s1:
            return 70.0  # Below pivot (support zone)
        elif current_price >= levels.s2:
            return 85.0  # Strong support
        else:
            return 95.0  # Very oversold (strong buy zone)


# Global instance
support_resistance_service = SupportResistanceService()
