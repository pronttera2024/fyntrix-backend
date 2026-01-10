from __future__ import annotations

"""Daily helper script to refresh offline TP1/MFE/Ladder backtests.

Run this once after market close (e.g. via Windows Task Scheduler):

    python run_daily_backtest.py

It will:
- Look back over the last N calendar days (approx. last 5 trading days)
- For each configured universe (e.g. NIFTY50, BANKNIFTY)
- Run the offline backtest job across all trading modes
  (Scalping, Intraday, Swing, Options, Futures)
- Persist results into cache/top_picks_backtest.db

The Winning Trades API then uses this DB to surface TP1/MFE/Ladder
metrics in the KPIs and per-trade rows.
"""

from datetime import datetime, timedelta, timezone
from typing import List

from app.services.top_picks_backtest import run_backtest_sync


# Universes we want to keep backtested for Winning Trades.
UNIVERSES: List[str] = ["nifty50", "banknifty"]

# How many calendar days to look back when running the job.
# ~7 calendar days ≈ last 5 trading days (excluding weekends/holidays).
LOOKBACK_DAYS: int = 7

# Upper bound on how many historical Top Picks runs to process per universe.
MAX_RUNS: int = 500


def main() -> None:
    now_utc = datetime.now(timezone.utc)
    start = now_utc - timedelta(days=LOOKBACK_DAYS)
    end = now_utc

    print(
        f"[daily_backtest] Running offline backtest for universes={UNIVERSES} "
        f"window={start.isoformat()} -> {end.isoformat()} (UTC)"
    )

    for universe in UNIVERSES:
        try:
            print(f"[daily_backtest] Universe={universe}: starting run_backtest_sync()")
            run_backtest_sync(
                universe=universe,
                mode=None,  # all modes
                start_utc=start.isoformat(),
                end_utc=end.isoformat(),
                max_runs=MAX_RUNS,
            )
            print(f"[daily_backtest] Universe={universe}: completed successfully")
        except Exception as exc:  # pragma: no cover - best-effort logging
            print(f"[daily_backtest] ERROR for universe={universe}: {exc}")

    print("[daily_backtest] Done")


if __name__ == "__main__":
    main()
