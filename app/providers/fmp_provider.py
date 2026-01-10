"""Financial Modeling Prep (FMP) Data Provider

Thin async-friendly wrapper used by Fyntrix for external fundamentals.

Design goals:
- Read API key from environment variable FMP_API_KEY
- Fail gracefully on any error (return None)
- Keep network calls minimal (1–2 endpoints per symbol)
"""

import os
import logging
import asyncio
from typing import Dict, Any, Optional

import requests

logger = logging.getLogger(__name__)


class FMPProvider:
    """Minimal FMP API client for company snapshot data.

    This is intentionally conservative and only exposes a single high-level
    method used by `external_fundamentals.fetch_external_fundamentals`.
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("FMP_API_KEY")
        self.base_url = "https://financialmodelingprep.com/api/v3"
        self.session = requests.Session()

        if not self.api_key:
            logger.warning("\u26a0\ufe0f  FMP API key not found. External fundamentals via FMP will be disabled.")
        else:
            logger.info("\u2713 FMP API initialized (key: %s...)", self.api_key[:8])

    def is_configured(self) -> bool:
        """Return True if the provider has a usable API key."""
        return bool(self.api_key)

    async def get_company_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch a compact snapshot for a symbol from FMP.

        Returns a dict with keys like:
            {
                "symbol": "RELIANCE",
                "business_summary": str | None,
                "pe_ratio": float | None,
                "pb_ratio": float | None,
                "roe": float | None,
                "roce": float | None,
                "de_ratio": float | None,
            }

        On any error, returns None (caller will handle fallbacks).
        """
        symbol = (symbol or "").upper()
        if not symbol or not self.api_key:
            return None

        def _fetch_sync() -> Optional[Dict[str, Any]]:
            try:
                snapshot: Dict[str, Any] = {"symbol": symbol}

                # 1) Company profile (business description + basic ratios)
                profile_url = f"{self.base_url}/profile/{symbol}"
                profile_resp = self.session.get(profile_url, params={"apikey": self.api_key}, timeout=10)
                profile_resp.raise_for_status()
                profile_data = profile_resp.json()
                if isinstance(profile_data, list) and profile_data:
                    profile = profile_data[0]
                    desc = profile.get("description") or profile.get("companyName")
                    if desc:
                        snapshot["business_summary"] = str(desc)

                    # FMP profile often exposes trailing PE as `pe`
                    pe = profile.get("pe")
                    if pe is not None:
                        snapshot["pe_ratio"] = pe

                # 2) Key ratios (TTM) for more fundamentals
                ratios_url = f"{self.base_url}/ratios-ttm/{symbol}"
                ratios_resp = self.session.get(ratios_url, params={"apikey": self.api_key}, timeout=10)
                if ratios_resp.ok:
                    ratios_data = ratios_resp.json()
                    if isinstance(ratios_data, list) and ratios_data:
                        ratios = ratios_data[0]
                        # Map a few common fields into a stable, generic shape
                        pb = ratios.get("priceToBookRatioTTM")
                        if pb is not None:
                            snapshot["pb_ratio"] = pb

                        roe = ratios.get("returnOnEquityTTM")
                        if roe is not None:
                            snapshot["roe"] = roe

                        roce = ratios.get("returnOnCapitalEmployedTTM") or ratios.get("returnOnAssetsTTM")
                        if roce is not None:
                            snapshot["roce"] = roce

                        de = ratios.get("debtEquityRatioTTM") or ratios.get("debtToEquityTTM")
                        if de is not None:
                            snapshot["de_ratio"] = de

                return snapshot
            except Exception as e:  # pragma: no cover - defensive
                logger.error("FMP snapshot error for %s: %s", symbol, str(e)[:200])
                return None

        return await asyncio.to_thread(_fetch_sync)


_fmp_provider: Optional[FMPProvider] = None


def get_fmp_provider() -> FMPProvider:
    """Global accessor used by services.

    Lazily instantiates the provider so that missing API keys or
    import errors do not break app startup.
    """
    global _fmp_provider
    if _fmp_provider is None:
        _fmp_provider = FMPProvider()
    return _fmp_provider
