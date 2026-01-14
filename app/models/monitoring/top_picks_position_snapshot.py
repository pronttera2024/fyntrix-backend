"""Top Picks Position Snapshot Model"""
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, func, Index
from sqlalchemy.dialects.postgresql import JSONB
from app.db import Base


class TopPicksPositionSnapshot(Base):
    """Track top picks positions over time for performance analytics"""
    __tablename__ = "top_picks_position_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Universe and mode
    universe = Column(String(50), nullable=False, index=True)
    mode = Column(String(50), nullable=False, index=True)
    
    # Position metrics
    total_positions = Column(Integer, nullable=True)
    active_positions = Column(Integer, nullable=True)
    total_pnl = Column(Float, nullable=True)
    total_pnl_pct = Column(Float, nullable=True)
    win_count = Column(Integer, nullable=True)
    loss_count = Column(Integer, nullable=True)
    
    # Detailed data (JSON)
    positions_json = Column(JSONB, nullable=True)
    metadata_json = Column(JSONB, nullable=True)
    
    # Timestamps
    snapshot_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Indexes
    __table_args__ = (
        Index('idx_tpps_universe_mode_time', 'universe', 'mode', 'snapshot_at'),
    )
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'universe': self.universe,
            'mode': self.mode,
            'total_positions': self.total_positions,
            'active_positions': self.active_positions,
            'total_pnl': self.total_pnl,
            'total_pnl_pct': self.total_pnl_pct,
            'win_count': self.win_count,
            'loss_count': self.loss_count,
            'positions_json': self.positions_json,
            'metadata_json': self.metadata_json,
            'snapshot_at': self.snapshot_at.isoformat() if self.snapshot_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
