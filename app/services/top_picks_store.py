"""Top Picks Runs Store

SQLite-backed persistent storage for Top Picks engine runs.

Each run corresponds to a (universe, mode) evaluation by the TopPicksEngine
and is stored append-only for analytics, performance tracking, and
compliance/audit use cases.
"""

import os
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional


class TopPicksStore:
    """SQLite-based storage for top picks runs.

    Uses a dedicated database file (cache/top_picks_runs.db) separate from
    other context/cost tracking DBs.
    """

    def __init__(self, db_path: str = "cache/top_picks_runs.db", retention_days: Optional[int] = None) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Retention policy (in days). Default 90, configurable up to e.g. 5 years
        env_retention = os.getenv("TOP_PICKS_RETENTION_DAYS")
        if retention_days is not None:
            self.retention_days = retention_days
        elif env_retention:
            try:
                self.retention_days = int(env_retention)
            except ValueError:
                self.retention_days = 90
        else:
            self.retention_days = 90

        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS top_picks_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                universe TEXT NOT NULL,
                mode TEXT NOT NULL,
                generated_at_utc TEXT NOT NULL,
                trigger TEXT NOT NULL,
                total_analyzed INTEGER,
                filtered_count INTEGER,
                picks_count INTEGER,
                elapsed_sec REAL,
                payload TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tpr_universe_mode_time
            ON top_picks_runs (universe, mode, generated_at_utc DESC)
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tpr_run_id
            ON top_picks_runs (run_id)
            """
        )

        conn.commit()
        conn.close()

    def store_run(self, picks_data: Dict[str, Any], trigger: str) -> str:
        """Store a single Top Picks run.

        Args:
            picks_data: The full picks payload returned by TopPicksEngine.
            trigger:   Logical trigger label (e.g. 'preopen', 'hourly',
                       'scalping_cycle', 'manual', 'scheduler').

        Returns:
            Generated run_id string for this run.
        """
        universe = str(picks_data.get("universe") or "").lower()
        mode = str(picks_data.get("mode") or "").title()

        # Use UTC timestamp for retention / time-based queries
        generated_at_utc = datetime.utcnow().isoformat()

        # Simple deterministic run identifier
        run_id = f"{universe}:{mode}:{generated_at_utc}"

        total_analyzed = int(picks_data.get("total_analyzed") or 0)
        filtered_count = int(picks_data.get("passed_filter") or 0)
        picks_count = int(picks_data.get("picks_count") or len(picks_data.get("picks") or []))
        elapsed_sec: Optional[float] = None
        try:
            elapsed_meta = picks_data.get("metadata", {}).get("analysis_time_seconds")
            if isinstance(elapsed_meta, (int, float)):
                elapsed_sec = float(elapsed_meta)
        except Exception:
            elapsed_sec = None

        payload_json = json.dumps(picks_data)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO top_picks_runs (
                run_id,
                universe,
                mode,
                generated_at_utc,
                trigger,
                total_analyzed,
                filtered_count,
                picks_count,
                elapsed_sec,
                payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                universe,
                mode,
                generated_at_utc,
                trigger,
                total_analyzed,
                filtered_count,
                picks_count,
                elapsed_sec,
                payload_json,
            ),
        )

        conn.commit()
        conn.close()

        # Best-effort cleanup based on retention policy
        try:
            self.cleanup_old_runs()
        except Exception:
            # Soft-fail: do not break primary flow if cleanup fails
            pass

        return run_id

    def get_latest_run_for(self, universe: str, mode: str) -> Optional[Dict[str, Any]]:
        """Return the most recent Top Picks run for a (universe, mode) pair.

        The return structure matches the lightweight scheduler payload used by
        TopPicksScheduler/TOP_PICKS_CACHE so it can be dropped in as a cache
        entry for UI reads.
        """

        universe_key = str(universe or "").lower()
        mode_key = str(mode or "").title()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT payload
            FROM top_picks_runs
            WHERE universe = ?
              AND mode = ?
              AND picks_count IS NOT NULL
              AND picks_count > 0
            ORDER BY generated_at_utc DESC
            LIMIT 1
            """,
            (universe_key, mode_key),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        try:
            data = json.loads(row[0])
        except Exception:
            return None

        if not isinstance(data, dict):
            return None

        items = data.get("picks") or []

        # Prefer engine's generated_at field, fall back to current UTC time
        as_of = data.get("generated_at") or datetime.utcnow().isoformat() + "Z"

        elapsed = None
        try:
            elapsed_meta = data.get("metadata", {}).get("analysis_time_seconds")
            if isinstance(elapsed_meta, (int, float)):
                elapsed = float(elapsed_meta)
        except Exception:
            elapsed = None

        payload: Dict[str, Any] = {
            "items": items,
            "as_of": as_of,
            "universe": data.get("universe", universe_key),
            "mode": data.get("mode", mode_key),
        }

        if elapsed is not None:
            payload["elapsed_seconds"] = elapsed

        return payload

    def get_run_by_id(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Return the original engine payload for a specific run_id.

        This is used by analytics to rehydrate full pick structures (including
        agent scores and metadata) when the lightweight scheduler logs are
        missing some fields.
        """

        if not run_id:
            return None

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT payload
                FROM top_picks_runs
                WHERE run_id = ?
                LIMIT 1
                """,
                (run_id,),
            )
            row = cursor.fetchone()
        finally:
            conn.close()

        if not row:
            return None

        try:
            data = json.loads(row[0])
        except Exception:
            return None

        return data if isinstance(data, dict) else None

    def query_runs(
        self,
        universe: Optional[str] = None,
        mode: Optional[str] = None,
        trigger: Optional[str] = None,
        start_utc: Optional[str] = None,
        end_utc: Optional[str] = None,
        limit: int = 500,
    ) -> list[Dict[str, Any]]:
        """Query multiple top picks runs for analytics / audit purposes.

        Returns a list of dicts containing run metadata plus the original
        engine payload for each run. All arguments are optional filters.
        """

        # Normalise filters to match how store_run persists values
        universe_key = universe.lower() if universe else None
        mode_key = mode.title() if mode else None

        # Build WHERE clause dynamically
        where_clauses: list[str] = []
        params: list[Any] = []

        if universe_key:
            where_clauses.append("universe = ?")
            params.append(universe_key)

        if mode_key:
            where_clauses.append("mode = ?")
            params.append(mode_key)

        if trigger:
            where_clauses.append("trigger = ?")
            params.append(trigger)

        # Time window filters (ISO8601 strings)
        if start_utc:
            try:
                start_dt = datetime.fromisoformat(start_utc)
                where_clauses.append("generated_at_utc >= ?")
                params.append(start_dt.isoformat())
            except Exception:
                pass

        if end_utc:
            try:
                end_dt = datetime.fromisoformat(end_utc)
                where_clauses.append("generated_at_utc <= ?")
                params.append(end_dt.isoformat())
            except Exception:
                pass

        where_sql = ""
        if where_clauses:
            where_sql = " WHERE " + " AND ".join(where_clauses)

        # Clamp limit defensively
        safe_limit = max(1, min(int(limit or 1), 5000))

        sql = (
            "SELECT run_id, universe, mode, generated_at_utc, trigger, "
            "total_analyzed, filtered_count, picks_count, elapsed_sec, payload "
            "FROM top_picks_runs" + where_sql + " ORDER BY generated_at_utc DESC LIMIT ?"
        )

        params.append(safe_limit)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
        finally:
            conn.close()

        results: list[Dict[str, Any]] = []

        for (
            run_id_val,
            universe_val,
            mode_val,
            generated_at,
            trigger_val,
            total_analyzed,
            filtered_count,
            picks_count,
            elapsed_sec,
            payload_json,
        ) in rows:
            try:
                payload = json.loads(payload_json)
            except Exception:
                payload = None

            results.append(
                {
                    "run_id": run_id_val,
                    "universe": universe_val,
                    "mode": mode_val,
                    "generated_at_utc": generated_at,
                    "trigger": trigger_val,
                    "total_analyzed": total_analyzed,
                    "filtered_count": filtered_count,
                    "picks_count": picks_count,
                    "elapsed_sec": elapsed_sec,
                    "payload": payload,
                }
            )

        return results

    def cleanup_old_runs(self, retention_days: Optional[int] = None) -> int:
        """Remove runs older than the configured retention window.

        Args:
            retention_days: Optional override; if None, uses instance default.

        Returns:
            Number of deleted rows.
        """
        days = self.retention_days if retention_days is None else retention_days
        if days is None or days <= 0:
            # Non-positive means "no cleanup" (infinite retention)
            return 0

        cutoff = datetime.utcnow() - timedelta(days=days)
        cutoff_str = cutoff.isoformat()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM top_picks_runs
            WHERE generated_at_utc < ?
            """,
            (cutoff_str,),
        )

        deleted = cursor.rowcount
        conn.commit()
        conn.close()

        return deleted


# Global store instance
_top_picks_store = TopPicksStore()


def get_top_picks_store() -> TopPicksStore:
    return _top_picks_store
