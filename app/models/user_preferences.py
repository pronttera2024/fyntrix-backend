from datetime import datetime
from sqlalchemy import Column, String, Boolean, JSON, DateTime, ForeignKey
from sqlalchemy.sql import func
from ..config.database import Base


class UserPreferences(Base):
    """User preferences and settings model"""
    __tablename__ = "user_preferences"
    
    # Primary key - user_id (one-to-one with users table)
    user_id = Column(String(255), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, comment="User ID (FK to users)")
    
    # Disclosure and onboarding
    disclosure_accepted = Column(Boolean, nullable=False, default=False, comment="Whether user accepted disclosure")
    disclosure_version = Column(String(20), nullable=True, comment="Version of disclosure accepted (e.g., v1)")
    
    # Market preferences
    universe = Column(String(50), nullable=False, default="NIFTY50", comment="Stock universe (NIFTY50, NIFTY500, etc.)")
    market_region = Column(String(20), nullable=False, default="India", comment="Market region (India, Global)")
    
    # Risk profile
    risk_profile = Column(String(20), nullable=False, default="Moderate", comment="Risk profile (Aggressive, Moderate, Conservative)")
    
    # Trading modes (JSON object: {Intraday: bool, Swing: bool, Options: bool, Futures: bool})
    trading_modes = Column(JSON, nullable=True, comment="Trading modes as JSON object")
    primary_mode = Column(String(20), nullable=True, comment="Primary trading mode")
    auxiliary_modes = Column(JSON, nullable=True, comment="Auxiliary trading modes as JSON array")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="Preferences creation timestamp")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False, comment="Last update timestamp")
    
    def __repr__(self):
        return f"<UserPreferences(user_id={self.user_id}, universe={self.universe}, risk={self.risk_profile})>"
    
    def to_dict(self):
        """Convert preferences to dictionary"""
        return {
            "user_id": self.user_id,
            "disclosure_accepted": self.disclosure_accepted,
            "disclosure_version": self.disclosure_version,
            "universe": self.universe,
            "market_region": self.market_region,
            "risk_profile": self.risk_profile,
            "trading_modes": self.trading_modes,
            "primary_mode": self.primary_mode,
            "auxiliary_modes": self.auxiliary_modes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
