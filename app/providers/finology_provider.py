"""Finology (ticker.finology.in) data provider for Fyntrix.

This is a *best-effort* HTML scraper intended only to pull a few key
fundamental ratios (PE, ROE, margins, debt/equity) for Indian stocks.

Design goals:
- Never block for long (short timeouts, single request per symbol)
- Fail gracefully on any error and simply return None
- Keep parsing conservative – if structure changes, we just skip

NOTE: Finology does not expose an official public API. This helper makes
one GET request to the company page and uses regex to extract a few
numbers. If you have an authenticated session, you can optionally pass
its cookies via the FINOLOGY_COOKIE env var.
"""

import os
import re
import logging
import asyncio
from typing import Dict, Any, Optional

import requests

logger = logging.getLogger(__name__)


class FinologyProvider:
    """Minimal Finology HTML client.

    We intentionally keep this very small and defensive. If Finology
    layout changes or access is blocked (e.g. by login requirements),
    this provider will simply return None and the caller will fall back
    to other data sources.
    """

    def __init__(self) -> None:
        self.base_url = "https://ticker.finology.in"
        self.session = requests.Session()
        # Simple UA to avoid being treated as a bot immediately
        self.session.headers.update(
            {
                "User-Agent": "FyntrixBot/0.1 (+for personal research; contact user)",
            }
        )

        cookie = os.getenv("FINOLOGY_COOKIE")
        if cookie:
            # Raw cookie header, if user chooses to supply it
            self.session.headers["Cookie"] = cookie
            logger.info("✓ Finology cookie configured from FINOLOGY_COOKIE env var")

    def is_configured(self) -> bool:
        """Return True if provider is allowed to run.

        For now we always return True – there is no API key, only
        optional cookies. You can later gate this behind another env var
        if desired.
        """

        return True

    async def get_company_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch a small set of ratios for a symbol from Finology.

        Returns a dict like:
            {
                "symbol": "RELIANCE",
                "pe_ratio": float | None,
                "roe": float | None,
                "operating_margin": float | None,
                "de_ratio": float | None,
            }

        On any error, returns None.
        """
        symbol = (symbol or "").upper()
        if not symbol:
            return None

        def _fetch_sync() -> Optional[Dict[str, Any]]:
            try:
                url = f"{self.base_url}/company/{symbol}"
                resp = self.session.get(url, timeout=10)
                resp.raise_for_status()
                html = resp.text

                snapshot: Dict[str, Any] = {"symbol": symbol}

                def _find_number(patterns: list[str]) -> Optional[float]:
                    for pat in patterns:
                        m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
                        if m:
                            try:
                                raw = m.group(1).replace(",", "").strip()
                                return float(raw)
                            except Exception:
                                continue
                    return None

                # These regexes are intentionally loose – they may match
                # if the label and number are reasonably close.
                pe = _find_number([
                    r"P\s*\/\s*E[^0-9]*([0-9]+(?:\.[0-9]+)?)",
                    r"PE\s*Ratio[^0-9]*([0-9]+(?:\.[0-9]+)?)",
                ])
                if pe is not None:
                    snapshot["pe_ratio"] = pe

                roe = _find_number([
                    r"ROE[^0-9]*([0-9]+(?:\.[0-9]+)?)%",
                    r"Return\s+on\s+Equity[^0-9]*([0-9]+(?:\.[0-9]+)?)%",
                ])
                if roe is not None:
                    snapshot["roe"] = roe

                opm = _find_number([
                    r"Operating\s+Margin[^0-9]*([0-9]+(?:\.[0-9]+)?)%",
                    r"OPM[^0-9]*([0-9]+(?:\.[0-9]+)?)%",
                ])
                if opm is not None:
                    snapshot["operating_margin"] = opm

                de = _find_number([
                    r"Debt\s*[:\-]?\s*Equity[^0-9]*([0-9]+(?:\.[0-9]+)?)",
                    r"Debt\s*\/\s*Equity[^0-9]*([0-9]+(?:\.[0-9]+)?)",
                ])
                if de is not None:
                    snapshot["de_ratio"] = de

                # If we didn't extract anything, treat as failure
                if len(snapshot) == 1:
                    return None

                return snapshot
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("Finology snapshot error for %s: %s", symbol, str(e)[:200])
                return None

        return await asyncio.to_thread(_fetch_sync)


_finology_provider: Optional[FinologyProvider] = None


def get_finology_provider() -> FinologyProvider:
    """Global accessor used by services.

    Lazily instantiate provider so errors do not break app startup.
    """
    global _finology_provider
    if _finology_provider is None:
        _finology_provider = FinologyProvider()
    return _finology_provider
