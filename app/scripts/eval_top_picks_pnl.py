"""Simple P&L backtest for stored Top Picks.

Loads a picks_YYYY-MM-DD.json file from backend/data/top_picks, fetches
same-day price data via Yahoo Finance, and computes approximate P&L for
long/short ideas versus NIFTY.

Assumptions (first cut):
- Direction:
  - Long for recommendations in {"Strong Buy", "Buy"}
  - Short for {"Sell", "Strong Sell"}
- Entry price:
  - Prefer pick["entry_price"], then pick["price"], then pick["last_price"].
- Exit price:
  - Close price for the same trading date from Yahoo Finance.
- Realised P&L:
  - For longs: (close - entry) / entry * 100
  - For shorts: (entry - close) / entry * 100
  - If exit_strategy has stop_pct/target_pct, clamp P&L between
    -stop_pct and +target_pct to approximate bounded intraday risk.
- Index benchmark:
  - NIFTY 50 via ticker "^NSEI"; daily return = (close - open) / open * 100.

This is intentionally lightweight and transparent so that it can be
iterated as we refine execution assumptions.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import yfinance as yf


@dataclass
class PickPnl:
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    pnl_pct: float
    index_pct: float
    recommendation: str


def _load_picks(date_str: str, file_path: Optional[str] = None) -> Dict[str, Any]:
    if file_path:
        path = Path(file_path)
    else:
        root = Path(__file__).resolve().parents[2]
        path = root / "data" / "top_picks" / f"picks_{date_str}.json"

    if not path.exists():
        raise FileNotFoundError(f"Top picks file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return data


def _fetch_daily_close(symbol: str, date: datetime) -> Optional[Dict[str, float]]:
    yf_symbol = f"{symbol}.NS" if not symbol.endswith((".NS", ".BO")) else symbol

    start = date
    end = date + timedelta(days=1)

    try:
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(start=start, end=end, interval="1d")
    except Exception as e:
        print(f"  ⚠️  Yahoo fetch failed for {symbol}: {e}")
        return None

    if df is None or df.empty:
        print(f"  ⚠️  No daily data for {symbol} on {date.date()}")
        return None

    row = df.iloc[0]
    try:
        open_price = float(row["Open"])
        close_price = float(row["Close"])
    except Exception:
        return None

    return {"open": open_price, "close": close_price}


def _fetch_index_return(date: datetime) -> Optional[float]:
    start = date
    end = date + timedelta(days=1)

    try:
        ticker = yf.Ticker("^NSEI")
        df = ticker.history(start=start, end=end, interval="1d")
    except Exception as e:
        print(f"  ⚠️  Yahoo fetch failed for ^NSEI: {e}")
        return None

    if df is None or df.empty:
        print(f"  ⚠️  No NIFTY data for {date.date()}")
        return None

    row = df.iloc[0]
    try:
        open_price = float(row["Open"])
        close_price = float(row["Close"])
    except Exception:
        return None

    if open_price <= 0:
        return None

    return (close_price - open_price) / open_price * 100.0


def _infer_direction(rec: str) -> Optional[str]:
    rec = (rec or "").strip().lower()
    if rec in {"strong buy", "buy"}:
        return "LONG"
    if rec in {"sell", "strong sell"}:
        return "SHORT"
    return None


def _select_entry_price(pick: Dict[str, Any]) -> Optional[float]:
    for key in ("entry_price", "price", "last_price"):
        val = pick.get(key)
        if val is None:
            continue
        try:
            v = float(val)
        except Exception:
            continue
        if v > 0:
            return v
    return None


def _compute_realised_pnl(
    direction: str,
    entry_price: float,
    exit_price: float,
    exit_strategy: Optional[Dict[str, Any]] = None,
) -> float:
    if entry_price <= 0 or exit_price <= 0:
        return 0.0

    if direction == "LONG":
        raw = (exit_price - entry_price) / entry_price * 100.0
    else:
        raw = (entry_price - exit_price) / entry_price * 100.0

    if not exit_strategy:
        return raw

    try:
        stop_pct = float(exit_strategy.get("stop_pct") or 0.0)
    except Exception:
        stop_pct = 0.0
    try:
        target_pct = float(exit_strategy.get("target_pct") or 0.0)
    except Exception:
        target_pct = 0.0

    if stop_pct <= 0 and target_pct <= 0:
        return raw

    lower = -abs(stop_pct) if stop_pct > 0 else None
    upper = abs(target_pct) if target_pct > 0 else None

    if lower is not None and raw < lower:
        raw = lower
    if upper is not None and raw > upper:
        raw = upper

    return raw


def evaluate_picks(date_str: str, file_path: Optional[str] = None) -> None:
    data = _load_picks(date_str, file_path)
    picks: List[Dict[str, Any]] = data.get("picks", [])
    if not picks:
        print(f"No picks found for {date_str}.")
        return

    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    index_ret = _fetch_index_return(date_obj) or 0.0

    results: List[PickPnl] = []

    print(f"\nEvaluating {len(picks)} picks for {date_str} (index ~ {index_ret:+.2f}%):\n")

    for pick in picks:
        symbol = pick.get("symbol") or ""
        rec = str(pick.get("recommendation") or "")
        direction = _infer_direction(rec)
        if not symbol or direction is None:
            continue

        entry_price = _select_entry_price(pick)
        if entry_price is None:
            continue

        ohlc = _fetch_daily_close(symbol, date_obj)
        if not ohlc:
            continue

        exit_price = ohlc["close"]
        exit_strategy = pick.get("exit_strategy") or {}

        pnl_pct = _compute_realised_pnl(direction, entry_price, exit_price, exit_strategy)

        res = PickPnl(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl_pct=pnl_pct,
            index_pct=index_ret,
            recommendation=rec,
        )
        results.append(res)

        print(
            f"{symbol:10s} | {direction:5s} | entry={entry_price:8.2f} -> exit={exit_price:8.2f} | "
            f"pnl={pnl_pct:+5.2f}% | vs index={pnl_pct - index_ret:+5.2f}%"
        )

    if not results:
        print("No evaluable picks (missing prices or symbols).")
        return

    longs = [r for r in results if r.direction == "LONG"]
    shorts = [r for r in results if r.direction == "SHORT"]

    def _avg(xs: List[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    avg_all = _avg([r.pnl_pct for r in results])
    avg_longs = _avg([r.pnl_pct for r in longs])
    avg_shorts = _avg([r.pnl_pct for r in shorts])
    avg_vs_index = _avg([r.pnl_pct - r.index_pct for r in results])

    print("\nSummary:")
    print(f"  Picks evaluated : {len(results)} (longs={len(longs)}, shorts={len(shorts)})")
    print(f"  Avg P&L         : {avg_all:+5.2f}%")
    print(f"  Avg P&L longs   : {avg_longs:+5.2f}%")
    print(f"  Avg P&L shorts  : {avg_shorts:+5.2f}%")
    print(f"  Index return    : {index_ret:+5.2f}% (NIFTY 50)")
    print(f"  Avg alpha vs idx: {avg_vs_index:+5.2f}%")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate P&L for stored Top Picks.")
    parser.add_argument(
        "--date",
        required=True,
        help="Trading date in YYYY-MM-DD format (must match picks_YYYY-MM-DD.json)",
    )
    parser.add_argument(
        "--file",
        default=None,
        help="Optional explicit path to a picks JSON file (overrides --date lookup)",
    )
    args = parser.parse_args()

    evaluate_picks(args.date, args.file)


if __name__ == "__main__":
    main()
