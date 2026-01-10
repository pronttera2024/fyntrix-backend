import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from ..db import Base


class BrokerName(str, enum.Enum):
    ZERODHA = "ZERODHA"
    ANGEL_ONE = "ANGEL_ONE"
    ICICI_DIRECT = "ICICI_DIRECT"
    HDFC_SECURITIES = "HDFC_SECURITIES"


class BrokerConnectionStatus(str, enum.Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    EXPIRED = "EXPIRED"


class TradeIntentSource(str, enum.Enum):
    CHART = "CHART"
    STRATEGY = "STRATEGY"


class Segment(str, enum.Enum):
    CASH = "CASH"
    FNO = "FNO"


class Product(str, enum.Enum):
    CNC = "CNC"
    MIS = "MIS"
    NRML = "NRML"


class Side(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, enum.Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SLM = "SLM"


class TradeIntentState(str, enum.Enum):
    CREATED = "CREATED"
    SUBMITTED_TO_BROKER = "SUBMITTED_TO_BROKER"
    ACCEPTED = "ACCEPTED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


def _uuid_str() -> str:
    return str(uuid.uuid4())


class BrokerConnection(Base):
    __tablename__ = "broker_connections"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    account_id = Column(String(128), index=True, nullable=False)
    broker = Column(String(32), index=True, nullable=False)
    status = Column(String(16), nullable=False, default=BrokerConnectionStatus.DISCONNECTED.value)

    client_user_id = Column(String(128))
    scopes = Column(Text)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class BrokerToken(Base):
    __tablename__ = "broker_tokens"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    broker_connection_id = Column(String(36), ForeignKey("broker_connections.id", ondelete="CASCADE"), nullable=False, index=True)

    access_token_enc = Column(Text, nullable=False)
    refresh_token_enc = Column(Text)
    expires_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class TradeIntent(Base):
    __tablename__ = "trade_intents"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    account_id = Column(String(128), index=True, nullable=False)
    session_id = Column(String(128), index=True)

    broker = Column(String(32), index=True, nullable=False)
    source = Column(String(16), nullable=False)

    symbol = Column(String(64), index=True, nullable=False)
    exchange = Column(String(16))
    segment = Column(String(8), nullable=False)
    product = Column(String(8), nullable=False)

    side = Column(String(8), nullable=False)
    qty = Column(Integer, nullable=False)
    order_type = Column(String(8), nullable=False)

    limit_price = Column(Float)
    trigger_price = Column(Float)
    stop_loss = Column(Float)
    target = Column(Float)

    state = Column(String(32), index=True, nullable=False, default=TradeIntentState.CREATED.value)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class BrokerOrder(Base):
    __tablename__ = "broker_orders"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    trade_intent_id = Column(String(36), ForeignKey("trade_intents.id", ondelete="CASCADE"), nullable=False, index=True)

    broker = Column(String(32), index=True, nullable=False)
    broker_order_id = Column(String(128), index=True)

    status = Column(String(32), index=True)
    filled_qty = Column(Integer)
    average_price = Column(Float)
    raw_response_redacted = Column(Text)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    account_id = Column(String(128), index=True, nullable=False)
    broker = Column(String(32), index=True, nullable=False)

    kind = Column(String(16), nullable=False)
    as_of = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    payload = Column(Text, nullable=False)
    is_latest = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
