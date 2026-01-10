"""Offline Policy Learner Skeleton

Reads evaluated AI recommendations grouped by mode and policy_version and
emits a candidate mode_weights.json config with a bumped version for human
review. This does not change the live policy; it only writes a candidate
file alongside the existing config.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .ai_recommendation_store import get_ai_recommendation_store
from .policy_store import get_policy_store


@dataclass
class PolicyPerformanceSnapshot:
    mode: str
    policy_version: str
    count: int
    avg_pnl: float


class PolicyLearner:
    """Small offline learner skeleton for policy configuration.

    Intended to be run manually or on a cron/scheduled job. It inspects the
    ai_recommendations dataset, summarizes performance by (mode,
    policy_version), and writes a candidate mode_weights config that can be
    reviewed and, if approved, promoted to the live policy file.
    """

    def __init__(self, project_root: Optional[Path] = None) -> None:
        root = project_root or Path(__file__).parent.parent.parent
        self._config_path = root / "config" / "mode_weights.json"
        self._store = get_ai_recommendation_store()
        self._policy_store = get_policy_store()

    def _load_current_config(self) -> Dict[str, Any]:
        try:
            with open(self._config_path, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _query_performance(self) -> List[PolicyPerformanceSnapshot]:
        """Aggregate evaluated performance by mode and policy_version.

        This is deliberately simple: it uses average pnl_pct across all
        evaluated rows. More sophisticated learners can plug in here later.
        """

        conn = sqlite3.connect(self._store.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT
                    mode,
                    COALESCE(policy_version, ''),
                    COUNT(*) AS n,
                    AVG(COALESCE(pnl_pct, 0.0)) AS avg_pnl
                FROM ai_recommendations
                WHERE evaluated = 1
                GROUP BY mode, COALESCE(policy_version, '')
                """
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

        snapshots: List[PolicyPerformanceSnapshot] = []
        for mode, policy_version, n, avg_pnl in rows:
            snapshots.append(
                PolicyPerformanceSnapshot(
                    mode=str(mode or ""),
                    policy_version=str(policy_version or ""),
                    count=int(n or 0),
                    avg_pnl=float(avg_pnl or 0.0),
                )
            )

        return snapshots

    def _bump_version(self, current_version: str) -> str:
        """Generate a simple bumped version string for candidate policies."""
        s = str(current_version or "").strip()
        try:
            as_float = float(s)
            return f"{as_float + 0.1:.1f}"
        except Exception:
            ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
            base = s or "1.0"
            return f"{base}-candidate-{ts}"

    def generate_candidate_config(self, output_path: Optional[Path] = None) -> Dict[str, Any]:
        """Build and optionally write a candidate mode_weights config.

        The current implementation keeps weights unchanged and only bumps the
        version and attaches a performance snapshot. This establishes the
        end-to-end pipeline; future iterations can modify weights based on
        these statistics.
        """

        current = self._load_current_config()
        if not current:
            raise RuntimeError("Could not load current mode_weights.json")

        current_version = str(current.get("version", "1.0"))
        candidate_version = self._bump_version(current_version)
        performance = self._query_performance()

        # Shallow copy is fine; we overwrite top-level metadata keys below.
        candidate: Dict[str, Any] = dict(current)
        candidate["version"] = candidate_version

        meta = candidate.get("meta") or {}
        meta["last_learned_at"] = datetime.utcnow().isoformat() + "Z"
        meta["source_version"] = current_version
        meta["policy_version_at_runtime"] = self._policy_store.get_policy_version()
        meta["performance_snapshot"] = [
            {
                "mode": s.mode,
                "policy_version": s.policy_version,
                "count": s.count,
                "avg_pnl": s.avg_pnl,
            }
            for s in performance
        ]
        candidate["meta"] = meta

        target = output_path or (
            self._config_path.parent
            / f"mode_weights_candidate_{candidate_version.replace(' ', '_')}.json"
        )

        try:
            with open(target, "w") as f:
                json.dump(candidate, f, indent=2)
        except Exception:
            # Best-effort: if writing fails, still return the candidate dict.
            pass

        return candidate


def generate_candidate_policy(output_path: Optional[str] = None) -> Dict[str, Any]:
    """Convenience function for scripts / REPL usage."""
    learner = PolicyLearner()
    path_obj = Path(output_path) if output_path else None
    return learner.generate_candidate_config(path_obj)
