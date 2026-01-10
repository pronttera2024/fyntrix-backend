import os
from typing import Any, Dict, List, Optional

from kiteconnect import KiteConnect


class ZerodhaBroker:
    def __init__(self) -> None:
        self.api_key = os.getenv("ZERODHA_API_KEY", "").strip()
        self.api_secret = os.getenv("ZERODHA_API_SECRET", "").strip()
        if not self.api_key or not self.api_secret:
            raise RuntimeError("ZERODHA_API_KEY/ZERODHA_API_SECRET not configured")

    def get_login_url(self) -> str:
        kite = KiteConnect(api_key=self.api_key)
        return kite.login_url()

    def generate_session(self, request_token: str) -> Dict[str, Any]:
        kite = KiteConnect(api_key=self.api_key)
        return kite.generate_session(request_token=request_token, api_secret=self.api_secret)

    def _kite(self, access_token: str) -> KiteConnect:
        kite = KiteConnect(api_key=self.api_key)
        kite.set_access_token(access_token)
        return kite

    def place_order(
        self,
        access_token: str,
        *,
        tradingsymbol: str,
        exchange: str,
        transaction_type: str,
        quantity: int,
        order_type: str,
        product: str,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
    ) -> str:
        kite = self._kite(access_token)

        tt = kite.TRANSACTION_TYPE_BUY if transaction_type.upper() == "BUY" else kite.TRANSACTION_TYPE_SELL

        ot_upper = order_type.upper()
        if ot_upper == "MARKET":
            ot = kite.ORDER_TYPE_MARKET
        elif ot_upper == "LIMIT":
            ot = kite.ORDER_TYPE_LIMIT
        elif ot_upper == "SL":
            ot = kite.ORDER_TYPE_SL
        elif ot_upper == "SLM":
            ot = kite.ORDER_TYPE_SLM
        else:
            raise ValueError(f"Unsupported order_type: {order_type}")

        payload: Dict[str, Any] = {
            "variety": kite.VARIETY_REGULAR,
            "exchange": exchange,
            "tradingsymbol": tradingsymbol,
            "transaction_type": tt,
            "quantity": int(quantity),
            "product": product,
            "order_type": ot,
            "validity": kite.VALIDITY_DAY,
        }

        if ot_upper in ("LIMIT", "SL"):
            if price is None:
                raise ValueError("price is required for LIMIT/SL orders")
            payload["price"] = float(price)

        if ot_upper in ("SL", "SLM"):
            if trigger_price is None:
                raise ValueError("trigger_price is required for SL/SLM orders")
            payload["trigger_price"] = float(trigger_price)

        order_id = kite.place_order(**payload)
        return str(order_id)

    def orders(self, access_token: str) -> List[Dict[str, Any]]:
        kite = self._kite(access_token)
        return kite.orders()

    def order_history(self, access_token: str, order_id: str) -> List[Dict[str, Any]]:
        kite = self._kite(access_token)
        return kite.order_history(order_id)

    def positions(self, access_token: str) -> Dict[str, Any]:
        kite = self._kite(access_token)
        return kite.positions()

    def holdings(self, access_token: str) -> List[Dict[str, Any]]:
        kite = self._kite(access_token)
        return kite.holdings()
