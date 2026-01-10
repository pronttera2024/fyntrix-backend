from __future__ import annotations

"""Small diagnostic helper to inspect offline backtest results per day.

Usage (from backend folder):

    python analyze_backtest_day.py 2025-12-04

This does NOT affect any APIs or production services; it only reads
cache/top_picks_backtest.db and prints simple counts.
"""

import sqlite3
import pathlib
import sys
from typing import Tuple

DB_PATH = pathlib.Path("cache/top_picks_backtest.db")


def analyze(date_str: str) -> Tuple[int, int, int, int]:
    """Return (total_rows, tp1_hits, sl_hits, other) for a given date.

    We classify rows based on how potential_return_tp1 relates to the
    theoretical TP1/SL returns implied by entry/SL/target.
    """

    if not DB_PATH.exists():
        print(f"[analyze] DB not found: {DB_PATH}")
        return 0, 0, 0, 0

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    rows = cur.execute(
        """
        SELECT
            entry_price,
            stop_loss_price,
            target_price,
            direction,
            potential_return_tp1
        FROM picks_backtest
        WHERE date(generated_at_utc) = ?
        """,
        (date_str,),
    ).fetchall()

    conn.close()

    total = len(rows)
    tol = 5e-4  # tolerance for float comparison

    tp1_hits = 0
    sl_hits = 0
    other = 0

    for entry, sl_price, target, direction, r in rows:
        d = (direction or "").upper()

        if entry in (None, 0) or r is None or d not in ("LONG", "SHORT"):
            other += 1
            continue

        tp_ret = None
        sl_ret = None

        try:
            if target is not None:
                tp_ret = ((target - entry) / entry) if d == "LONG" else ((entry - target) / entry)
        except Exception:
            tp_ret = None

        try:
            if sl_price is not None:
                sl_ret = ((sl_price - entry) / entry) if d == "LONG" else ((entry - sl_price) / entry)
        except Exception:
            sl_ret = None

        if tp_ret is not None and abs(r - tp_ret) <= tol:
            tp1_hits += 1
        elif sl_ret is not None and abs(r - sl_ret) <= tol:
            sl_hits += 1
        else:
            other += 1

    return total, tp1_hits, sl_hits, other


if __name__ == "__main__":
    date = sys.argv[1] if len(sys.argv) > 1 else "2025-12-04"
    total, tp1, sl, other = analyze(date)
    print(f"DATE {date}")
    print(f"TOTAL_ROWS {total}")
    print(f"TP1_HIT_EST {tp1}")
    print(f"SL_HIT_EST {sl}")
    print(f"OTHER_EST {other}")
