"""Portfolio Snapshot Model"""
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, func, Index
from sqlalchemy.dialects.postgresql import JSONB
from app.db import Base


class PortfolioSnapshot(Base):
    """Track portfolio positions over time for historical analysis"""
    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Snapshot type
    snapshot_type = Column(String(50), nullable=False, index=True)  # 'positions', 'watchlist'
    
    # Portfolio metrics
    total_positions = Column(Integer, nullable=True)
    total_value = Column(Float, nullable=True)
    total_pnl = Column(Float, nullable=True)
    total_pnl_pct = Column(Float, nullable=True)
    
    # Detailed data (JSON)
    positions_json = Column(JSONB, nullable=True)
    metadata_json = Column(JSONB, nullable=True)
    
    # Timestamps
    snapshot_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Indexes
    __table_args__ = (
        Index('idx_portfolio_snapshot_type_time', 'snapshot_type', 'snapshot_at'),
        {'extend_existing': True}
    )
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'snapshot_type': self.snapshot_type,
            'total_positions': self.total_positions,
            'total_value': self.total_value,
            'total_pnl': self.total_pnl,
            'total_pnl_pct': self.total_pnl_pct,
            'positions_json': self.positions_json,
            'metadata_json': self.metadata_json,
            'snapshot_at': self.snapshot_at.isoformat() if self.snapshot_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
