"""
Finnhub Data Provider
Provides global market data, news, and financial information
"""

import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import requests

logger = logging.getLogger(__name__)

class FinnhubProvider:
    """
    Finnhub API provider for global market data
    
    Capabilities:
    - Real-time quotes for global stocks
    - Company news and press releases
    - Market news by category
    - Earnings calendar
    - IPO calendar
    - Economic calendar
    - Company fundamentals
    """
    
    def __init__(self):
        self.api_key = os.getenv('FINNHUB_API_KEY')
        self.base_url = 'https://finnhub.io/api/v1'
        self.session = requests.Session()
        
        if not self.api_key:
            logger.warning("⚠️  Finnhub API key not found. Global data features will be limited.")
        else:
            logger.info(f"✓ Finnhub API initialized (key: {self.api_key[:10]}...)")
    
    def is_available(self) -> bool:
        """Check if Finnhub is configured"""
        return bool(self.api_key)
    
    def get_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get real-time quote for a symbol
        
        Args:
            symbol: Stock symbol (e.g., 'AAPL', 'TSLA')
        
        Returns:
            Quote data with current price, change, etc.
        """
        if not self.api_key:
            return None
        
        try:
            url = f"{self.base_url}/quote"
            params = {
                'symbol': symbol,
                'token': self.api_key
            }
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data and 'c' in data:  # c = current price
                return {
                    'symbol': symbol,
                    'price': data['c'],
                    'change': data.get('d', 0),
                    'percent_change': data.get('dp', 0),
                    'high': data.get('h', 0),
                    'low': data.get('l', 0),
                    'open': data.get('o', 0),
                    'previous_close': data.get('pc', 0),
                    'timestamp': datetime.now().isoformat()
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Finnhub quote error for {symbol}: {e}")
            return None
    
    def get_company_news(
        self, 
        symbol: str, 
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get company-specific news
        
        Args:
            symbol: Stock symbol
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
        
        Returns:
            List of news articles
        """
        if not self.api_key:
            return []
        
        try:
            # Default to last 7 days
            if not to_date:
                to_date = datetime.now().strftime('%Y-%m-%d')
            if not from_date:
                from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            
            url = f"{self.base_url}/company-news"
            params = {
                'symbol': symbol,
                'from': from_date,
                'to': to_date,
                'token': self.api_key
            }
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            news = response.json()
            
            # Format news items
            formatted_news = []
            for item in news[:20]:  # Limit to 20 articles
                formatted_news.append({
                    'title': item.get('headline', ''),
                    'description': item.get('summary', ''),
                    'url': item.get('url', ''),
                    'source': item.get('source', 'Finnhub'),
                    'published_at': item.get('datetime', 0),
                    'image': item.get('image', ''),
                    'category': item.get('category', 'general')
                })
            
            logger.info(f"✓ Fetched {len(formatted_news)} news articles for {symbol}")
            return formatted_news
            
        except Exception as e:
            logger.error(f"Finnhub company news error for {symbol}: {e}")
            return []
    
    def get_market_news(
        self, 
        category: str = 'general'
    ) -> List[Dict[str, Any]]:
        """
        Get general market news
        
        Args:
            category: News category (general, forex, crypto, merger)
        
        Returns:
            List of news articles
        """
        if not self.api_key:
            return []
        
        try:
            url = f"{self.base_url}/news"
            params = {
                'category': category,
                'token': self.api_key
            }
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            news = response.json()
            
            # Format news items
            formatted_news = []
            for item in news[:30]:  # Limit to 30 articles
                formatted_news.append({
                    'title': item.get('headline', ''),
                    'description': item.get('summary', ''),
                    'url': item.get('url', ''),
                    'source': item.get('source', 'Finnhub'),
                    'published_at': item.get('datetime', 0),
                    'image': item.get('image', ''),
                    'category': category
                })
            
            logger.info(f"✓ Fetched {len(formatted_news)} {category} market news articles")
            return formatted_news
            
        except Exception as e:
            logger.error(f"Finnhub market news error: {e}")
            return []
    
    def get_company_profile(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get company profile information
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Company profile data
        """
        if not self.api_key:
            return None
        
        try:
            url = f"{self.base_url}/stock/profile2"
            params = {
                'symbol': symbol,
                'token': self.api_key
            }
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data:
                return {
                    'name': data.get('name', ''),
                    'ticker': data.get('ticker', symbol),
                    'exchange': data.get('exchange', ''),
                    'industry': data.get('finnhubIndustry', ''),
                    'market_cap': data.get('marketCapitalization', 0),
                    'country': data.get('country', ''),
                    'currency': data.get('currency', 'USD'),
                    'logo': data.get('logo', ''),
                    'phone': data.get('phone', ''),
                    'weburl': data.get('weburl', ''),
                    'ipo': data.get('ipo', '')
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Finnhub company profile error for {symbol}: {e}")
            return None
    
    def search_symbol(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for symbols by company name or ticker
        
        Args:
            query: Search query
        
        Returns:
            List of matching symbols
        """
        if not self.api_key:
            return []
        
        try:
            url = f"{self.base_url}/search"
            params = {
                'q': query,
                'token': self.api_key
            }
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            results = []
            
            if data and 'result' in data:
                for item in data['result'][:10]:  # Limit to 10 results
                    results.append({
                        'symbol': item.get('symbol', ''),
                        'description': item.get('description', ''),
                        'type': item.get('type', ''),
                        'display_symbol': item.get('displaySymbol', '')
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"Finnhub search error for '{query}': {e}")
            return []
    
    def get_earnings_calendar(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get earnings calendar
        
        Args:
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            symbol: Optional symbol filter
        
        Returns:
            List of earnings events
        """
        if not self.api_key:
            return []
        
        try:
            # Default to next 30 days
            if not from_date:
                from_date = datetime.now().strftime('%Y-%m-%d')
            if not to_date:
                to_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
            
            url = f"{self.base_url}/calendar/earnings"
            params = {
                'from': from_date,
                'to': to_date,
                'token': self.api_key
            }
            
            if symbol:
                params['symbol'] = symbol
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            earnings = []
            
            if data and 'earningsCalendar' in data:
                for item in data['earningsCalendar'][:50]:  # Limit to 50 events
                    earnings.append({
                        'date': item.get('date', ''),
                        'symbol': item.get('symbol', ''),
                        'eps_estimate': item.get('epsEstimate', 0),
                        'eps_actual': item.get('epsActual', 0),
                        'revenue_estimate': item.get('revenueEstimate', 0),
                        'revenue_actual': item.get('revenueActual', 0)
                    })
            
            logger.info(f"✓ Fetched {len(earnings)} earnings events")
            return earnings
            
        except Exception as e:
            logger.error(f"Finnhub earnings calendar error: {e}")
            return []


# Singleton instance
_finnhub_provider = None

def get_finnhub_provider() -> FinnhubProvider:
    """Get singleton Finnhub provider instance"""
    global _finnhub_provider
    if _finnhub_provider is None:
        _finnhub_provider = FinnhubProvider()
    return _finnhub_provider
