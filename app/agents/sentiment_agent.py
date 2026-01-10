"""
Sentiment Agent - News and Social Media Sentiment Analysis
Analyzes news sentiment, analyst ratings, and social media buzz
"""

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from .base import BaseAgent, AgentResult
from ..services.news_aggregator import aggregate_news, get_symbol_news
from ..llm import llm_manager


class SentimentAgent(BaseAgent):
    """
    Analyzes market sentiment from news and social sources.
    
    Data Sources:
    1. News Headlines - NSE, MoneyControl, ET
    2. Analyst Ratings - Upgrades/downgrades
    3. Social Media - Twitter/Reddit sentiment (future)
    4. Earnings Calls - Management commentary (future)
    """
    
    def __init__(self, weight: float = 0.15):
        super().__init__(name="sentiment", weight=weight)
    
    async def analyze(
        self, 
        symbol: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Analyze sentiment from multiple sources.
        
        Args:
            symbol: Stock symbol
            context: Additional context
            
        Returns:
            AgentResult with sentiment signals
        """
        symbol_upper = (symbol or "").upper()

        # Fetch recent general news plus symbol-specific feeds so that
        # large-cap events (earnings, regulatory actions, disruptions)
        # reliably show up even when headlines use company names instead
        # of NSE tickers.
        all_news = await aggregate_news(category="general", limit=50)
        try:
            symbol_specific = await get_symbol_news(symbol_upper, limit=10)
        except Exception as e:
            print(f"  ⚠️  SentimentAgent: get_symbol_news failed for {symbol_upper}: {e}")
            symbol_specific = []

        # Simple alias map for common NIFTY/NIFTY-like names where media
        # headlines often use full company name instead of ticker.
        alias_map = {
            "INDIGO": ["interglobe aviation", "interglobe", "indigo"],
            "RELIANCE": ["reliance industries"],
            "HDFCBANK": ["hdfc bank"],
            "SBIN": ["state bank of india"],
        }
        aliases = [a.lower() for a in alias_map.get(symbol_upper, [])]

        def _matches_symbol(news: Dict[str, Any]) -> bool:
            title = str(news.get("title", "")).lower()
            desc = str(news.get("description", "")).lower()
            sym_field = str(news.get("symbol", "")).upper()

            if sym_field and sym_field == symbol_upper:
                return True
            if symbol_upper and symbol_upper.lower() in title:
                return True
            if symbol_upper and symbol_upper.lower() in desc:
                return True
            for alias in aliases:
                if alias and (alias in title or alias in desc):
                    return True
            return False

        merged_news = list(all_news) + list(symbol_specific)
        seen_ids = set()
        deduped: List[Dict[str, Any]] = []
        for n in merged_news:
            key = (str(n.get("source", "")).lower(), str(n.get("title", "")).strip().lower())
            if key in seen_ids:
                continue
            seen_ids.add(key)
            deduped.append(n)

        symbol_news = [n for n in deduped if _matches_symbol(n)]
        
        if not symbol_news:
            # No specific news - use general market sentiment
            return await self._analyze_general_sentiment(symbol, all_news)
        
        # Analyze news sentiment
        news_sentiment = await self._analyze_news_sentiment(symbol_news)
        
        # Analyze headline patterns
        headline_analysis = self._analyze_headline_patterns(symbol_news)
        
        # Count positive/negative/neutral
        sentiment_counts = self._count_sentiments(symbol_news)
        
        # Aggregate signals
        signals = []
        signals.extend(news_sentiment.get('signals', []))
        signals.extend(headline_analysis.get('signals', []))
        
        # Calculate score
        score = self._calculate_sentiment_score(
            news_sentiment, headline_analysis, sentiment_counts
        )
        
        # Confidence
        confidence = self.calculate_confidence(score, len(symbol_news))
        
        # Reasoning
        reasoning = self._generate_reasoning(
            symbol, news_sentiment, sentiment_counts, len(symbol_news)
        )
        
        # Metadata
        metadata = {
            'news_count': len(symbol_news),
            'positive_count': sentiment_counts['positive'],
            'negative_count': sentiment_counts['negative'],
            'neutral_count': sentiment_counts['neutral'],
            'recent_headlines': [n.get('title', '')[:100] for n in symbol_news[:5]]
        }
        
        return AgentResult(
            agent_type="sentiment",
            symbol=symbol,
            score=round(score, 2),
            confidence=confidence,
            signals=signals,
            reasoning=reasoning,
            metadata=metadata
        )
    
    async def _analyze_news_sentiment(self, news: List[Dict]) -> Dict[str, Any]:
        """
        Analyze news sentiment using OpenAI.
        Falls back to keyword-based if OpenAI unavailable.
        """
        if not llm_manager.client:
            # Fallback to keyword analysis
            return self._keyword_sentiment_analysis(news)
        
        try:
            # Use OpenAI for sophisticated sentiment analysis
            headlines = [n.get('title', '') for n in news[:10]]
            
            prompt = f"""Analyze the sentiment of these news headlines for a stock:

{chr(10).join(f"{i+1}. {h}" for i, h in enumerate(headlines))}

Provide:
1. Overall sentiment (Bullish/Bearish/Neutral)
2. Sentiment score (0-100, where 0=very bearish, 50=neutral, 100=very bullish)
3. Key themes (brief)

Format: sentiment|score|themes"""
            
            result = await llm_manager.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a financial news analyst."},
                    {"role": "user", "content": prompt}
                ],
                complexity="simple",
                max_tokens=150
            )
            
            # Parse response
            content = result.get('content', '').strip()
            parts = content.split('|')
            
            if len(parts) >= 2:
                sentiment = parts[0].strip()
                try:
                    score = float(parts[1].strip())
                except:
                    score = 50.0
                
                themes = parts[2].strip() if len(parts) > 2 else "General news"
                
                signals = [{
                    'type': 'NEWS_SENTIMENT',
                    'value': sentiment,
                    'signal': themes
                }]
                
                return {
                    'signals': signals,
                    'score': score,
                    'sentiment': sentiment,
                    'themes': themes
                }
        
        except Exception as e:
            print(f"  ⚠️  OpenAI sentiment analysis failed: {e}")
        
        # Fallback to keyword analysis
        return self._keyword_sentiment_analysis(news)
    
    def _keyword_sentiment_analysis(self, news: List[Dict]) -> Dict[str, Any]:
        """Keyword-based sentiment analysis (fallback)"""
        positive_keywords = [
            'beat', 'exceed', 'growth', 'surge', 'rally', 'gain', 'profit',
            'upgrade', 'strong', 'bullish', 'positive', 'outperform', 'buy'
        ]
        negative_keywords = [
            'miss', 'fall', 'decline', 'loss', 'downgrade', 'weak', 'bearish',
            'negative', 'underperform', 'sell', 'warning', 'concern', 'risk',
            'audit', 'probe', 'raids', 'raided', 'ban', 'banned', 'suspension',
            'suspended', 'grounded', 'regulator', 'regulatory', 'penalty',
            'penalised', 'fine', 'fined', 'investigation', 'dgca',
            'operational disruption', 'disruption', 'halted operations'
        ]
        
        pos_count = 0
        neg_count = 0
        
        regulatory_hit = False

        for item in news[:10]:
            text = f"{item.get('title', '')} {item.get('description', '')}".lower()
            
            pos_count += sum(1 for kw in positive_keywords if kw in text)
            neg_hits = [kw for kw in negative_keywords if kw in text]
            neg_count += len(neg_hits)

            if any(kw in text for kw in [
                'audit', 'regulatory', 'dgca', 'probe', 'ban', 'suspension',
                'grounded', 'operations halted', 'operational disruption'
            ]):
                regulatory_hit = True
        
        # Calculate sentiment score
        if pos_count + neg_count > 0:
            sentiment_ratio = pos_count / (pos_count + neg_count)
            score = 50 + (sentiment_ratio - 0.5) * 100
        else:
            score = 50
        
        # Strongly penalise regulatory/operational stress events
        if regulatory_hit and score > 30:
            score = 30
        
        # Determine sentiment
        if score > 65:
            sentiment = "Bullish"
            signal = "Positive news flow"
        elif score < 35 or regulatory_hit:
            sentiment = "Bearish"
            signal = "Regulatory/operational risk" if regulatory_hit else "Negative news flow"
        else:
            sentiment = "Neutral"
            signal = "Mixed news"
        
        signals = [{
            'type': 'NEWS_SENTIMENT',
            'value': sentiment,
            'signal': signal
        }]
        
        return {
            'signals': signals,
            'score': score,
            'sentiment': sentiment
        }
    
    def _analyze_headline_patterns(self, news: List[Dict]) -> Dict[str, Any]:
        """Analyze headline patterns"""
        signals = []
        
        # Check for recent earnings
        earnings_news = [
            n for n in news
            if any(kw in n.get('title', '').lower() for kw in ['earnings', 'results', 'quarter'])
        ]
        
        if earnings_news:
            title = earnings_news[0].get('title', '').lower()
            if 'beat' in title or 'exceed' in title:
                signals.append({
                    'type': 'EARNINGS',
                    'value': 'Beat estimates',
                    'signal': 'Positive'
                })
                score = 70
            elif 'miss' in title:
                signals.append({
                    'type': 'EARNINGS',
                    'value': 'Miss estimates',
                    'signal': 'Negative'
                })
                score = 30
            else:
                signals.append({
                    'type': 'EARNINGS',
                    'value': 'Results announced',
                    'signal': 'Neutral'
                })
                score = 50
        else:
            score = 50
        
        # Check for analyst actions
        analyst_news = [
            n for n in news
            if any(kw in n.get('title', '').lower() for kw in ['upgrade', 'downgrade', 'target', 'rating'])
        ]
        
        if analyst_news:
            title = analyst_news[0].get('title', '').lower()
            if 'upgrade' in title or 'raise' in title:
                signals.append({
                    'type': 'ANALYST',
                    'value': 'Upgrade',
                    'signal': 'Positive'
                })
            elif 'downgrade' in title or 'cut' in title:
                signals.append({
                    'type': 'ANALYST',
                    'value': 'Downgrade',
                    'signal': 'Negative'
                })
        
        return {'signals': signals, 'score': score}
    
    def _count_sentiments(self, news: List[Dict]) -> Dict[str, int]:
        """Count positive/negative/neutral news"""
        positive = 0
        negative = 0
        neutral = 0
        
        pos_words = ['gain', 'up', 'rise', 'growth', 'profit', 'beat', 'strong']
        neg_words = ['fall', 'down', 'decline', 'loss', 'miss', 'weak', 'concern']
        
        for item in news:
            title = item.get('title', '').lower()
            
            has_positive = any(w in title for w in pos_words)
            has_negative = any(w in title for w in neg_words)
            
            if has_positive and not has_negative:
                positive += 1
            elif has_negative and not has_positive:
                negative += 1
            else:
                neutral += 1
        
        return {
            'positive': positive,
            'negative': negative,
            'neutral': neutral
        }
    
    def _calculate_sentiment_score(
        self,
        news_sentiment: Dict,
        headline_analysis: Dict,
        sentiment_counts: Dict
    ) -> float:
        """Calculate overall sentiment score"""
        # Weight: 50% news sentiment, 30% headline patterns, 20% counts
        news_score = news_sentiment.get('score', 50)
        headline_score = headline_analysis.get('score', 50)
        
        # Calculate counts score
        total = sum(sentiment_counts.values())
        if total > 0:
            pos_ratio = sentiment_counts['positive'] / total
            count_score = 50 + (pos_ratio - 0.5) * 100
        else:
            count_score = 50
        
        final_score = (news_score * 0.5) + (headline_score * 0.3) + (count_score * 0.2)
        
        return final_score
    
    async def _analyze_general_sentiment(
        self,
        symbol: str,
        all_news: List[Dict]
    ) -> AgentResult:
        """Analyze general market sentiment when no symbol-specific news"""
        general_sentiment = self._keyword_sentiment_analysis(all_news[:10])
        
        signals = [{
            'type': 'MARKET_SENTIMENT',
            'value': general_sentiment.get('sentiment', 'Neutral'),
            'signal': 'No specific news for symbol'
        }]
        
        return AgentResult(
            agent_type="sentiment",
            symbol=symbol,
            score=50.0,  # Neutral when no news
            confidence="Low",
            signals=signals,
            reasoning=f"{symbol} - No recent news. General market sentiment: {general_sentiment.get('sentiment', 'Neutral')}.",
            metadata={'news_count': 0}
        )
    
    def _generate_reasoning(
        self,
        symbol: str,
        news_sentiment: Dict,
        sentiment_counts: Dict,
        news_count: int
    ) -> str:
        """Generate reasoning text"""
        sentiment = news_sentiment.get('sentiment', 'Neutral')
        pos = sentiment_counts.get('positive', 0)
        neg = sentiment_counts.get('negative', 0)
        
        reasoning = f"{symbol} - {news_count} recent news items. "
        reasoning += f"Sentiment: {sentiment}. "
        reasoning += f"Distribution: {pos} positive, {neg} negative."
        
        return reasoning
