"""Top Picks Positions Service

Derive lightweight, logical positions from the latest Top Picks runs
for non-scalping modes (Intraday, Swing, etc.).

These positions are used by the Top Picks Positions Monitor to raise
stop/target proximity alerts via AutoMonitoringAgent. No order
execution is performed.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from .top_picks_store import get_top_picks_store


def _map_recommendation_to_direction(rec: Optional[str]) -> Optional[str]:
    """Map textual recommendation to LONG/SHORT direction.

    We treat Strong Buy/Buy as LONG, Sell/Strong Sell as SHORT, and
    ignore Neutral/Hold-style values for the purposes of position
    monitoring.
    """

    if not rec:
        return None

    text = str(rec).lower()
    if "sell" in text:
        return "SHORT"
    if "buy" in text:
        return "LONG"
    return None


def get_top_picks_positions(
    universes: Optional[List[str]] = None,
    modes: Optional[List[str]] = None,
    max_per_run: int = 5,
) -> List[Dict[str, Any]]:
    """Return a list of logical positions derived from latest Top Picks.

    Each position contains at minimum:
    - symbol
    - universe, mode
    - direction (LONG/SHORT)
    - entry_price
    - stop_loss (if available)
    - target (if available)

    Only non-Scalping modes are considered here; Scalping positions are
    handled by the dedicated scalping monitor and exit tracker.
    """

    store = get_top_picks_store()

    if universes is None:
        universes = ["nifty50", "banknifty"]

    if modes is None:
        modes = ["Intraday", "Swing"]

    positions: List[Dict[str, Any]] = []

    for universe in universes:
        for mode in modes:
            run = store.get_latest_run_for(universe, mode)
            if not run:
                continue

            items = run.get("items") or []
            as_of = run.get("as_of") or datetime.utcnow().isoformat() + "Z"

            for idx, pick in enumerate(items[:max_per_run]):
                symbol = pick.get("symbol")
                if not symbol:
                    continue

                direction = _map_recommendation_to_direction(pick.get("recommendation"))
                if not direction:
                    # Skip Neutral/Hold-style picks for monitoring
                    continue

                price = pick.get("price") or 0.0
                try:
                    entry_price = float(price) if price is not None else 0.0
                except Exception:
                    entry_price = 0.0

                if entry_price <= 0:
                    continue

                exit_strategy = pick.get("exit_strategy") or {}
                stop_price = exit_strategy.get("stop_loss_price") or exit_strategy.get("stop_loss")
                target_price = exit_strategy.get("target_price") or exit_strategy.get("target")

                try:
                    stop_price_f = float(stop_price) if stop_price is not None else 0.0
                except Exception:
                    stop_price_f = 0.0

                try:
                    target_price_f = float(target_price) if target_price is not None else 0.0
                except Exception:
                    target_price_f = 0.0

                # Require at least one of stop/target to be present to be useful
                if stop_price_f <= 0 and target_price_f <= 0:
                    continue

                positions.append(
                    {
                        "symbol": symbol,
                        "universe": universe,
                        "mode": mode,
                        "direction": direction,
                        "entry_price": entry_price,
                        "stop_loss": stop_price_f if stop_price_f > 0 else None,
                        "target": target_price_f if target_price_f > 0 else None,
                        "exit_strategy": exit_strategy,
                        "source": "top_picks",
                        "rank": pick.get("rank") or (idx + 1),
                        "as_of": as_of,
                    }
                )

    return positions
