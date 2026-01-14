from sqlalchemy import Column, Integer, String, Float, DateTime, Date, Text, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from datetime import datetime
from typing import Dict, Any, Optional

from ..config.database import Base


class PickEvent(Base):
    """Trading pick events - signals and recommendations"""
    __tablename__ = "pick_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pick_uuid = Column(String(36), nullable=False, unique=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    direction = Column(String(10), nullable=False)  # LONG/SHORT
    source = Column(String(50), nullable=False)
    mode = Column(String(20), nullable=False)
    signal_ts = Column(DateTime(timezone=True), nullable=False)
    trade_date = Column(Date, nullable=False, index=True)
    signal_price = Column(Float, nullable=False)

    # Optional recommendation fields
    recommended_entry = Column(Float, nullable=True)
    recommended_target = Column(Float, nullable=True)
    recommended_stop = Column(Float, nullable=True)

    # Analysis fields
    time_horizon = Column(String(20), nullable=True)
    blend_score = Column(Float, nullable=True)
    recommendation = Column(Text, nullable=True)
    confidence = Column(String(20), nullable=True)

    # Market context
    regime = Column(String(50), nullable=True)
    risk_profile_bucket = Column(String(20), nullable=True)
    mode_bucket = Column(String(20), nullable=True)
    universe = Column(String(50), nullable=True)
    extra_context = Column(JSONB, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    agent_contributions = relationship("PickAgentContribution", back_populates="pick_event", cascade="all, delete-orphan")
    outcomes = relationship("PickOutcome", back_populates="pick_event", cascade="all, delete-orphan")

    # Indexes for performance
    __table_args__ = (
        Index('idx_pick_events_symbol_date', 'symbol', 'trade_date'),
        Index('idx_pick_events_trade_date', 'trade_date'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'pick_uuid': self.pick_uuid,
            'symbol': self.symbol,
            'direction': self.direction,
            'source': self.source,
            'mode': self.mode,
            'signal_ts': self.signal_ts.isoformat() if self.signal_ts else None,
            'trade_date': self.trade_date.isoformat() if self.trade_date else None,
            'signal_price': self.signal_price,
            'recommended_entry': self.recommended_entry,
            'recommended_target': self.recommended_target,
            'recommended_stop': self.recommended_stop,
            'time_horizon': self.time_horizon,
            'blend_score': self.blend_score,
            'recommendation': self.recommendation,
            'confidence': self.confidence,
            'regime': self.regime,
            'risk_profile_bucket': self.risk_profile_bucket,
            'mode_bucket': self.mode_bucket,
            'universe': self.universe,
            'extra_context': self.extra_context,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class PickAgentContribution(Base):
    """Individual agent contributions to pick decisions"""
    __tablename__ = "pick_agent_contributions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pick_uuid = Column(String(36), ForeignKey('pick_events.pick_uuid', ondelete='CASCADE'), nullable=False, index=True)
    agent_name = Column(String(100), nullable=False, index=True)
    score = Column(Float, nullable=True)
    confidence = Column(String(20), nullable=True)
    agent_metadata = Column(JSONB, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    pick_event = relationship("PickEvent", back_populates="agent_contributions")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'pick_uuid': self.pick_uuid,
            'agent_name': self.agent_name,
            'score': self.score,
            'confidence': self.confidence,
            'agent_metadata': self.agent_metadata,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class PickOutcome(Base):
    """Realized outcomes for trading picks"""
    __tablename__ = "pick_outcomes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pick_uuid = Column(String(36), ForeignKey('pick_events.pick_uuid', ondelete='CASCADE'), nullable=False, index=True)
    evaluation_horizon = Column(String(20), nullable=False)

    # Price data at horizon end
    horizon_end_ts = Column(DateTime(timezone=True), nullable=False)
    price_close = Column(Float, nullable=True)
    price_high = Column(Float, nullable=True)
    price_low = Column(Float, nullable=True)

    # Return metrics
    ret_close_pct = Column(Float, nullable=True)
    max_runup_pct = Column(Float, nullable=True)
    max_drawdown_pct = Column(Float, nullable=True)

    # Benchmark comparison
    benchmark_symbol = Column(String(20), nullable=True)
    benchmark_ret_pct = Column(Float, nullable=True)
    ret_vs_benchmark_pct = Column(Float, nullable=True)

    # Target/stop analysis
    hit_target = Column(Boolean, nullable=True)
    hit_stop = Column(Boolean, nullable=True)

    # Classification
    outcome_label = Column(String(20), nullable=True, index=True)  # WIN/LOSS/BREAKEVEN
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    pick_event = relationship("PickOutcome", back_populates="outcomes")

    # Unique constraint to prevent duplicate outcomes per pick/horizon
    __table_args__ = (
        UniqueConstraint('pick_uuid', 'evaluation_horizon', name='uq_pick_outcome'),
        Index('idx_pick_outcomes_label', 'outcome_label'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'pick_uuid': self.pick_uuid,
            'evaluation_horizon': self.evaluation_horizon,
            'horizon_end_ts': self.horizon_end_ts.isoformat() if self.horizon_end_ts else None,
            'price_close': self.price_close,
            'price_high': self.price_high,
            'price_low': self.price_low,
            'ret_close_pct': self.ret_close_pct,
            'max_runup_pct': self.max_runup_pct,
            'max_drawdown_pct': self.max_drawdown_pct,
            'benchmark_symbol': self.benchmark_symbol,
            'benchmark_ret_pct': self.benchmark_ret_pct,
            'ret_vs_benchmark_pct': self.ret_vs_benchmark_pct,
            'hit_target': self.hit_target,
            'hit_stop': self.hit_stop,
            'outcome_label': self.outcome_label,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class RlPolicy(Base):
    """Reinforcement Learning policy configurations"""
    __tablename__ = "rl_policies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    policy_id = Column(String(36), nullable=False, unique=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # Status and lifecycle
    status = Column(String(20), nullable=False, index=True)  # DRAFT/ACTIVE/RETIRED
    config_json = Column(JSONB, nullable=False)
    metrics_json = Column(JSONB, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    activated_at = Column(DateTime(timezone=True), nullable=True)
    deactivated_at = Column(DateTime(timezone=True), nullable=True)

    # Indexes for performance
    __table_args__ = (
        Index('idx_rl_policies_status', 'status'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'policy_id': self.policy_id,
            'name': self.name,
            'description': self.description,
            'status': self.status,
            'config': self.config_json,
            'metrics': self.metrics_json,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'activated_at': self.activated_at.isoformat() if self.activated_at else None,
            'deactivated_at': self.deactivated_at.isoformat() if self.deactivated_at else None,
        }
