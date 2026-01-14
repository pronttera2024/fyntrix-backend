"""
Agent Analysis Model
Stores agent analysis results for performance tracking and ML training
"""

from sqlalchemy import Column, String, Integer, Float, Text, DateTime, Index
from sqlalchemy.sql import func
from app.config.database import Base


class AgentAnalysis(Base):
    """
    Agent Analysis tracking for performance evaluation
    
    Stores every agent's analysis of a symbol with scores, signals,
    and reasoning for historical performance tracking.
    """
    
    __tablename__ = "agent_analyses"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Analysis details
    symbol = Column(String(20), nullable=False, index=True)
    agent_type = Column(String(100), nullable=False, index=True)
    
    # Scoring
    score = Column(Float, nullable=True)
    confidence = Column(String(20), nullable=True)
    
    # Analysis data (JSON stored as text)
    signals = Column(Text, nullable=True)
    reasoning = Column(Text, nullable=True)
    analysis_metadata = Column(Text, nullable=True)
    
    # Context (JSON stored as text)
    global_context = Column(Text, nullable=True)
    policy_context = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_agent_analysis_symbol_date', 'symbol', 'created_at'),
        Index('idx_agent_analysis_agent_symbol', 'agent_type', 'symbol', 'created_at'),
    )
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "symbol": self.symbol,
            "agent_type": self.agent_type,
            "score": self.score,
            "confidence": self.confidence,
            "signals": self.signals,
            "reasoning": self.reasoning,
            "analysis_metadata": self.analysis_metadata,
            "global_context": self.global_context,
            "policy_context": self.policy_context,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self):
        return f"<AgentAnalysis(id={self.id}, symbol={self.symbol}, agent_type={self.agent_type}, score={self.score})>"
