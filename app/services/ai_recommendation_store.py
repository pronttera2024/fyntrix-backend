"""AI Recommendation Store

SQLite-backed storage for individual AI trade recommendations (Top Five Picks
and, via modes, Scalping/Intraday/Swing/Options/Futures).

This is the primary dataset for performance analytics and future
reinforcement-learning style optimization of agent weights, filters, and
exit rules.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class RecommendationContext:
    symbol: str
    mode: str
    universe: str
    source: str
    recommendation: str
    direction: str
    generated_at_utc: str
    entry_price: Optional[float]
    stop_loss_price: Optional[float]
    target_price: Optional[float]
    score_blend: Optional[float]
    confidence: Optional[str]
    risk_profile: Optional[str]
    run_id: Optional[str]
    rank_in_run: Optional[int]
    policy_version: Optional[str]
    features_json: str


class AiRecommendationStore:
    """SQLite-based storage for AI recommendations.

    Each row represents a single recommendation instance (symbol, mode,
    universe, run) with both inputs and, later, realized outcomes. Outcomes
    are populated by analytics services once price/exit data is available.
    """

    def __init__(self, db_path: str = "cache/ai_recommendations.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                mode TEXT NOT NULL,
                universe TEXT NOT NULL,
                source TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                direction TEXT NOT NULL,
                generated_at_utc TEXT NOT NULL,
                entry_price REAL,
                stop_loss_price REAL,
                target_price REAL,
                score_blend REAL,
                confidence TEXT,
                risk_profile TEXT,
                run_id TEXT,
                rank_in_run INTEGER,
                policy_version TEXT,
                features_json TEXT,
                evaluated INTEGER NOT NULL DEFAULT 0,
                evaluated_at_utc TEXT,
                exit_price REAL,
                exit_time_utc TEXT,
                exit_reason TEXT,
                pnl_pct REAL,
                max_drawdown_pct REAL,
                alpha_vs_benchmark REAL,
                labels_json TEXT
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ai_rec_symbol_mode_time
            ON ai_recommendations (symbol, mode, generated_at_utc DESC)
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ai_rec_evaluated_time
            ON ai_recommendations (evaluated, generated_at_utc)
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ai_rec_run_id
            ON ai_recommendations (run_id)
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ai_rec_source
            ON ai_recommendations (source)
            """
        )

        # Backfill new columns for existing databases (no-op if already present)
        try:
            cursor.execute(
                "ALTER TABLE ai_recommendations ADD COLUMN policy_version TEXT"
            )
        except Exception:
            pass

        conn.commit()
        conn.close()

    def _normalize_to_utc(self, ts: Optional[str]) -> str:
        """Normalize an ISO8601-ish timestamp to strict UTC ISO string.

        Accepts naive or offset-aware strings (optionally with trailing 'Z').
        Falls back to current UTC time if parsing fails or value is missing.
        """
        if not ts:
            return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        try:
            s = str(ts)
            if s.endswith("Z"):
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            else:
                dt = datetime.fromisoformat(s)
        except Exception:
            return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        return dt.isoformat().replace("+00:00", "Z")

    def _build_context_from_item(self, payload: Dict[str, Any], item: Dict[str, Any], source: str) -> Optional[RecommendationContext]:
        symbol = str(item.get("symbol") or "").upper()
        if not symbol:
            return None

        mode = str(payload.get("mode") or item.get("mode") or "Unknown")
        universe = str(payload.get("universe") or "").upper() or "UNKNOWN"
        recommendation = str(item.get("recommendation") or "Hold")
        direction = "SHORT" if "sell" in recommendation.lower() else "LONG"

        generated_at_raw = payload.get("as_of") or payload.get("generated_at")
        generated_at_utc = self._normalize_to_utc(generated_at_raw)

        # Entry/targets from pick and its exit_strategy when available
        entry_price = None
        stop_loss_price = None
        target_price = None

        try:
            if mode == "Scalping":
                entry_price = item.get("entry_price") or item.get("price")
            else:
                entry_price = item.get("price")
        except Exception:
            entry_price = None

        exit_strategy = item.get("exit_strategy") or {}
        if isinstance(exit_strategy, dict):
            try:
                sl = exit_strategy.get("stop_loss_price")
                tp = exit_strategy.get("target_price")
                stop_loss_price = float(sl) if sl is not None else None
                target_price = float(tp) if tp is not None else None
            except Exception:
                stop_loss_price = stop_loss_price or None
                target_price = target_price or None

        # Scores / metadata snapshot
        try:
            score_blend = float(item.get("score_blend", item.get("blend_score", 0.0)))
        except Exception:
            score_blend = None

        confidence = item.get("confidence")
        risk_profile = payload.get("risk_profile")  # optional, may be None
        run_id = payload.get("run_id")
        rank_in_run = item.get("rank")

        # Policy version: prefer top-level payload, then nested metadata
        metadata = payload.get("metadata") or {}
        policy_version = payload.get("policy_version") or metadata.get("policy_version")

        features: Dict[str, Any] = {
            "scores": item.get("scores"),
            "agent_consensus": item.get("agent_consensus"),
            "key_signals": item.get("key_signals"),
            "exit_strategy": exit_strategy,
            "reasoning": item.get("reasoning"),
            "horizon": item.get("horizon"),
            "risk_reward_ratio": item.get("risk_reward_ratio"),
            "color_scheme": item.get("color_scheme"),
            "recommendation_note": item.get("recommendation_note"),
            "metadata": {
                "elapsed_seconds": payload.get("elapsed_seconds"),
            },
        }

        try:
            features_json = json.dumps(features, default=str)
        except Exception:
            features_json = "{}"

        return RecommendationContext(
            symbol=symbol,
            mode=mode,
            universe=universe,
            source=source,
            recommendation=recommendation,
            direction=direction,
            generated_at_utc=generated_at_utc,
            entry_price=float(entry_price) if entry_price is not None else None,
            stop_loss_price=stop_loss_price,
            target_price=target_price,
            score_blend=score_blend,
            confidence=str(confidence) if confidence is not None else None,
            risk_profile=str(risk_profile) if risk_profile is not None else None,
            run_id=str(run_id) if run_id is not None else None,
            rank_in_run=int(rank_in_run) if isinstance(rank_in_run, int) else None,
            policy_version=str(policy_version) if policy_version is not None else None,
            features_json=features_json,
        )

    def log_from_top_picks_payload(self, payload: Dict[str, Any], source: str = "top_picks_scheduler") -> int:
        """Persist recommendations from a Top Picks payload.

        The payload is expected to have the shape produced by
        TopPicksScheduler._compute_for_universe (items, as_of, universe,
        mode, elapsed_seconds, optional run_id).

        Returns the number of rows inserted.
        """
        items = payload.get("items") or []
        if not isinstance(items, list) or not items:
            return 0

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        inserted = 0
        for item in items[:50]:  # defensive cap per run
            ctx = self._build_context_from_item(payload, item, source)
            if ctx is None:
                continue

            cursor.execute(
                """
                INSERT INTO ai_recommendations (
                    symbol,
                    mode,
                    universe,
                    source,
                    recommendation,
                    direction,
                    generated_at_utc,
                    entry_price,
                    stop_loss_price,
                    target_price,
                    score_blend,
                    confidence,
                    risk_profile,
                    run_id,
                    rank_in_run,
                    policy_version,
                    features_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ctx.symbol,
                    ctx.mode,
                    ctx.universe,
                    ctx.source,
                    ctx.recommendation,
                    ctx.direction,
                    ctx.generated_at_utc,
                    ctx.entry_price,
                    ctx.stop_loss_price,
                    ctx.target_price,
                    ctx.score_blend,
                    ctx.confidence,
                    ctx.risk_profile,
                    ctx.run_id,
                    ctx.rank_in_run,
                    ctx.policy_version,
                    ctx.features_json,
                ),
            )
            inserted += 1

        if inserted:
            conn.commit()
        conn.close()
        return inserted

    def apply_scalping_exit(self, exit_data: Dict[str, Any]) -> int:
        """Best-effort hook to apply a scalping exit into the dataset.

        This attempts to find the corresponding Scalping recommendation row in
        ai_recommendations and mark it evaluated with the provided exit
        details. If no matching row is found, this is a no-op.
        """

        symbol = str(exit_data.get("symbol") or "").upper()
        if not symbol:
            return 0

        mode = "Scalping"

        # Derive entry trade date from entry_time when available so that we
        # can narrow the search to recommendations from that day.
        entry_date_prefix: Optional[str]
        try:
            entry_time_raw = exit_data.get("entry_time")
            if entry_time_raw:
                dt = datetime.fromisoformat(str(entry_time_raw).replace("Z", "+00:00"))
                entry_date_prefix = dt.date().isoformat()
            else:
                entry_date_prefix = None
        except Exception:
            entry_date_prefix = None

        exit_price = exit_data.get("exit_price")
        exit_time = exit_data.get("exit_time")
        exit_reason = exit_data.get("exit_reason")
        pnl_pct = exit_data.get("return_pct")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            where = "symbol = ? AND mode = ? AND evaluated = 0"
            params: list[Any] = [symbol, mode]

            if entry_date_prefix:
                where += " AND generated_at_utc LIKE ?"
                params.append(entry_date_prefix + "%")

            cursor.execute(
                f"SELECT id FROM ai_recommendations WHERE {where} "
                "ORDER BY generated_at_utc ASC LIMIT 1",
                tuple(params),
            )
            row = cursor.fetchone()
            if not row:
                return 0

            rec_id = int(row[0])
            evaluated_at_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

            cursor.execute(
                """
                UPDATE ai_recommendations
                SET evaluated = 1,
                    evaluated_at_utc = ?,
                    exit_price = ?,
                    exit_time_utc = ?,
                    exit_reason = ?,
                    pnl_pct = ?
                WHERE id = ?
                """,
                (
                    evaluated_at_utc,
                    float(exit_price) if exit_price is not None else None,
                    exit_time,
                    exit_reason,
                    float(pnl_pct) if pnl_pct is not None else None,
                    rec_id,
                ),
            )
            conn.commit()
            return cursor.rowcount or 0
        except Exception:
            return 0
        finally:
            conn.close()

    def fetch_dataset(
        self,
        mode: Optional[str] = None,
        symbol: Optional[str] = None,
        evaluated_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Dict[str, Any]]:
        """Return a slice of the recommendations dataset for inspection.

        This is intentionally simple: basic filters + paging, ordered by
        generated_at_utc DESC so recent ideas come first.
        """

        safe_limit = max(1, min(int(limit or 1), 500))
        safe_offset = max(0, int(offset or 0))

        where_clauses = []
        params: list[Any] = []

        if mode:
            where_clauses.append("mode = ?")
            params.append(str(mode))

        if symbol:
            where_clauses.append("symbol = ?")
            params.append(str(symbol).upper())

        if evaluated_only:
            where_clauses.append("evaluated = 1")

        where_sql = ""
        if where_clauses:
            where_sql = " WHERE " + " AND ".join(where_clauses)

        sql = (
            "SELECT "
            "id, symbol, mode, universe, source, recommendation, direction, "
            "generated_at_utc, entry_price, stop_loss_price, target_price, "
            "score_blend, confidence, run_id, rank_in_run, policy_version, "
            "evaluated, evaluated_at_utc, exit_price, exit_time_utc, "
            "exit_reason, pnl_pct "
            "FROM ai_recommendations" + where_sql +
            " ORDER BY generated_at_utc DESC LIMIT ? OFFSET ?"
        )

        params.extend([safe_limit, safe_offset])

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
        finally:
            conn.close()

        results: list[Dict[str, Any]] = []
        for (
            rec_id,
            symbol_val,
            mode_val,
            universe_val,
            source_val,
            recommendation_val,
            direction_val,
            generated_at_val,
            entry_price_val,
            stop_loss_price_val,
            target_price_val,
            score_blend_val,
            confidence_val,
            run_id_val,
            rank_in_run_val,
            policy_version_val,
            evaluated_val,
            evaluated_at_val,
            exit_price_val,
            exit_time_val,
            exit_reason_val,
            pnl_pct_val,
        ) in rows:
            results.append(
                {
                    "id": rec_id,
                    "symbol": symbol_val,
                    "mode": mode_val,
                    "universe": universe_val,
                    "source": source_val,
                    "recommendation": recommendation_val,
                    "direction": direction_val,
                    "generated_at_utc": generated_at_val,
                    "entry_price": entry_price_val,
                    "stop_loss_price": stop_loss_price_val,
                    "target_price": target_price_val,
                    "score_blend": score_blend_val,
                    "confidence": confidence_val,
                    "run_id": run_id_val,
                    "rank_in_run": rank_in_run_val,
                    "policy_version": policy_version_val,
                    "evaluated": evaluated_val,
                    "evaluated_at_utc": evaluated_at_val,
                    "exit_price": exit_price_val,
                    "exit_time_utc": exit_time_val,
                    "exit_reason": exit_reason_val,
                    "pnl_pct": pnl_pct_val,
                }
            )

        return results


_ai_recommendation_store = AiRecommendationStore()


def get_ai_recommendation_store() -> AiRecommendationStore:
    return _ai_recommendation_store
