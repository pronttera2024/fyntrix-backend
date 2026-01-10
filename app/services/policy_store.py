"""Policy Store

Centralized loader for mode-specific policy configuration used by the
TopPicksEngine and analytics layer.

Unifies:
- Mode agent weights from config/mode_weights.json
- Evaluation horizons from config/performance_horizons.json

This is intentionally read-only at runtime; offline learners and human
operators update the JSON configs and bump the version field.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import json


@dataclass
class ModePolicy:
    mode: str
    weights: Dict[str, float]
    horizon_type: Optional[str] = None
    horizon_days: Optional[int] = None
    thresholds: Dict[str, Any] = None


class PolicyStore:
    """Loads and exposes policy configuration for trading modes."""

    def __init__(self) -> None:
        root = Path(__file__).parent.parent.parent
        self._mode_weights_path = root / "config" / "mode_weights.json"
        self._horizons_path = root / "config" / "performance_horizons.json"

        self._policy_version: str = "1.0"
        self._weights_raw: Dict[str, Any] = {}
        self._horizons_raw: Dict[str, Any] = {}

        self._load_configs()

    def _load_configs(self) -> None:
        # Load mode weights
        try:
            with open(self._mode_weights_path, "r") as f:
                mw = json.load(f)
        except Exception:
            mw = {}

        self._policy_version = str(mw.get("version", self._policy_version))
        self._weights_raw = mw.get("modes", {}) or {}

        # Load horizons
        try:
            with open(self._horizons_path, "r") as f:
                self._horizons_raw = json.load(f) or {}
        except Exception:
            self._horizons_raw = {}

    def reload(self) -> None:
        """Reload policy configuration from disk (for hot config updates)."""
        self._load_configs()

    def get_policy_version(self) -> str:
        """Return the current policy version string."""
        return self._policy_version

    def get_mode_policy(self, mode: str) -> ModePolicy:
        """Return unified policy for a mode.

        Args:
            mode: Trading mode name (e.g. "Scalping", "Intraday", "Swing").
        """
        mode_key = str(mode or "").strip() or "Swing"

        # Weights
        mode_cfg = self._weights_raw.get(mode_key) or {}
        weights = mode_cfg.get("weights", {}) or {}

        # Optional thresholds section can be added into mode_weights.json later
        thresholds = mode_cfg.get("thresholds", {}) or {}

        # Horizons
        hz_cfg = self._horizons_raw.get(mode_key) or {}
        horizon_type = hz_cfg.get("type")
        horizon_days = hz_cfg.get("days")

        return ModePolicy(
            mode=mode_key,
            weights=weights,
            horizon_type=horizon_type,
            horizon_days=horizon_days,
            thresholds=thresholds,
        )


_policy_store = PolicyStore()


def get_policy_store() -> PolicyStore:
    return _policy_store
