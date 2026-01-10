import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


class StrategyExitTracker:
    """Track strategy-based advisory exits (e.g. S1 virtual exits).

    This is advisory-only data used for KPI evaluation. It does not
    trigger or record real broker exits.
    """

    def __init__(self) -> None:
        base = Path(__file__).parent.parent.parent
        self.exits_dir = base / "data" / "strategy_exits"
        self.exits_dir.mkdir(parents=True, exist_ok=True)

    def log_advisory(self, advisory: Dict[str, Any], position: Dict[str, Any]) -> None:
        """Log a single strategy advisory with a recommended_exit_price.

        The advisory dict is expected to contain at minimum:
        - strategy_id
        - kind
        - symbol
        - recommended_exit_price

        Position should contain at minimum:
        - symbol
        - direction
        - entry_price
        - mode (e.g. Intraday, Swing)
        - source (e.g. top_picks, portfolio)
        """

        try:
            symbol = advisory.get("symbol") or position.get("symbol")
            strategy_id = advisory.get("strategy_id")
            kind = advisory.get("kind")
            price = advisory.get("recommended_exit_price")
            # Default to treating advisories as exit-driving unless explicitly
            # marked otherwise by the producer. This preserves existing
            # behaviour for historical data while allowing new advisory types
            # to opt out via is_exit=False.
            is_exit = bool(advisory.get("is_exit", True))

            if not symbol or not strategy_id or price is None:
                return

            ts = advisory.get("generated_at")
            if isinstance(ts, str):
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    dt = datetime.utcnow()
            elif isinstance(ts, datetime):
                dt = ts
            else:
                dt = datetime.utcnow()

            date_str = dt.strftime("%Y%m%d")
            file_path = self.exits_dir / f"strategy_exits_{date_str}.json"

            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {"date": dt.strftime("%Y-%m-%d"), "exits": []}

            exits: List[Dict[str, Any]] = data.get("exits", [])

            for e in exits:
                if (
                    e.get("symbol") == symbol
                    and e.get("strategy_id") == strategy_id
                    and e.get("kind") == kind
                    and e.get("recommended_exit_price") == price
                ):
                    return

            record: Dict[str, Any] = {
                "symbol": symbol,
                "strategy_id": strategy_id,
                "kind": kind,
                "severity": advisory.get("severity"),
                "recommended_exit_price": float(price),
                "generated_at": dt.isoformat() + "Z",
                "direction": position.get("direction"),
                "entry_price": position.get("entry_price"),
                "mode": position.get("mode"),
                "source": position.get("source"),
                "rr_multiple": advisory.get("rr_multiple"),
                "is_exit": is_exit,
            }

            sr_reason = advisory.get("sr_reason")
            if sr_reason is not None:
                record["sr_reason"] = sr_reason

            news_reason = advisory.get("news_reason")
            if news_reason is not None:
                record["news_reason"] = news_reason

            news_risk_score = advisory.get("news_risk_score")
            if news_risk_score is not None:
                try:
                    record["news_risk_score"] = float(news_risk_score)
                except Exception:
                    pass

            exits.append(record)
            data["exits"] = exits

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            logger.info(
                "[StrategyExitTracker] Logged %s %s exit for %s @ %s",
                strategy_id,
                kind,
                symbol,
                price,
            )
        except Exception as e:
            logger.error("[StrategyExitTracker] Failed to log advisory: %s", e, exc_info=True)

    def get_exit_for(
        self,
        symbol: str,
        date: str,
        strategy_id: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return one best-matching strategy exit for a symbol on a given date.

        Selection priority:
        1) CONTEXT_INVALIDATED advisories
        2) PARTIAL_PROFIT advisories
        3) Others, all ordered by earliest generated_at.
        """

        try:
            try:
                dt = datetime.fromisoformat(date)
            except Exception:
                # Accept already-compact YYYYMMDD as a fallback
                try:
                    dt = datetime.strptime(date, "%Y%m%d")
                except Exception:
                    return None

            date_str = dt.strftime("%Y%m%d")
            file_path = self.exits_dir / f"strategy_exits_{date_str}.json"

            if not file_path.exists():
                return None

            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            exits: List[Dict[str, Any]] = data.get("exits", [])
            candidates: List[Dict[str, Any]] = []

            for rec in exits:
                if rec.get("symbol") != symbol:
                    continue
                if strategy_id and rec.get("strategy_id") != strategy_id:
                    continue
                if mode and rec.get("mode") != mode:
                    continue
                candidates.append(rec)

            if not candidates:
                return None

            def sort_key(rec: Dict[str, Any]) -> tuple:
                kind = str(rec.get("kind") or "")
                if kind == "CONTEXT_INVALIDATED":
                    kind_rank = 0
                elif kind == "PARTIAL_PROFIT":
                    kind_rank = 1
                else:
                    kind_rank = 2

                ts = rec.get("generated_at")
                try:
                    if isinstance(ts, str):
                        ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    else:
                        ts_dt = datetime.min
                except Exception:
                    ts_dt = datetime.min

                return (kind_rank, ts_dt)

            candidates.sort(key=sort_key)
            return candidates[0]
        except Exception as e:
            logger.error("[StrategyExitTracker] Failed to get exit for %s on %s: %s", symbol, date, e, exc_info=True)
            return None


strategy_exit_tracker = StrategyExitTracker()
