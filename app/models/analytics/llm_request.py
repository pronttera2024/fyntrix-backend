"""
LLM Request Model
Tracks OpenAI API usage and costs for billing and analytics
"""

from sqlalchemy import Column, String, Integer, Float, DateTime, Index
from sqlalchemy.sql import func
from app.config.database import Base


class LLMRequest(Base):
    """
    LLM API Request tracking for cost management and analytics
    
    Stores every OpenAI API call with token usage and cost information
    for billing, budgeting, and usage analytics.
    """
    
    __tablename__ = "llm_requests"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Request details
    model = Column(String(100), nullable=False, index=True)
    tokens_input = Column(Integer, nullable=True)
    tokens_output = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_llm_requests_created_at', 'created_at'),
        Index('idx_llm_requests_model_date', 'model', 'created_at'),
    )
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "model": self.model,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "cost_usd": self.cost_usd,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self):
        return f"<LLMRequest(id={self.id}, model={self.model}, cost=${self.cost_usd:.4f})>"
