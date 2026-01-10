from typing import Any, Dict

class TechnicalAgent:
    name = "technical"

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        sym = (payload.get("symbol") or "NIFTY").upper()
        return {
            "symbol": sym,
            "levels": ["R1 20000", "S1 19500"],
            "signal": "BUY",
            "confidence": 0.62,
        }
