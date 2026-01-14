"""
Agent Learning Model
Stores agent learning patterns for ML improvement
"""

from sqlalchemy import Column, String, Integer, Float, DateTime, Index
from sqlalchemy.sql import func
from app.config.database import Base


class AgentLearning(Base):
    """
    Agent Learning tracking for ML improvements
    
    Stores patterns recognized by agents with accuracy metrics
    for continuous learning and improvement.
    """
    
    __tablename__ = "agent_learnings"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Learning details
    agent_type = Column(String(100), nullable=False, index=True)
    pattern_recognized = Column(String(255), nullable=False)
    
    # Performance metrics
    accuracy = Column(Float, nullable=True)
    sample_size = Column(Integer, nullable=True)
    
    # Timestamps
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_agent_learning_agent_type', 'agent_type'),
        Index('idx_agent_learning_updated', 'last_updated'),
    )
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "agent_type": self.agent_type,
            "pattern_recognized": self.pattern_recognized,
            "accuracy": self.accuracy,
            "sample_size": self.sample_size,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self):
        return f"<AgentLearning(id={self.id}, agent_type={self.agent_type}, pattern={self.pattern_recognized})>"
