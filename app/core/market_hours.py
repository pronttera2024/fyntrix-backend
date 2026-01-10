from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

IST_OFFSET = timedelta(hours=5, minutes=30)


def now_ist() -> datetime:
    """Return current naive datetime in IST (UTC+5:30 offset)."""
    return datetime.utcnow() + IST_OFFSET


def is_trading_weekday_ist(dt: Optional[datetime] = None) -> bool:
    """Return True if the given IST datetime falls on a trading weekday (Mon-Fri)."""
    if dt is None:
        dt = now_ist()
    return dt.weekday() < 5


def is_cash_market_open_ist(dt: Optional[datetime] = None) -> bool:
    """Return True if Indian cash market is open (9:1515:30 IST, Mon1313Fri)."""
    if dt is None:
        dt = now_ist()
    if not is_trading_weekday_ist(dt):
        return False
    minutes = dt.hour * 60 + dt.minute
    open_min = 9 * 60 + 15
    close_min = 15 * 60 + 30
    return open_min <= minutes < close_min


def is_scalping_cycle_window_ist(dt: Optional[datetime] = None) -> bool:
    """Return True during scalping cycle window (9:2015:30 IST, Mon1313Fri)."""
    if dt is None:
        dt = now_ist()
    if not is_trading_weekday_ist(dt):
        return False
    minutes = dt.hour * 60 + dt.minute
    open_min = 9 * 60 + 20
    close_min = 15 * 60 + 30
    return open_min <= minutes <= close_min


def is_eod_window_ist(dt: Optional[datetime] = None) -> bool:
    """Return True during the short EOD window just after close (15:3015:45 IST, Mon1313Fri)."""
    if dt is None:
        dt = now_ist()
    if not is_trading_weekday_ist(dt):
        return False
    return dt.hour == 15 and 30 <= dt.minute <= 45


def now_utc() -> datetime:
    """Return current UTC datetime."""
    return datetime.utcnow()


def to_iso_utc(dt: datetime) -> str:
    """Convert datetime to ISO format with Z suffix."""
    return dt.isoformat() + 'Z'
