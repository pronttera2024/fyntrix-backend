import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..deps import get_db
from ..security import TokenPayload, decode_token
from ..db_models.trading import BrokerConnection, BrokerOrder, BrokerToken, PortfolioSnapshot, TradeIntent
from ..services.broker_adapters import get_broker_adapter
from ..services.brokers_zerodha import ZerodhaBroker
from ..services.crypto_vault import decrypt_text, encrypt_text


router = APIRouter(tags=["trading"])


_bearer_optional = HTTPBearer(auto_error=False)


async def get_optional_token_payload(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_optional),
) -> Optional[TokenPayload]:
    if not creds:
        return None
    return await decode_token(creds.credentials)


def _resolve_account_id(req_account_id: Optional[str], payload: Optional[TokenPayload]) -> str:
    arise_env = (os.getenv("ARISE_ENV") or "").strip().lower()
    is_prod = arise_env in ("prod", "production")

    if is_prod:
        if payload is None:
            raise HTTPException(status_code=401, detail="Authorization required")
        return payload.sub

    if payload is not None:
        return payload.sub
    if req_account_id and req_account_id.strip():
        return req_account_id.strip()
    raise HTTPException(status_code=400, detail="account_id missing")


class ZerodhaConnectRequest(BaseModel):
    request_token: str = Field(..., description="Zerodha request_token from login redirect")
    account_id: Optional[str] = Field(None, description="Account id (ignored if Authorization token is present)")


class ExecuteTradeRequest(BaseModel):
    trade_intent_id: Optional[str] = Field(
        None,
        description="Existing trade_intent_id for confirmation step. Required when confirm=true.",
    )
    confirm: bool = Field(
        False,
        description="When false, create TradeIntent only (no broker order). When true, execute the existing TradeIntent.",
    )
    account_id: Optional[str] = Field(None, description="Account id (ignored if Authorization token is present)")
    session_id: Optional[str] = Field(None, description="Client session id")

    source: str = Field(..., description="CHART or STRATEGY")

    broker: str = Field("ZERODHA", description="Broker (ZERODHA for now)")

    symbol: str = Field(..., description="Trading symbol (e.g. RELIANCE or NIFTY24JANFUT)")
    exchange: str = Field("NSE", description="Exchange (NSE/BSE/NFO)")

    segment: str = Field(..., description="CASH or FNO")
    product: str = Field(..., description="CNC/MIS/NRML")

    side: str = Field(..., description="BUY/SELL")
    qty: int = Field(..., ge=1, description="Quantity")
    order_type: str = Field(..., description="MARKET/LIMIT/SL/SLM")

    limit_price: Optional[float] = Field(None, description="Limit price")
    trigger_price: Optional[float] = Field(None, description="Trigger price (for SL/SLM)")

    stop_loss: Optional[float] = Field(None, description="Optional risk plan stop-loss")
    target: Optional[float] = Field(None, description="Optional risk plan target")


class SyncOrderRequest(BaseModel):
    trade_intent_id: str = Field(..., description="Trade intent id")
    account_id: Optional[str] = Field(None, description="Account id (ignored if Authorization token is present)")


@router.get("/trading/brokers/zerodha/login-url")
async def zerodha_login_url() -> Dict[str, Any]:
    try:
        broker = ZerodhaBroker()
        return {"login_url": broker.get_login_url()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trading/brokers/zerodha/connect")
async def zerodha_connect(
    req: ZerodhaConnectRequest,
    db: Session = Depends(get_db),
    token_payload: Optional[TokenPayload] = Depends(get_optional_token_payload),
) -> Dict[str, Any]:
    account_id = _resolve_account_id(req.account_id, token_payload)

    try:
        broker = ZerodhaBroker()
        session = broker.generate_session(req.request_token)
        access_token = str(session.get("access_token") or "").strip()
        user_id = str(session.get("user_id") or "").strip() or None
        if not access_token:
            raise RuntimeError("No access_token returned from Zerodha")

        conn = (
            db.query(BrokerConnection)
            .filter(BrokerConnection.account_id == account_id, BrokerConnection.broker == "ZERODHA")
            .one_or_none()
        )
        if conn is None:
            conn = BrokerConnection(account_id=account_id, broker="ZERODHA", status="CONNECTED", client_user_id=user_id)
            db.add(conn)
            db.flush()
        else:
            conn.status = "CONNECTED"
            conn.client_user_id = user_id

        expires_at = datetime.utcnow() + timedelta(hours=24)
        token_row = BrokerToken(
            broker_connection_id=conn.id,
            access_token_enc=encrypt_text(access_token),
            refresh_token_enc=None,
            expires_at=expires_at,
        )
        db.add(token_row)
        db.commit()

        return {
            "status": "success",
            "broker": "ZERODHA",
            "account_id": account_id,
            "user_id": user_id,
            "expires_at": expires_at.isoformat() + "Z",
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Zerodha connect failed: {e}")


def _get_latest_zerodha_access_token(db: Session, account_id: str) -> str:
    conn = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.account_id == account_id, BrokerConnection.broker == "ZERODHA")
        .one_or_none()
    )
    if conn is None:
        raise HTTPException(status_code=401, detail="Zerodha not connected")

    token_row = (
        db.query(BrokerToken)
        .filter(BrokerToken.broker_connection_id == conn.id)
        .order_by(BrokerToken.created_at.desc())
        .first()
    )
    if token_row is None:
        raise HTTPException(status_code=401, detail="Zerodha token not found")

    return decrypt_text(token_row.access_token_enc)


def _map_zerodha_status_to_intent_state(status: Optional[str]) -> str:
    s = (status or "").strip().upper()
    if s in ("COMPLETE", "COMPLETED", "FILLED"):
        return "FILLED"
    if s in ("REJECTED",):
        return "REJECTED"
    if s in ("CANCELLED", "CANCELED"):
        return "CANCELLED"
    if s in ("OPEN", "TRIGGER PENDING", "VALIDATION PENDING", "PENDING"):
        return "ACCEPTED"
    return "SUBMITTED_TO_BROKER"


def _intent_to_ticket(intent: TradeIntent) -> Dict[str, Any]:
    return {
        "trade_intent_id": intent.id,
        "state": intent.state,
        "broker": intent.broker,
        "source": intent.source,
        "symbol": intent.symbol,
        "exchange": intent.exchange,
        "segment": intent.segment,
        "side": intent.side,
        "qty": intent.qty,
        "product": intent.product,
        "order_type": intent.order_type,
        "limit_price": intent.limit_price,
        "trigger_price": intent.trigger_price,
        "stop_loss": intent.stop_loss,
        "target": intent.target,
        "created_at": intent.created_at.isoformat() + "Z" if intent.created_at else None,
    }


@router.post("/trading/orders/sync")
async def sync_order_status(
    req: SyncOrderRequest,
    db: Session = Depends(get_db),
    token_payload: Optional[TokenPayload] = Depends(get_optional_token_payload),
) -> Dict[str, Any]:
    resolved_account_id = _resolve_account_id(req.account_id, token_payload)

    intent = db.query(TradeIntent).filter(TradeIntent.id == req.trade_intent_id).one_or_none()
    if intent is None or intent.account_id != resolved_account_id:
        raise HTTPException(status_code=404, detail="Trade intent not found")

    order = (
        db.query(BrokerOrder)
        .filter(BrokerOrder.trade_intent_id == req.trade_intent_id)
        .order_by(BrokerOrder.created_at.desc())
        .first()
    )
    if order is None or not order.broker_order_id:
        raise HTTPException(status_code=404, detail="Broker order not found")

    try:
        adapter = get_broker_adapter(order.broker or intent.broker or "")
        adapter.assert_supported()

        r = adapter.sync_order(db, resolved_account_id, intent, order.broker_order_id)

        latest_status: Optional[str] = r.get("latest_status")
        filled_qty: Optional[int] = r.get("filled_qty")
        average_price: Optional[float] = r.get("average_price")
        next_intent_state: Optional[str] = r.get("intent_state")
        raw_redacted: Optional[str] = r.get("raw_redacted")

        order.status = (latest_status or order.status)
        if filled_qty is not None:
            order.filled_qty = filled_qty
        if average_price is not None:
            order.average_price = average_price
        if raw_redacted:
            order.raw_response_redacted = raw_redacted

        if next_intent_state:
            intent.state = next_intent_state
        db.commit()

        return {
            "status": "success",
            "trade_intent_id": intent.id,
            "intent_state": intent.state,
            "order": {
                "broker": order.broker,
                "broker_order_id": order.broker_order_id,
                "status": order.status,
                "filled_qty": order.filled_qty,
                "average_price": order.average_price,
                "updated_at": order.updated_at.isoformat() + "Z" if order.updated_at else None,
            },
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Sync failed: {e}")


@router.post("/trading/execute")
async def execute_trade(
    req: ExecuteTradeRequest,
    db: Session = Depends(get_db),
    token_payload: Optional[TokenPayload] = Depends(get_optional_token_payload),
) -> Dict[str, Any]:
    account_id = _resolve_account_id(req.account_id, token_payload)

    adapter = get_broker_adapter(req.broker or "ZERODHA")
    adapter.assert_supported()

    try:
        # Step 1: create intent only (no live order) unless confirm=true.
        if not req.confirm:
            intent = TradeIntent(
                account_id=account_id,
                session_id=req.session_id,
                broker=adapter.name,
                source=req.source,
                symbol=req.symbol,
                exchange=req.exchange,
                segment=req.segment,
                product=req.product,
                side=req.side,
                qty=req.qty,
                order_type=req.order_type,
                limit_price=req.limit_price,
                trigger_price=req.trigger_price,
                stop_loss=req.stop_loss,
                target=req.target,
                state="CREATED",
            )
            db.add(intent)
            db.commit()

            return {
                "status": "pending_confirmation",
                "requires_confirmation": True,
                "trade_intent_id": intent.id,
                "broker": adapter.name,
                "preview": {
                    "symbol": intent.symbol,
                    "exchange": intent.exchange,
                    "side": intent.side,
                    "qty": intent.qty,
                    "product": intent.product,
                    "order_type": intent.order_type,
                    "limit_price": intent.limit_price,
                    "trigger_price": intent.trigger_price,
                    "ticket": _intent_to_ticket(intent),
                },
            }

        # Step 2: confirm=true => execute existing intent.
        if not req.trade_intent_id:
            raise HTTPException(status_code=400, detail="trade_intent_id is required when confirm=true")

        intent = db.query(TradeIntent).filter(TradeIntent.id == req.trade_intent_id).one_or_none()
        if intent is None or intent.account_id != account_id:
            raise HTTPException(status_code=404, detail="Trade intent not found")

        adapter = get_broker_adapter(intent.broker or "")
        adapter.assert_supported()

        existing_order = (
            db.query(BrokerOrder)
            .filter(BrokerOrder.trade_intent_id == intent.id)
            .order_by(BrokerOrder.created_at.desc())
            .first()
        )
        if existing_order is not None and existing_order.broker_order_id:
            return {
                "status": "success",
                "trade_intent_id": intent.id,
                "broker": existing_order.broker,
                "broker_order_id": existing_order.broker_order_id,
                "note": "Order already submitted for this trade_intent_id",
            }

        order_id = adapter.place_order(db, account_id, intent)

        intent.state = "SUBMITTED_TO_BROKER"
        order = BrokerOrder(
            trade_intent_id=intent.id,
            broker=adapter.name,
            broker_order_id=order_id,
            status="SUBMITTED",
            raw_response_redacted=json.dumps({"broker_order_id": order_id}),
        )
        db.add(order)
        db.commit()

        return {
            "status": "success",
            "trade_intent_id": intent.id,
            "broker": adapter.name,
            "broker_order_id": order_id,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Execute failed: {e}")


@router.get("/trading/orders")
async def get_order_status(
    trade_intent_id: str = Query(...),
    account_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    token_payload: Optional[TokenPayload] = Depends(get_optional_token_payload),
) -> Dict[str, Any]:
    resolved_account_id = _resolve_account_id(account_id, token_payload)

    intent = db.query(TradeIntent).filter(TradeIntent.id == trade_intent_id).one_or_none()
    if intent is None or intent.account_id != resolved_account_id:
        raise HTTPException(status_code=404, detail="Trade intent not found")

    order = (
        db.query(BrokerOrder)
        .filter(BrokerOrder.trade_intent_id == trade_intent_id)
        .order_by(BrokerOrder.created_at.desc())
        .first()
    )

    return {
        "trade_intent_id": trade_intent_id,
        "state": intent.state,
        "order": None
        if order is None
        else {
            "broker": order.broker,
            "broker_order_id": order.broker_order_id,
            "status": order.status,
            "filled_qty": order.filled_qty,
            "average_price": order.average_price,
            "updated_at": order.updated_at.isoformat() + "Z" if order.updated_at else None,
        },
    }


@router.post("/trading/portfolio/refresh")
async def refresh_portfolio(
    broker: str = Query("ZERODHA"),
    account_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    token_payload: Optional[TokenPayload] = Depends(get_optional_token_payload),
) -> Dict[str, Any]:
    resolved_account_id = _resolve_account_id(account_id, token_payload)

    adapter = get_broker_adapter(broker or "ZERODHA")
    adapter.assert_supported()

    try:
        positions, holdings = adapter.fetch_portfolio(db, resolved_account_id)

        for kind in ("POSITIONS", "HOLDINGS"):
            (
                db.query(PortfolioSnapshot)
                .filter(
                    PortfolioSnapshot.account_id == resolved_account_id,
                    PortfolioSnapshot.broker == adapter.name,
                    PortfolioSnapshot.kind == kind,
                    PortfolioSnapshot.is_latest == True,
                )
                .update({"is_latest": False})
            )

        now = datetime.utcnow()
        db.add(
            PortfolioSnapshot(
                account_id=resolved_account_id,
                broker=adapter.name,
                kind="POSITIONS",
                as_of=now,
                payload=json.dumps(positions),
                is_latest=True,
            )
        )
        db.add(
            PortfolioSnapshot(
                account_id=resolved_account_id,
                broker=adapter.name,
                kind="HOLDINGS",
                as_of=now,
                payload=json.dumps(holdings),
                is_latest=True,
            )
        )
        db.commit()

        return {
            "status": "success",
            "broker": adapter.name,
            "account_id": resolved_account_id,
            "as_of": now.isoformat() + "Z",
            "positions_count": len(positions.get("net", []) if isinstance(positions, dict) else []),
            "holdings_count": len(holdings) if isinstance(holdings, list) else 0,
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Refresh failed: {e}")
