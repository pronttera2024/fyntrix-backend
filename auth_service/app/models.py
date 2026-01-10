import uuid

from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID
from sqlalchemy.sql import func

from .db import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idp_sub = Column(Text, nullable=False)
    idp_issuer = Column(Text, nullable=False)
    email = Column(Text, nullable=False)
    email_verified = Column(Boolean, nullable=False, default=False)
    preferred_username = Column(Text)
    status = Column(Text, nullable=False, default="active")
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class UserPersona(Base):
    __tablename__ = "user_personas"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    trader_type = Column(Text, nullable=False)
    goals = Column(ARRAY(Text), nullable=False, default=list)
    feature_prefs = Column(ARRAY(Text), nullable=False, default=list)
    risk_tolerance = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class KYCProfile(Base):
    __tablename__ = "kyc_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider = Column(Text, nullable=False)
    provider_reference = Column(Text)
    status = Column(Text, nullable=False)
    last_checked_at = Column(TIMESTAMP(timezone=True))
    details = Column(JSONB)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_code = Column(Text, nullable=False)
    status = Column(Text, nullable=False)
    current_period_start = Column(TIMESTAMP(timezone=True))
    current_period_end = Column(TIMESTAMP(timezone=True))
    cancel_at = Column(TIMESTAMP(timezone=True))
    canceled_at = Column(TIMESTAMP(timezone=True))
    payment_provider = Column(Text)
    payment_customer_id = Column(Text)
    payment_subscription_id = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    idp_sub = Column(Text)
    session_id = Column(Text)
    event_type = Column(Text, nullable=False)
    occurred_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    ip = Column(INET)
    user_agent = Column(Text)
    auth_method = Column(Text)
    data = Column(JSONB)
