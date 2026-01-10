"""
External fundamentals & research integration for Fyntrix Chat.

Provides a safe, time-bounded way to fetch a small set of
fundamental bullets about a symbol from external providers
(FMP, marketscreener, screener.in, finology, etc.).

Design goals:
- Never block the main request for too long
- Fail gracefully with clear "external data unavailable" messages
- Return a compact, LLM-friendly structure (3–5 bullets max)
"""

import asyncio
from typing import Dict, Any, List

import httpx

DEFAULT_TIMEOUT = 6.0  # seconds per upstream call
MAX_BULLETS = 5


async def _fetch_json(url: str, params: Dict[str, Any] | None = None) -> Dict[str, Any] | None:
    """Helper to fetch JSON from an external HTTP endpoint with timeouts.

    Returns None on any error; callers should handle fallbacks.
    """
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            return r.json()
    except Exception:
        return None


async def fetch_external_fundamentals(symbol: str) -> Dict[str, Any]:
    """Fetch compact external fundamentals & research bullets for a symbol.

    This is intentionally conservative: we try a small number of
    well-scoped calls and summarise to a handful of bullets.

    Structure:
        {
            "symbol": "INFY",
            "bullets": ["..."],
            "sources": ["FMP", "screener.in"],
            "note": "...",
        }
    """
    symbol = (symbol or "").upper()
    if not symbol:
        return {
            "symbol": symbol,
            "bullets": [],
            "sources": [],
            "note": "No symbol provided for external fundamentals",
        }

    bullets: List[str] = []
    sources: List[str] = []

    # FMP example (expects FMP_API_KEY in env, wired separately).
    # We only try if the backend has already configured this provider.
    # Concrete integration can be extended later without changing
    # chat logic.
    try:
        # Import lazily to avoid hard dependency if provider is missing.
        from ..providers.fmp_provider import get_fmp_provider  # type: ignore

        fmp = get_fmp_provider()
        if fmp and fmp.is_configured():  # type: ignore[attr-defined]
            info = await fmp.get_company_snapshot(symbol)  # type: ignore[attr-defined]
            if info:
                desc = info.get("business_summary") or info.get("description")
                if desc:
                    bullets.append(desc.strip())
                for key in ("pe_ratio", "pb_ratio", "roce", "roe", "de_ratio"):
                    if key in info and info[key] is not None:
                        bullets.append(f"{key.upper()}: {info[key]}")
                        if len(bullets) >= MAX_BULLETS:
                            break
                sources.append("FMP")
    except Exception:
        # Silently ignore issues; Fyntrix will mention that external data may
        # be temporarily unavailable when no bullets are present.
        pass

    # Finology: India-focused fundamentals (best-effort HTML scrape)
    try:
        from ..providers.finology_provider import get_finology_provider  # type: ignore

        fin = get_finology_provider()
        if fin and fin.is_configured():  # type: ignore[attr-defined]
            fin_info = await fin.get_company_snapshot(symbol)  # type: ignore[attr-defined]
            if fin_info:
                # We prefix some bullets to make source clear to the LLM.
                pe = fin_info.get("pe_ratio")
                if pe is not None:
                    bullets.append(f"Finology PE: {pe}")

                roe = fin_info.get("roe")
                if roe is not None:
                    bullets.append(f"Finology ROE: {roe}%")

                opm = fin_info.get("operating_margin")
                if opm is not None:
                    bullets.append(f"Operating Margin (Finology): {opm}%")

                de = fin_info.get("de_ratio")
                if de is not None:
                    bullets.append(f"Debt/Equity (Finology): {de}")

                if any(k in fin_info for k in ("pe_ratio", "roe", "operating_margin", "de_ratio")):
                    sources.append("Finology")
    except Exception:
        # Best-effort only – any error here is non-fatal.
        pass

    # TODO: add thin wrappers for marketscreener / screener.in / finology
    # when their access patterns are finalised. Keep them under the same
    # timeout and bullet limits.

    if len(bullets) > MAX_BULLETS:
        bullets = bullets[:MAX_BULLETS]

    note: str
    if not bullets:
        note = (
            "External fundamentals could not be fetched right now. "
            "Fyntrix is answering mainly from internal analytics and live data."
        )
    else:
        note = (
            "External bullets are a high-level summary from third-party "
            "research sources (may be delayed or approximate)."
        )

    return {
        "symbol": symbol,
        "bullets": bullets,
        "sources": sources,
        "note": note,
    }
