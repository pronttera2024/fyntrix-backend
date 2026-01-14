"""
Top Picks Run Model
Stores historical top picks runs for performance tracking and audit trail
"""

from sqlalchemy import Column, String, Integer, Text, DateTime, Index
from sqlalchemy.sql import func
from app.config.database import Base


class TopPicksRun(Base):
    """
    Top Picks Run tracking for historical analysis
    
    Stores every top picks generation run with full pick details
    for performance analysis and regulatory compliance.
    """
    
    __tablename__ = "top_picks_runs"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Run identification
    run_id = Column(String(100), unique=True, nullable=False, index=True)
    
    # Run configuration
    universe = Column(String(50), nullable=False, index=True)
    mode = Column(String(50), nullable=False, index=True)
    
    # Picks data (JSON stored as text)
    picks_json = Column(Text, nullable=False)
    
    # Metadata
    elapsed_seconds = Column(Integer, nullable=True)
    pick_count = Column(Integer, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_top_picks_universe_mode_time', 'universe', 'mode', 'created_at'),
        Index('idx_top_picks_created_at', 'created_at'),
    )
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "run_id": self.run_id,
            "universe": self.universe,
            "mode": self.mode,
            "picks_json": self.picks_json,
            "elapsed_seconds": self.elapsed_seconds,
            "pick_count": self.pick_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self):
        return f"<TopPicksRun(id={self.id}, run_id={self.run_id}, universe={self.universe}, mode={self.mode})>"
