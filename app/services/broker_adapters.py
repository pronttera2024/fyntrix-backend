from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..db_models.trading import BrokerConnection, BrokerToken, TradeIntent
from ..services.brokers_zerodha import ZerodhaBroker
from ..services.crypto_vault import decrypt_text


class BrokerAdapter:
    name: str

    def assert_supported(self) -> None:
        raise NotImplementedError

    def place_order(self, db: Session, account_id: str, intent: TradeIntent) -> str:
        raise NotImplementedError

    def sync_order(self, db: Session, account_id: str, intent: TradeIntent, broker_order_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    def fetch_portfolio(self, db: Session, account_id: str) -> Tuple[Any, Any]:
        raise NotImplementedError


def _get_latest_access_token(db: Session, *, account_id: str, broker: str) -> str:
    conn = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.account_id == account_id, BrokerConnection.broker == broker)
        .one_or_none()
    )
    if conn is None:
        raise HTTPException(status_code=401, detail=f"{broker} not connected")

    token_row = (
        db.query(BrokerToken)
        .filter(BrokerToken.broker_connection_id == conn.id)
        .order_by(BrokerToken.created_at.desc())
        .first()
    )
    if token_row is None:
        raise HTTPException(status_code=401, detail=f"{broker} token not found")

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


class ZerodhaAdapter(BrokerAdapter):
    name = "ZERODHA"

    def assert_supported(self) -> None:
        return

    def place_order(self, db: Session, account_id: str, intent: TradeIntent) -> str:
        access_token = _get_latest_access_token(db, account_id=account_id, broker=self.name)
        zerodha = ZerodhaBroker()
        order_id = zerodha.place_order(
            access_token,
            tradingsymbol=intent.symbol,
            exchange=intent.exchange,
            transaction_type=intent.side,
            quantity=intent.qty,
            order_type=intent.order_type,
            product=intent.product,
            price=intent.limit_price,
            trigger_price=intent.trigger_price,
        )
        return str(order_id)

    def sync_order(self, db: Session, account_id: str, intent: TradeIntent, broker_order_id: str) -> Dict[str, Any]:
        access_token = _get_latest_access_token(db, account_id=account_id, broker=self.name)
        zerodha = ZerodhaBroker()

        latest_status: Optional[str] = None
        filled_qty: Optional[int] = None
        average_price: Optional[float] = None

        history = zerodha.order_history(access_token, broker_order_id)
        if history:
            last = history[-1] if isinstance(history, list) else None
            if isinstance(last, dict):
                latest_status = last.get("status")
                try:
                    fq = last.get("filled_quantity")
                    filled_qty = int(fq) if fq is not None else None
                except Exception:
                    filled_qty = None
                try:
                    ap = last.get("average_price")
                    average_price = float(ap) if ap is not None else None
                except Exception:
                    average_price = None
        else:
            orders = zerodha.orders(access_token)
            match = None
            for o in orders or []:
                if str(o.get("order_id")) == str(broker_order_id):
                    match = o
                    break
            if isinstance(match, dict):
                latest_status = match.get("status")
                try:
                    fq = match.get("filled_quantity")
                    filled_qty = int(fq) if fq is not None else None
                except Exception:
                    filled_qty = None
                try:
                    ap = match.get("average_price")
                    average_price = float(ap) if ap is not None else None
                except Exception:
                    average_price = None

        intent_state = _map_zerodha_status_to_intent_state(latest_status)

        return {
            "latest_status": latest_status,
            "filled_qty": filled_qty,
            "average_price": average_price,
            "intent_state": intent_state,
            "raw_redacted": json.dumps(
                {
                    "broker_order_id": broker_order_id,
                    "status": latest_status,
                    "filled_qty": filled_qty,
                    "average_price": average_price,
                }
            ),
        }

    def fetch_portfolio(self, db: Session, account_id: str) -> Tuple[Any, Any]:
        access_token = _get_latest_access_token(db, account_id=account_id, broker=self.name)
        zerodha = ZerodhaBroker()
        positions = zerodha.positions(access_token)
        holdings = zerodha.holdings(access_token)
        return positions, holdings


class NotImplementedAdapter(BrokerAdapter):
    def __init__(self, name: str):
        self.name = name

    def assert_supported(self) -> None:
        raise HTTPException(status_code=501, detail=f"Broker adapter not implemented: {self.name}")

    def place_order(self, db: Session, account_id: str, intent: TradeIntent) -> str:
        self.assert_supported()
        raise RuntimeError("unreachable")

    def sync_order(self, db: Session, account_id: str, intent: TradeIntent, broker_order_id: str) -> Dict[str, Any]:
        self.assert_supported()
        raise RuntimeError("unreachable")

    def fetch_portfolio(self, db: Session, account_id: str) -> Tuple[Any, Any]:
        self.assert_supported()
        raise RuntimeError("unreachable")


def get_broker_adapter(name: str) -> BrokerAdapter:
    broker = (name or "").strip().upper()
    if not broker:
        raise HTTPException(status_code=400, detail="broker missing")

    if broker == "ZERODHA":
        return ZerodhaAdapter()
    if broker in ("ICICI_DIRECT", "HDFC_SECURITIES", "ANGEL_ONE"):
        return NotImplementedAdapter(broker)

    raise HTTPException(status_code=400, detail=f"Unknown broker: {broker}")
