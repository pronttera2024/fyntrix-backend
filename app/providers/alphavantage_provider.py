"""
Alpha Vantage Data Provider
Provides technical indicators, fundamentals, and market data
"""

import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import requests
import pandas as pd

logger = logging.getLogger(__name__)

class AlphaVantageProvider:
    """
    Alpha Vantage API provider for technical and fundamental data
    
    Capabilities:
    - Technical indicators (RSI, MACD, SMA, EMA, etc.)
    - Fundamental data (earnings, income statement, balance sheet)
    - Intraday and historical price data
    - Global market data
    - Economic indicators
    - Crypto and forex data
    """
    
    def __init__(self):
        self.api_key = os.getenv('ALPHA_VANTAGE_API_KEY')
        self.base_url = 'https://www.alphavantage.co/query'
        self.session = requests.Session()
        
        if not self.api_key:
            logger.warning("⚠️  Alpha Vantage API key not found. Technical data features will be limited.")
        else:
            logger.info(f"✓ Alpha Vantage API initialized (key: {self.api_key[:10]}...)")
    
    def is_available(self) -> bool:
        """Check if Alpha Vantage is configured"""
        return bool(self.api_key)
    
    def get_rsi(
        self, 
        symbol: str, 
        interval: str = 'daily',
        time_period: int = 14
    ) -> Optional[Dict[str, Any]]:
        """
        Get RSI (Relative Strength Index) indicator
        
        Args:
            symbol: Stock symbol
            interval: Time interval (1min, 5min, 15min, 30min, 60min, daily, weekly, monthly)
            time_period: RSI period (default 14)
        
        Returns:
            RSI data with latest value
        """
        if not self.api_key:
            return None
        
        try:
            params = {
                'function': 'RSI',
                'symbol': symbol,
                'interval': interval,
                'time_period': time_period,
                'series_type': 'close',
                'apikey': self.api_key
            }
            
            response = self.session.get(self.base_url, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            if 'Technical Analysis: RSI' in data:
                rsi_data = data['Technical Analysis: RSI']
                latest_date = list(rsi_data.keys())[0]
                latest_rsi = float(rsi_data[latest_date]['RSI'])
                
                return {
                    'symbol': symbol,
                    'indicator': 'RSI',
                    'value': latest_rsi,
                    'date': latest_date,
                    'interpretation': self._interpret_rsi(latest_rsi),
                    'signal': 'overbought' if latest_rsi > 70 else 'oversold' if latest_rsi < 30 else 'neutral'
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Alpha Vantage RSI error for {symbol}: {e}")
            return None
    
    def _interpret_rsi(self, rsi: float) -> str:
        """Interpret RSI value"""
        if rsi > 70:
            return 'Overbought - potential reversal down'
        elif rsi > 60:
            return 'Strong upward momentum'
        elif rsi < 30:
            return 'Oversold - potential reversal up'
        elif rsi < 40:
            return 'Weak momentum, possible downtrend'
        else:
            return 'Neutral momentum'
    
    def get_macd(
        self, 
        symbol: str, 
        interval: str = 'daily'
    ) -> Optional[Dict[str, Any]]:
        """
        Get MACD (Moving Average Convergence Divergence) indicator
        
        Args:
            symbol: Stock symbol
            interval: Time interval
        
        Returns:
            MACD data with signal
        """
        if not self.api_key:
            return None
        
        try:
            params = {
                'function': 'MACD',
                'symbol': symbol,
                'interval': interval,
                'series_type': 'close',
                'apikey': self.api_key
            }
            
            response = self.session.get(self.base_url, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            if 'Technical Analysis: MACD' in data:
                macd_data = data['Technical Analysis: MACD']
                latest_date = list(macd_data.keys())[0]
                latest = macd_data[latest_date]
                
                macd_value = float(latest['MACD'])
                signal_value = float(latest['MACD_Signal'])
                histogram = float(latest['MACD_Hist'])
                
                return {
                    'symbol': symbol,
                    'indicator': 'MACD',
                    'macd': macd_value,
                    'signal': signal_value,
                    'histogram': histogram,
                    'date': latest_date,
                    'crossover': 'bullish' if histogram > 0 else 'bearish',
                    'interpretation': self._interpret_macd(histogram)
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Alpha Vantage MACD error for {symbol}: {e}")
            return None
    
    def _interpret_macd(self, histogram: float) -> str:
        """Interpret MACD histogram"""
        if histogram > 0:
            return 'Bullish crossover - upward momentum'
        elif histogram < 0:
            return 'Bearish crossover - downward momentum'
        else:
            return 'No clear signal'
    
    def get_sma(
        self, 
        symbol: str, 
        interval: str = 'daily',
        time_period: int = 50
    ) -> Optional[Dict[str, Any]]:
        """
        Get SMA (Simple Moving Average)
        
        Args:
            symbol: Stock symbol
            interval: Time interval
            time_period: SMA period (default 50)
        
        Returns:
            SMA data
        """
        if not self.api_key:
            return None
        
        try:
            params = {
                'function': 'SMA',
                'symbol': symbol,
                'interval': interval,
                'time_period': time_period,
                'series_type': 'close',
                'apikey': self.api_key
            }
            
            response = self.session.get(self.base_url, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            if 'Technical Analysis: SMA' in data:
                sma_data = data['Technical Analysis: SMA']
                latest_date = list(sma_data.keys())[0]
                sma_value = float(sma_data[latest_date]['SMA'])
                
                return {
                    'symbol': symbol,
                    'indicator': f'SMA-{time_period}',
                    'value': sma_value,
                    'date': latest_date
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Alpha Vantage SMA error for {symbol}: {e}")
            return None
    
    def get_company_overview(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get company fundamental data overview
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Company overview with fundamentals
        """
        if not self.api_key:
            return None
        
        try:
            params = {
                'function': 'OVERVIEW',
                'symbol': symbol,
                'apikey': self.api_key
            }
            
            response = self.session.get(self.base_url, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            if data and 'Symbol' in data:
                return {
                    'symbol': data.get('Symbol', ''),
                    'name': data.get('Name', ''),
                    'description': data.get('Description', ''),
                    'sector': data.get('Sector', ''),
                    'industry': data.get('Industry', ''),
                    'market_cap': data.get('MarketCapitalization', '0'),
                    'pe_ratio': data.get('PERatio', 'N/A'),
                    'peg_ratio': data.get('PEGRatio', 'N/A'),
                    'book_value': data.get('BookValue', 'N/A'),
                    'dividend_yield': data.get('DividendYield', '0'),
                    'eps': data.get('EPS', 'N/A'),
                    'revenue_ttm': data.get('RevenueTTM', '0'),
                    'profit_margin': data.get('ProfitMargin', 'N/A'),
                    '52_week_high': data.get('52WeekHigh', '0'),
                    '52_week_low': data.get('52WeekLow', '0'),
                    'analyst_target': data.get('AnalystTargetPrice', 'N/A')
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Alpha Vantage company overview error for {symbol}: {e}")
            return None
    
    def get_earnings(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get earnings data
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Earnings data
        """
        if not self.api_key:
            return None
        
        try:
            params = {
                'function': 'EARNINGS',
                'symbol': symbol,
                'apikey': self.api_key
            }
            
            response = self.session.get(self.base_url, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            if 'quarterlyEarnings' in data:
                latest_quarter = data['quarterlyEarnings'][0] if data['quarterlyEarnings'] else {}
                
                return {
                    'symbol': symbol,
                    'fiscal_date': latest_quarter.get('fiscalDateEnding', ''),
                    'reported_eps': latest_quarter.get('reportedEPS', 'N/A'),
                    'estimated_eps': latest_quarter.get('estimatedEPS', 'N/A'),
                    'surprise': latest_quarter.get('surprise', 'N/A'),
                    'surprise_percent': latest_quarter.get('surprisePercentage', 'N/A')
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Alpha Vantage earnings error for {symbol}: {e}")
            return None
    
    def get_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get real-time quote
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Quote data
        """
        if not self.api_key:
            return None
        
        try:
            params = {
                'function': 'GLOBAL_QUOTE',
                'symbol': symbol,
                'apikey': self.api_key
            }
            
            response = self.session.get(self.base_url, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            if 'Global Quote' in data:
                quote = data['Global Quote']
                
                return {
                    'symbol': quote.get('01. symbol', symbol),
                    'price': float(quote.get('05. price', 0)),
                    'change': float(quote.get('09. change', 0)),
                    'percent_change': quote.get('10. change percent', '0%').replace('%', ''),
                    'volume': int(quote.get('06. volume', 0)),
                    'latest_trading_day': quote.get('07. latest trading day', ''),
                    'previous_close': float(quote.get('08. previous close', 0)),
                    'open': float(quote.get('02. open', 0)),
                    'high': float(quote.get('03. high', 0)),
                    'low': float(quote.get('04. low', 0))
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Alpha Vantage quote error for {symbol}: {e}")
            return None
    
    def search_symbol(self, keywords: str) -> List[Dict[str, Any]]:
        """
        Search for symbols
        
        Args:
            keywords: Search keywords
        
        Returns:
            List of matching symbols
        """
        if not self.api_key:
            return []
        
        try:
            params = {
                'function': 'SYMBOL_SEARCH',
                'keywords': keywords,
                'apikey': self.api_key
            }
            
            response = self.session.get(self.base_url, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            results = []
            
            if 'bestMatches' in data:
                for match in data['bestMatches'][:10]:  # Limit to 10
                    results.append({
                        'symbol': match.get('1. symbol', ''),
                        'name': match.get('2. name', ''),
                        'type': match.get('3. type', ''),
                        'region': match.get('4. region', ''),
                        'currency': match.get('8. currency', '')
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"Alpha Vantage search error for '{keywords}': {e}")
            return []
    
    def get_technical_analysis(self, symbol: str) -> Dict[str, Any]:
        """
        Get comprehensive technical analysis
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Dictionary with multiple technical indicators
        """
        analysis = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'indicators': {}
        }
        
        # Get RSI
        rsi = self.get_rsi(symbol)
        if rsi:
            analysis['indicators']['rsi'] = rsi
        
        # Get MACD
        macd = self.get_macd(symbol)
        if macd:
            analysis['indicators']['macd'] = macd
        
        # Get SMA50
        sma50 = self.get_sma(symbol, time_period=50)
        if sma50:
            analysis['indicators']['sma_50'] = sma50
        
        # Get SMA200
        sma200 = self.get_sma(symbol, time_period=200)
        if sma200:
            analysis['indicators']['sma_200'] = sma200
        
        return analysis


# Singleton instance
_alphavantage_provider = None

def get_alphavantage_provider() -> AlphaVantageProvider:
    """Get singleton Alpha Vantage provider instance"""
    global _alphavantage_provider
    if _alphavantage_provider is None:
        _alphavantage_provider = AlphaVantageProvider()
    return _alphavantage_provider
