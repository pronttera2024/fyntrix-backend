"""
Multi-source news aggregator with NSE priority.
Integrates: FMP, Fiscal AI, Yahoo Finance, and NSE official announcements.
"""
from __future__ import annotations
import os
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import httpx
from bs4 import BeautifulSoup
# Note: Using 'html.parser' instead of 'lxml' to avoid C++ build dependency on Windows
from .cache import get_cached

# API Keys
FMP_API_KEY = (os.environ.get("FMP_API_KEY", "") or "").strip() or None
FISCAL_AI_API_KEY = (os.environ.get("FISCAL_AI_API_KEY", "") or "").strip() or None

# Priority order for sources (higher = more important)
SOURCE_PRIORITY = {
    "NSE": 100,
    "BSE": 90,
    "MoneyControl": 95,
    "FMP": 80,
    "Fiscal AI": 70,
    "Yahoo Finance": 60,
    "Nikkei Asia": 55,
    "Bloomberg": 50,
    "WSJ Business": 45,
    "NDTV Profit": 40,
    "MarketWatch": 30,
}


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        pass
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%y %H:%M:%S", "%d-%b-%y %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


# Keywords to help distinguish market-moving headlines from generic content
_MARKET_POSITIVE_KEYWORDS = [
    "market",
    "markets",
    "stock",
    "stocks",
    "equity",
    "equities",
    "nifty",
    "sensex",
    "index",
    "indices",
    "ipo",
    "listing",
    "earnings",
    "results",
    "quarter",
    "dividend",
    "bonus",
    "split",
    "buyback",
    "merger",
    "acquisition",
    "deal",
    "rbi",
    "sebi",
    "fed",
    "federal reserve",
    "central bank",
    "rate",
    "rates",
    "policy",
    "budget",
    "gdp",
    "inflation",
    "economy",
    "economic",
    "bond",
    "yields",
    "currency",
    "rupee",
]

_MARKET_NEGATIVE_KEYWORDS = [
    "sports",
    "cricket",
    "football",
    "tennis",
    "movie",
    "film",
    "bollywood",
    "hollywood",
    "music",
    "celebrity",
    "lifestyle",
    "fashion",
    "travel",
    "recipes",
    "food",
]


def _is_market_moving_text(title: str, description: str = "") -> bool:
    """Heuristic filter to keep primarily market-impacting headlines.

    This is deliberately conservative: we avoid obvious non-market topics and
    prefer items mentioning markets/economy/policy/major events. If the
    heuristic drops too many items, the caller should fall back to the
    unfiltered list.
    """

    text = f"{title or ''} {description or ''}".lower()
    if not text.strip():
        return False

    # Filter out obviously irrelevant topics first
    for bad in _MARKET_NEGATIVE_KEYWORDS:
        if bad in text:
            return False

    # Keep headlines that clearly talk about markets/economy/policy/etc.
    for good in _MARKET_POSITIVE_KEYWORDS:
        if good in text:
            return True

    return False

async def fetch_nse_announcements() -> List[Dict[str, Any]]:
    """
    Fetch latest announcements from NSE.
    Includes corporate actions, earnings, dividends, etc.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://www.nseindia.com/",
            "Accept": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=15, headers=headers) as cx:
            # Warm up cookies
            await cx.get("https://www.nseindia.com/")
            
            # Fetch corporate announcements
            url = "https://www.nseindia.com/api/corporate-announcements?index=equities"
            r = await cx.get(url)
            r.raise_for_status()
            data = r.json()
            
            news_items = []
            for item in data[:15]:  # Top 15
                # Try to get a meaningful title
                subject = item.get("subject", "")
                desc = item.get("desc", "")
                symbol = item.get("symbol", "")
                
                # If subject is empty or generic, use description
                if not subject or subject.strip() == "":
                    if desc and desc.strip():
                        title = f"{symbol}: {desc}" if symbol else desc
                    else:
                        title = f"{symbol} - Corporate Announcement" if symbol else "Corporate Announcement"
                else:
                    title = f"{symbol}: {subject}" if symbol else subject
                
                # Limit title length
                if len(title) > 100:
                    title = title[:97] + "..."
                
                ts = _parse_timestamp(item.get("an_dt")) or datetime.utcnow()
                news_items.append({
                    "title": title,
                    "description": desc[:200] if desc else "",
                    "source": "NSE",
                    "url": f"https://www.nseindia.com/companies-listing/corporate-filings-announcements",
                    "timestamp": ts.isoformat() + "Z",
                    "symbol": symbol,
                    "category": "corporate"
                })
            
            return news_items[:10]  # Return top 10
    except Exception as e:
        print(f"NSE fetch error: {e}")
        return []

async def fetch_fmp_news(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch general market news from FMP.
    """
    if not FMP_API_KEY:
        return []

    try:
        # Use general news endpoint
        url = f"https://financialmodelingprep.com/api/v3/fmp/articles?page=0&size={limit}&apikey={FMP_API_KEY}"
        
        async with httpx.AsyncClient(timeout=10) as cx:
            r = await cx.get(url)
            r.raise_for_status()
            data = r.json()
            
            news_items = []
            content = data.get("content", []) if isinstance(data, dict) else data
            
            for article in content[:limit]:
                news_items.append({
                    "title": article.get("title", "Untitled"),
                    "description": article.get("content", "")[:200],
                    "source": "FMP",
                    "url": article.get("link", "") or article.get("url", ""),
                    "timestamp": article.get("date", article.get("publishedDate", "")),
                    "symbol": "",
                    "category": "general"
                })
            
            return news_items
            
    except Exception as e:
        print(f"FMP news fetch error: {e}")
        return []

async def fetch_fiscal_ai_news(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch news from Fiscal AI API.
    """
    try:
        if not FISCAL_AI_API_KEY:
            return []

        base_url = os.environ.get("FISCAL_AI_BASE_URL", "").rstrip("/")
        endpoint = os.environ.get("FISCAL_AI_NEWS_ENDPOINT", "/v1/news")
        if not base_url:
            return []

        url = f"{base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {FISCAL_AI_API_KEY}",
            "Accept": "application/json",
        }

        params = {"limit": limit}

        async with httpx.AsyncClient(timeout=15, headers=headers) as cx:
            r = await cx.get(url, params=params)
            r.raise_for_status()
            data = r.json()

        if isinstance(data, dict):
            items = data.get("items") or data.get("results") or data.get("data") or []
        elif isinstance(data, list):
            items = data
        else:
            items = []

        news_items: List[Dict[str, Any]] = []
        for item in items[:limit]:
            raw_title = item.get("title") or item.get("headline") or ""
            title = str(raw_title or "").strip()
            summary = str(
                (item.get("summary") or item.get("description") or item.get("body") or "")
            ).strip()
            link = str(item.get("url") or item.get("link") or "")
            ts_raw = item.get("published_at") or item.get("timestamp") or item.get("date")
            ts = _parse_timestamp(ts_raw) or datetime.utcnow()

            if not title and summary:
                title = summary[:80] + ("..." if len(summary) > 80 else "")
            if not title:
                continue

            news_items.append(
                {
                    "title": title,
                    "description": summary[:200],
                    "source": "Fiscal AI",
                    "url": link,
                    "timestamp": ts.isoformat() + "Z",
                    "symbol": "",
                    "category": "general",
                }
            )

        return news_items
    except Exception as e:
        print(f"Fiscal AI fetch error: {e}")
        return []

async def scrape_moneycontrol() -> List[Dict[str, Any]]:
    """
    Scrape latest news from MoneyControl.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        async with httpx.AsyncClient(timeout=10, headers=headers) as cx:
            r = await cx.get("https://www.moneycontrol.com/news/business/markets/")
            r.raise_for_status()
            soup = BeautifulSoup(r.text, 'html.parser')  # Using built-in parser
            
            news_items = []
            # Find news articles
            articles = soup.find_all('li', class_='clearfix', limit=10)
            
            for article in articles:
                link_tag = article.find('a')
                if link_tag:
                    title = link_tag.get('title', link_tag.get_text(strip=True))
                    href = link_tag.get('href', '')
                    
                    if title and len(title) > 20:  # Filter short titles
                        news_items.append({
                            "title": title,
                            "description": "",
                            "source": "MoneyControl",
                            "url": href,
                            "timestamp": datetime.now().isoformat(),
                            "symbol": "",
                            "category": "general"
                        })
            
            if len(news_items) < 5:
                headings = soup.find_all(['h2', 'h3'], limit=40)
                for heading in headings:
                    link = heading.find('a')
                    if not link:
                        continue
                    title = link.get('title') or link.get_text(strip=True)
                    href = link.get('href') or ''
                    if not title or len(title) <= 20:
                        continue
                    if href and not href.startswith('http'):
                        href = f"https://www.moneycontrol.com{href}"
                    news_items.append({
                        "title": title,
                        "description": "",
                        "source": "MoneyControl",
                        "url": href,
                        "timestamp": datetime.now().isoformat(),
                        "symbol": "",
                        "category": "general"
                    })
                    if len(news_items) >= 10:
                        break
            
            return news_items[:8]
    except Exception as e:
        print(f"MoneyControl scrape error: {e}")
        return []

async def scrape_yahoo_finance() -> List[Dict[str, Any]]:
    """
    Scrape latest headlines from Yahoo Finance.
    """
    try:
        # Use Yahoo Finance stock market news section which focuses on
        # market-moving headlines rather than generic navigation links.
        url = "https://finance.yahoo.com/topic/stock-market-news/"
        
        async with httpx.AsyncClient(
            timeout=15,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            },
        ) as cx:
            r = await cx.get(url)
            r.raise_for_status()
            
            soup = BeautifulSoup(r.text, 'html.parser')  # Using built-in parser
            news_items: List[Dict[str, Any]] = []

            # Find news headlines. Yahoo frequently uses <h3> for article
            # titles in this section.
            headlines = soup.find_all('h3', limit=30)

            for headline in headlines:
                link = headline.find('a')
                if not link:
                    continue

                title = link.get_text(strip=True)
                href = link.get('href', '') or ''

                # Normalise relative URLs so they work correctly from our app.
                if href and href.startswith('/'):
                    href = f"https://finance.yahoo.com{href}"

                # Drop very short or clearly non-informative labels such as
                # section names (e.g. "Sports", "Finance").
                if not title or len(title) < 20:
                    continue

                if not _is_market_moving_text(title):
                    continue

                news_items.append({
                    "title": title,
                    "description": "",
                    "source": "Yahoo Finance",
                    "url": href,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "category": "general",
                })

            return news_items
    except Exception as e:
        print(f"Yahoo scrape error: {e}")
        return []

async def scrape_nikkei_markets() -> List[Dict[str, Any]]:
    """Scrape latest markets headlines from Nikkei Asia."""
    try:
        url = "https://asia.nikkei.com/business/markets"
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as cx:
            r = await cx.get(url)
            r.raise_for_status()

            soup = BeautifulSoup(r.text, 'html.parser')
            news_items: List[Dict[str, Any]] = []

            links = soup.find_all('a', limit=30)
            for link in links:
                title = link.get_text(strip=True)
                href = link.get('href', '')
                if not title or len(title) < 20:
                    continue
                if not href:
                    continue
                if not href.startswith('http'):
                    href = f"https://asia.nikkei.com{href}"

                news_items.append({
                    "title": title,
                    "description": "",
                    "source": "Nikkei Asia",
                    "url": href,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "symbol": "",
                    "category": "general",
                })

            return news_items[:10]
    except Exception as e:
        print(f"Nikkei scrape error: {e}")
        return []


async def scrape_wsj_business() -> List[Dict[str, Any]]:
    """Scrape latest business headlines from WSJ Business section."""
    try:
        url = "https://www.wsj.com/business"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True) as cx:
            r = await cx.get(url)
            r.raise_for_status()

            soup = BeautifulSoup(r.text, 'html.parser')
            news_items: List[Dict[str, Any]] = []

            headings = soup.find_all(['h2', 'h3'], limit=30)
            for heading in headings:
                link = heading.find('a') or heading.parent if heading and heading.parent and heading.parent.name == 'a' else None
                if not link:
                    link = heading.find('a')
                if not link:
                    continue

                title = link.get_text(strip=True)
                href = link.get('href', '')
                if not title or len(title) < 30:
                    continue
                if not href:
                    continue
                if href.startswith('/'):
                    href = f"https://www.wsj.com{href}"

                news_items.append({
                    "title": title,
                    "description": "",
                    "source": "WSJ Business",
                    "url": href,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "symbol": "",
                    "category": "general",
                })

            return news_items[:10]
    except Exception as e:
        print(f"WSJ scrape error: {e}")
        return []

async def scrape_ndtv_profit() -> List[Dict[str, Any]]:
    """
    Scrape latest news from NDTV Profit.
    """
    try:
        url = "https://www.ndtvprofit.com/"
        
        async with httpx.AsyncClient(timeout=15) as cx:
            r = await cx.get(url)
            r.raise_for_status()
            
            soup = BeautifulSoup(r.text, 'html.parser')  # Using built-in parser
            news_items = []
            
            # Find news articles (adjust selectors based on actual site structure)
            articles = soup.find_all('article', limit=10)
            
            for article in articles:
                title_elem = article.find('h2') or article.find('h3')
                link_elem = article.find('a')
                
                if title_elem and link_elem:
                    href = link_elem.get('href', '')
                    if href and not href.startswith('http'):
                        href = f"https://www.ndtvprofit.com{href}"
                    
                    news_items.append({
                        "title": title_elem.get_text(strip=True),
                        "description": "",
                        "source": "NDTV Profit",
                        "url": href,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "category": "general"
                    })
            
            return news_items
    except Exception as e:
        print(f"NDTV Profit scrape error: {e}")
        return []

async def scrape_bloomberg() -> List[Dict[str, Any]]:
    """
    Scrape headlines from Bloomberg Markets.
    Note: Bloomberg has anti-scraping measures. Consider using their API if available.
    """
    try:
        url = "https://www.bloomberg.com/markets"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        async with httpx.AsyncClient(timeout=15, headers=headers) as cx:
            r = await cx.get(url)
            r.raise_for_status()
            
            soup = BeautifulSoup(r.text, 'html.parser')  # Using built-in parser
            news_items = []
            
            # Find headlines (adjust selectors as needed)
            headlines = soup.find_all('a', limit=10)
            
            for link in headlines:
                title = link.get_text(strip=True)
                if title and len(title) > 20:  # Filter out short/navigation text
                    href = link.get('href', '')
                    if href and not href.startswith('http'):
                        href = f"https://www.bloomberg.com{href}"
                    
                    news_items.append({
                        "title": title,
                        "description": "",
                        "source": "Bloomberg",
                        "url": href,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "category": "general"
                    })
            
            return news_items[:10]
    except Exception as e:
        print(f"Bloomberg scrape error: {e}")
        return []

async def aggregate_news(category: str = "general", limit: int = 20) -> List[Dict[str, Any]]:
    """
    Aggregate news from all sources with NSE priority.
    
    Args:
        category: News category filter (general, corporate, earnings)
        limit: Maximum number of news items to return
        
    Returns:
        List of news items sorted by source priority and timestamp
    """
    async def _fetch():
        all_news = []
        
        # Fetch from all sources with error handling - don't let one failure break all
        # Priority: NSE first (always)
        if category == "corporate":
            try:
                nse_news = await fetch_nse_announcements()
                all_news.extend(nse_news)
            except Exception as e:
                print(f"NSE fetch failed: {e}")
        
        # Then other sources. We always attempt them so that diverse sources are
        # available to the frontend selector, and rely on the final `limit` slice
        # to cap the total number of items returned.
        try:
            fmp_news = await fetch_fmp_news(limit=10)
            all_news.extend(fmp_news)
        except Exception as e:
            print(f"FMP fetch failed: {e}")

        try:
            fiscal_news = await fetch_fiscal_ai_news(limit=10)
            all_news.extend(fiscal_news)
        except Exception as e:
            print(f"Fiscal AI fetch failed: {e}")
        
        try:
            mc_news = await scrape_moneycontrol()
            all_news.extend(mc_news)
        except Exception as e:
            print(f"MoneyControl fetch failed: {e}")
        
        # Additional scraped sources for global markets context
        try:
            yahoo_news = await scrape_yahoo_finance()
            all_news.extend(yahoo_news)
        except Exception as e:
            print(f"Yahoo fetch failed: {e}")

        try:
            nikkei_news = await scrape_nikkei_markets()
            all_news.extend(nikkei_news)
        except Exception as e:
            print(f"Nikkei fetch failed: {e}")

        try:
            wsj_news = await scrape_wsj_business()
            all_news.extend(wsj_news)
        except Exception as e:
            print(f"WSJ fetch failed: {e}")

        try:
            ndtv_news = await scrape_ndtv_profit()
            all_news.extend(ndtv_news)
        except Exception as e:
            print(f"NDTV fetch failed: {e}")

        try:
            bloomberg_news = await scrape_bloomberg()
            all_news.extend(bloomberg_news)
        except Exception as e:
            print(f"Bloomberg fetch failed: {e}")
        
        # Add fallback news if we have very few non-exchange items overall
        non_exchange_news = [
            n for n in all_news
            if str(n.get("source", "")).upper() not in ("NSE", "BSE")
        ]
        if len(non_exchange_news) < 5:
            today = datetime.now().isoformat()
            fallback_items = [
                {
                    "title": "Indian markets track global trends as investors await key economic data",
                    "description": "Domestic indices follow international market movements amid mixed global cues",
                    "source": "Market Update",
                    "url": "https://www.nseindia.com",
                    "timestamp": today,
                    "symbol": "",
                    "category": "general"
                },
                {
                    "title": "FII and DII activity shows divergent trends in Indian equities",
                    "description": "Foreign investors and domestic institutions show contrasting positions",
                    "source": "Market Update",
                    "url": "https://www.nseindia.com",
                    "timestamp": today,
                    "symbol": "",
                    "category": "general"
                },
                {
                    "title": "Banking sector outlook remains positive amid stable interest rate environment",
                    "description": "Bank stocks show resilience as rate cycle remains supportive",
                    "source": "Market Update",
                    "url": "https://www.nseindia.com",
                    "timestamp": today,
                    "symbol": "",
                    "category": "general"
                },
                {
                    "title": "IT sector monitors global demand signals and currency movements",
                    "description": "Technology stocks track rupee-dollar dynamics and offshore deal flows",
                    "source": "Market Update",
                    "url": "https://www.nseindia.com",
                    "timestamp": today,
                    "symbol": "",
                    "category": "general"
                },
                {
                    "title": "Commodity prices influence metal and energy sector performance",
                    "description": "Raw material costs impact margins across industrial segments",
                    "source": "Market Update",
                    "url": "https://www.nseindia.com",
                    "timestamp": today,
                    "symbol": "",
                    "category": "general"
                }
            ]
            # Only add needed items to reach at least 5 non-exchange entries
            items_needed = 5 - len(non_exchange_news)
            if items_needed > 0:
                all_news.extend(fallback_items[:items_needed])
        
        # Sort by priority (NSE first) then by timestamp
        def sort_key(item):
            source_priority = SOURCE_PRIORITY.get(item["source"], 0)
            try:
                ts = _parse_timestamp(item.get("timestamp"))
                timestamp_score = ts.timestamp() if ts is not None else 0
            except Exception:
                timestamp_score = 0

            # Return tuple: (priority, -timestamp) so higher priority & newer = first
            return (-source_priority, -timestamp_score)

        all_news.sort(key=sort_key)

        # Deduplicate by title (case-insensitive)
        seen_titles = set()
        unique_news: List[Dict[str, Any]] = []
        for item in all_news:
            title_lower = str(item.get("title") or "").lower().strip()
            if title_lower not in seen_titles:
                seen_titles.add(title_lower)
                unique_news.append(item)

        # Apply a market-impact filter where possible. If the heuristic would
        # leave us with too few items, fall back to the unfiltered list so the
        # UI is never empty.
        market_filtered: List[Dict[str, Any]] = []
        for item in unique_news:
            title = str(item.get("title") or "")
            desc = str(item.get("description") or "")
            if _is_market_moving_text(title, desc):
                market_filtered.append(item)

        if len(market_filtered) >= 5:
            candidate_news = market_filtered
        else:
            candidate_news = unique_news

        # Lightweight per-source debug logging to understand which scrapers
        # are actually contributing items in this environment.
        source_debug: Dict[str, int] = {}
        for item in candidate_news:
            src = str(item.get("source") or "")
            source_debug[src] = source_debug.get(src, 0) + 1

        print(
            f"[NewsAggregator] aggregate_news category={category} limit={limit} "
            f"unique_total={len(candidate_news)} by_source={source_debug}"
        )

        # Enforce per-source caps so that no single outlet (e.g. MoneyControl)
        # dominates the feed and global sources (FMP, Nikkei Asia, WSJ,
        # Bloomberg, Yahoo Finance, etc.) reliably appear.
        source_counts: Dict[str, int] = {}
        diversified_news: List[Dict[str, Any]] = []

        # Sensible caps for the general feed. NSE/BSE can still surface more
        # items when present (mainly for corporate category), but for the
        # general news stream each non-exchange outlet is limited so that the
        # final list contains a healthy mix of India and global sources.
        PER_SOURCE_CAPS = {
            "NSE": 10,
            "BSE": 10,
            "MoneyControl": 5,
            "FMP": 4,
            "Fiscal AI": 3,
            "Yahoo Finance": 3,
            "Nikkei Asia": 3,
            "Bloomberg": 3,
            "WSJ Business": 3,
            "NDTV Profit": 3,
            "MarketWatch": 3,
        }
        DEFAULT_CAP = 3

        for item in candidate_news:
            source = str(item.get("source") or "")
            max_for_source = PER_SOURCE_CAPS.get(source, DEFAULT_CAP)

            count = source_counts.get(source, 0)
            if count >= max_for_source:
                continue

            diversified_news.append(item)
            source_counts[source] = count + 1

            if len(diversified_news) >= limit:
                break

        return diversified_news
    
    persist_flag = category != "general"

    return await get_cached(
        f"aggregated_news_v2:{category}:{limit}",
        _fetch,
        ttl=300.0,  # 5 minutes cache
        persist=persist_flag,
        region="India"
    )

async def get_symbol_news(symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get news for a specific symbol.
    """
    async def _fetch():
        news_items = []
        
        # FMP symbol news
        if FMP_API_KEY:
            try:
                url = f"https://financialmodelingprep.com/api/v3/stock_news?tickers={symbol}&limit={limit}&apikey={FMP_API_KEY}"
                async with httpx.AsyncClient(timeout=15) as cx:
                    r = await cx.get(url)
                    r.raise_for_status()
                    data = r.json()
                    
                    for item in data:
                        news_items.append({
                            "title": item.get("title", ""),
                            "description": item.get("text", ""),
                            "source": "FMP",
                            "url": item.get("url", ""),
                            "timestamp": item.get("publishedDate", datetime.utcnow().isoformat() + "Z"),
                            "symbol": symbol,
                            "category": "stock"
                        })
            except Exception as e:
                print(f"FMP symbol news error: {e}")
        
        # Check NSE for symbol-specific announcements
        nse_all = await fetch_nse_announcements()
        symbol_nse = [n for n in nse_all if n.get("symbol", "").upper() == symbol.upper()]
        news_items.extend(symbol_nse)
        
        # Sort by priority
        def sort_key(item):
            return -SOURCE_PRIORITY.get(item["source"], 0)
        
        news_items.sort(key=sort_key)
        return news_items[:limit]
    
    return await get_cached(
        f"symbol_news:{symbol}:{limit}",
        _fetch,
        ttl=300.0,
        persist=False,
        region="India"
    )
