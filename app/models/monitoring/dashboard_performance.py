"""Dashboard Performance Tracking Model"""
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, func
from sqlalchemy.dialects.postgresql import JSONB
from app.db import Base


class DashboardPerformance(Base):
    """Track dashboard performance metrics over time for historical analytics"""
    __tablename__ = "dashboard_performance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Time period
    period_type = Column(String(20), nullable=False, index=True)  # '7d', '30d', etc.
    
    # Performance metrics
    total_recommendations = Column(Integer, nullable=True)
    evaluated_count = Column(Integer, nullable=True)
    win_rate = Column(Float, nullable=True)
    avg_pnl_pct = Column(Float, nullable=True)
    total_pnl_pct = Column(Float, nullable=True)
    
    # Detailed metrics (JSON)
    metrics_json = Column(JSONB, nullable=True)
    recommendations_json = Column(JSONB, nullable=True)
    
    # Timestamps
    snapshot_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'period_type': self.period_type,
            'total_recommendations': self.total_recommendations,
            'evaluated_count': self.evaluated_count,
            'win_rate': self.win_rate,
            'avg_pnl_pct': self.avg_pnl_pct,
            'total_pnl_pct': self.total_pnl_pct,
            'metrics_json': self.metrics_json,
            'recommendations_json': self.recommendations_json,
            'snapshot_at': self.snapshot_at.isoformat() if self.snapshot_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
