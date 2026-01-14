from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Index
from sqlalchemy.sql import func
from ..config.database import Base
import uuid


class UserWatchlist(Base):
    """User watchlist model"""
    __tablename__ = "user_watchlists"
    
    # Primary key
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="Watchlist entry ID")
    
    # Foreign key to users
    user_id = Column(String(255), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="User ID (FK to users)")
    
    # Stock information
    symbol = Column(String(50), nullable=False, comment="Stock symbol (e.g., RELIANCE, TCS)")
    exchange = Column(String(20), nullable=True, comment="Exchange (NSE, BSE, etc.)")
    
    # Optional metadata
    notes = Column(Text, nullable=True, comment="User notes about this stock")
    
    # Timestamps
    added_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="When stock was added to watchlist")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False, comment="Last update timestamp")
    
    # Unique constraint: user can't add same symbol twice
    __table_args__ = (
        Index('ix_user_watchlists_user_symbol', 'user_id', 'symbol', unique=True),
    )
    
    def __repr__(self):
        return f"<UserWatchlist(user_id={self.user_id}, symbol={self.symbol})>"
    
    def to_dict(self):
        """Convert watchlist entry to dictionary"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "notes": self.notes,
            "added_at": self.added_at.isoformat() if self.added_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
