from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class StrategyProfile(BaseModel):
    """Minimal shared model for strategy configuration metadata.

    This is intentionally flexible so different strategies (S1, S2, S3, etc.)
    can attach their own indicator/entry/exit configuration without tightly
    coupling the backend.
    """

    id: str
    name: str
    mode: str
    timeframe: str
    direction: Optional[str] = None  # LONG / SHORT when known
    version: int = 1

    indicator_params: Dict[str, Any] = Field(default_factory=dict)
    entry_criteria: Dict[str, Any] = Field(default_factory=dict)
    exit_criteria: Dict[str, Any] = Field(default_factory=dict)
    bearish_execution: Dict[str, Any] = Field(default_factory=dict)


class StrategyAdvisory(BaseModel):
    """Runtime advisory event emitted by strategy monitors (e.g. S1).

    These advisories are *advisory-only* in v1: they do not perform any
    automated exits, but they do carry enough information to drive UI hints
    and downstream KPI evaluation (via recommended_exit_price).
    """

    id: str  # Stable identifier for this advisory type
    strategy_id: str
    kind: str  # e.g. CONTEXT_INVALIDATED, PARTIAL_PROFIT, TREND_WEAKENING
    severity: str = "info"  # info | warning | high | critical
    enforcement: str = "ADVISORY_ONLY"
    # Whether this advisory should be treated as an effective exit signal in
    # downstream analytics (e.g. Winning Trades). When True, performance
    # analytics are allowed to map this advisory into a closed trade with an
    # associated exit_time/exit_price. When False, the advisory is treated as
    # informational-only ("advisory-not for action") and must not change
    # trade status or exit timestamps.
    is_exit: bool = True

    symbol: Optional[str] = None
    position_id: Optional[str] = None
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    direction: Optional[str] = None  # LONG / SHORT
    price: Optional[float] = None
    entry_price: Optional[float] = None
    initial_sl: Optional[float] = None
    rr_multiple: Optional[float] = None

    indicators: Dict[str, Any] = Field(default_factory=dict)

    message: str
    recommended_actions: List[Dict[str, Any]] = Field(default_factory=list)

    # Key field for KPI evaluation: the price at which the strategy
    # effectively "says exit" (virtual exit for advisory-only mode).
    recommended_exit_price: Optional[float] = None
    sr_reason: Optional[str] = None
    news_reason: Optional[str] = None
    news_risk_score: Optional[float] = None
