"""
Global Market Agent - International Market Impact Analysis
Analyzes US, Asia, Europe markets and their impact on Indian markets
"""

import httpx
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import numpy as np

from .base import BaseAgent, AgentResult
from ..services.global_markets import get_global_indices


class GlobalMarketAgent(BaseAgent):
    """
    Analyzes global market trends and their impact on Indian markets.
    
    Key Functions:
    1. US Market Close Analysis (S&P 500, Nasdaq, Dow)
    2. Asia Market Live Analysis (Nikkei, Hang Seng, Shanghai)
    3. Europe Market Analysis (FTSE, DAX, CAC)
    4. Correlation Impact on NSE
    5. Gap Up/Down Prediction
    6. Global Sentiment (Risk-On vs Risk-Off)
    """
    
    def __init__(self, weight: float = 0.15):
        super().__init__(name="global", weight=weight)
        
        # Market correlations with NSE (approximate)
        self.correlations = {
            'S&P 500': 0.72,
            'Nasdaq': 0.68,
            'Dow': 0.65,
            'Nikkei': 0.55,
            'Hang Seng': 0.62,
            'FTSE': 0.58,
            'DAX': 0.60
        }
    
    async def analyze(
        self, 
        symbol: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Analyze global markets and predict impact on symbol.
        
        Args:
            symbol: Stock symbol (or 'NSE' for overall market)
            context: Additional context
            
        Returns:
            AgentResult with global market signals
        """
        # Fetch global market data
        global_data = await self._fetch_global_markets()
        
        if not global_data:
            return AgentResult(
                agent_type="global",
                symbol=symbol,
                score=50.0,
                confidence="Low",
                signals=[],
                reasoning="Unable to fetch global market data"
            )
        
        # Analyze different regions
        us_analysis = self._analyze_us_markets(global_data.get('us', {}))
        asia_analysis = self._analyze_asia_markets(global_data.get('asia', {}))
        europe_analysis = self._analyze_europe_markets(global_data.get('europe', {}))
        
        # Calculate global sentiment
        sentiment_score = self._calculate_global_sentiment(
            us_analysis, asia_analysis, europe_analysis
        )
        
        # Predict NSE gap
        gap_prediction = self._predict_nse_gap(
            us_analysis, asia_analysis, sentiment_score
        )
        
        # Aggregate signals
        signals = []
        signals.extend(us_analysis.get('signals', []))
        signals.extend(asia_analysis.get('signals', []))
        signals.extend(europe_analysis.get('signals', []))
        signals.append({
            'type': 'GLOBAL_SENTIMENT',
            'value': sentiment_score.get('sentiment', 'Neutral'),
            'signal': sentiment_score.get('signal', 'Neutral')
        })
        signals.append({
            'type': 'NSE_GAP_PREDICTION',
            'value': f"{gap_prediction['gap_direction']} {abs(gap_prediction['gap_pct']):.2f}%",
            'signal': gap_prediction['recommendation']
        })
        
        # Calculate overall score
        score = self._calculate_aggregate_score(
            us_analysis, asia_analysis, europe_analysis, sentiment_score
        )
        
        # Confidence based on data availability
        confidence = self.calculate_confidence(score, len(signals))
        
        # Generate reasoning
        reasoning = self._generate_reasoning(
            symbol, us_analysis, asia_analysis, gap_prediction, sentiment_score
        )
        
        # Metadata
        metadata = {
            'us_close': us_analysis.get('summary', {}),
            'asia_live': asia_analysis.get('summary', {}),
            'europe_close': europe_analysis.get('summary', {}),
            'gap_prediction': gap_prediction,
            'sentiment': sentiment_score.get('sentiment', 'Neutral'),
            'vix': global_data.get('vix', {}).get('value', 'N/A')
        }
        
        return AgentResult(
            agent_type="global",
            symbol=symbol,
            score=round(score, 2),
            confidence=confidence,
            signals=signals,
            reasoning=reasoning,
            metadata=metadata
        )
    
    async def _fetch_global_markets(self) -> Dict[str, Any]:
        """Fetch global market data from multiple sources"""
        try:
            # Use existing global_markets service
            global_summary = await get_global_indices()
            
            # Parse and structure
            us_markets = {}
            asia_markets = {}
            europe_markets = {}
            vix_data = {}
            
            for index in global_summary.get('indices', []):
                name = index.get('name', '')
                
                if name in ['S&P 500', 'Nasdaq', 'Dow Jones']:
                    us_markets[name] = {
                        'price': index.get('price'),
                        'change_pct': index.get('chg_pct'),
                        'source': index.get('source')
                    }
                elif name in ['Nikkei 225', 'Hang Seng', 'Shanghai']:
                    asia_markets[name] = {
                        'price': index.get('price'),
                        'change_pct': index.get('chg_pct'),
                        'source': index.get('source')
                    }
                elif name in ['FTSE 100', 'DAX', 'CAC 40']:
                    europe_markets[name] = {
                        'price': index.get('price'),
                        'change_pct': index.get('chg_pct'),
                        'source': index.get('source')
                    }
                elif name == 'VIX':
                    vix_data = {
                        'value': index.get('price'),
                        'change': index.get('chg_pct')
                    }
            
            return {
                'us': us_markets,
                'asia': asia_markets,
                'europe': europe_markets,
                'vix': vix_data
            }
            
        except Exception as e:
            print(f"  ⚠️  Global market fetch failed: {e}")
            return {}
    
    def _analyze_us_markets(self, us_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze US market close"""
        if not us_data:
            return {'signals': [], 'score': 50.0, 'summary': {}}
        
        signals = []
        scores = []
        
        for index_name, data in us_data.items():
            chg_pct = data.get('change_pct')
            
            if chg_pct is None:
                continue
            
            # Determine signal
            if chg_pct > 1.0:
                signal = "Strong Positive"
                score = 85
            elif chg_pct > 0.3:
                signal = "Positive"
                score = 70
            elif chg_pct > -0.3:
                signal = "Neutral"
                score = 50
            elif chg_pct > -1.0:
                signal = "Negative"
                score = 30
            else:
                signal = "Strong Negative"
                score = 15
            
            signals.append({
                'type': f'US_{index_name.replace(" ", "_").upper()}',
                'value': f"{chg_pct:+.2f}%",
                'signal': signal
            })
            
            # Weight by correlation
            correlation = self.correlations.get(index_name, 0.5)
            scores.append(score * correlation)
        
        # Calculate weighted average
        if scores:
            avg_score = sum(scores) / len(scores)
        else:
            avg_score = 50.0
        
        # Summary
        summary = {
            'overall_change': np.mean([d.get('change_pct', 0) for d in us_data.values()]),
            'session': 'Closed',
            'markets_count': len(us_data)
        }
        
        return {
            'signals': signals,
            'score': avg_score,
            'summary': summary
        }
    
    def _analyze_asia_markets(self, asia_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze Asia market live/close"""
        if not asia_data:
            return {'signals': [], 'score': 50.0, 'summary': {}}
        
        signals = []
        scores = []
        
        for index_name, data in asia_data.items():
            chg_pct = data.get('change_pct')
            
            if chg_pct is None:
                continue
            
            # Determine signal
            if chg_pct > 1.0:
                signal = "Strong Positive"
                score = 80
            elif chg_pct > 0.3:
                signal = "Positive"
                score = 65
            elif chg_pct > -0.3:
                signal = "Neutral"
                score = 50
            elif chg_pct > -1.0:
                signal = "Negative"
                score = 35
            else:
                signal = "Strong Negative"
                score = 20
            
            signals.append({
                'type': f'ASIA_{index_name.replace(" ", "_").upper()}',
                'value': f"{chg_pct:+.2f}%",
                'signal': signal
            })
            
            correlation = self.correlations.get(index_name, 0.5)
            scores.append(score * correlation)
        
        avg_score = sum(scores) / len(scores) if scores else 50.0
        
        summary = {
            'overall_change': np.mean([d.get('change_pct', 0) for d in asia_data.values()]),
            'session': 'Live/Closed',
            'markets_count': len(asia_data)
        }
        
        return {
            'signals': signals,
            'score': avg_score,
            'summary': summary
        }
    
    def _analyze_europe_markets(self, europe_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze Europe market close"""
        if not europe_data:
            return {'signals': [], 'score': 50.0, 'summary': {}}
        
        signals = []
        scores = []
        
        for index_name, data in europe_data.items():
            chg_pct = data.get('change_pct')
            
            if chg_pct is None:
                continue
            
            if chg_pct > 0.5:
                signal = "Positive"
                score = 65
            elif chg_pct > -0.5:
                signal = "Neutral"
                score = 50
            else:
                signal = "Negative"
                score = 35
            
            signals.append({
                'type': f'EUROPE_{index_name.replace(" ", "_").upper()}',
                'value': f"{chg_pct:+.2f}%",
                'signal': signal
            })
            
            correlation = self.correlations.get(index_name, 0.5)
            scores.append(score * correlation)
        
        avg_score = sum(scores) / len(scores) if scores else 50.0
        
        summary = {
            'overall_change': np.mean([d.get('change_pct', 0) for d in europe_data.values()]),
            'session': 'Closed',
            'markets_count': len(europe_data)
        }
        
        return {
            'signals': signals,
            'score': avg_score,
            'summary': summary
        }
    
    def _calculate_global_sentiment(
        self,
        us_analysis: Dict,
        asia_analysis: Dict,
        europe_analysis: Dict
    ) -> Dict[str, Any]:
        """Calculate overall global sentiment"""
        # Weighted average (US has highest weight)
        us_score = us_analysis.get('score', 50)
        asia_score = asia_analysis.get('score', 50)
        europe_score = europe_analysis.get('score', 50)
        
        # Weights: US 50%, Asia 30%, Europe 20%
        sentiment_score = (us_score * 0.5) + (asia_score * 0.3) + (europe_score * 0.2)
        
        if sentiment_score >= 70:
            sentiment = "Strong Risk-On"
            signal = "Very Bullish"
        elif sentiment_score >= 60:
            sentiment = "Risk-On"
            signal = "Bullish"
        elif sentiment_score >= 50:
            sentiment = "Neutral"
            signal = "Neutral"
        elif sentiment_score >= 40:
            sentiment = "Risk-Off"
            signal = "Bearish"
        else:
            sentiment = "Strong Risk-Off"
            signal = "Very Bearish"
        
        return {
            'sentiment': sentiment,
            'signal': signal,
            'score': sentiment_score
        }
    
    def _predict_nse_gap(
        self,
        us_analysis: Dict,
        asia_analysis: Dict,
        sentiment_score: Dict
    ) -> Dict[str, Any]:
        """Predict NSE gap up/down at opening"""
        # US markets have ~70% correlation
        us_change = us_analysis.get('summary', {}).get('overall_change', 0)
        asia_change = asia_analysis.get('summary', {}).get('overall_change', 0)
        
        # Predicted gap = 70% US impact + 30% Asia impact
        predicted_gap = (us_change * 0.7) + (asia_change * 0.3)
        
        # Adjust based on sentiment
        sentiment_adj = (sentiment_score.get('score', 50) - 50) / 100
        predicted_gap += sentiment_adj
        
        # Determine direction and recommendation
        if predicted_gap > 0.5:
            direction = "Gap Up"
            recommendation = "Buy on dips after gap-up"
        elif predicted_gap > 0.2:
            direction = "Slight Gap Up"
            recommendation = "Neutral to positive opening"
        elif predicted_gap > -0.2:
            direction = "Flat"
            recommendation = "Sideways opening expected"
        elif predicted_gap > -0.5:
            direction = "Slight Gap Down"
            recommendation = "Cautious - wait for support"
        else:
            direction = "Gap Down"
            recommendation = "Avoid buying at open, wait for bounce"
        
        return {
            'gap_pct': round(predicted_gap, 2),
            'gap_direction': direction,
            'recommendation': recommendation,
            'us_contribution': round(us_change * 0.7, 2),
            'asia_contribution': round(asia_change * 0.3, 2)
        }
    
    def _calculate_aggregate_score(
        self,
        us_analysis: Dict,
        asia_analysis: Dict,
        europe_analysis: Dict,
        sentiment_score: Dict
    ) -> float:
        """Calculate overall agent score"""
        # Use sentiment score as primary
        base_score = sentiment_score.get('score', 50)
        
        # Boost/reduce based on consistency
        us_score = us_analysis.get('score', 50)
        asia_score = asia_analysis.get('score', 50)
        
        # If all aligned, boost confidence
        if abs(us_score - asia_score) < 15:
            base_score += 5  # Markets in sync
        
        return min(100, max(0, base_score))
    
    def _generate_reasoning(
        self,
        symbol: str,
        us_analysis: Dict,
        asia_analysis: Dict,
        gap_prediction: Dict,
        sentiment_score: Dict
    ) -> str:
        """Generate plain English reasoning"""
        sentiment = sentiment_score.get('sentiment', 'Neutral')
        gap = gap_prediction.get('gap_direction', 'Flat')
        gap_pct = gap_prediction.get('gap_pct', 0)
        
        us_change = us_analysis.get('summary', {}).get('overall_change', 0)
        asia_change = asia_analysis.get('summary', {}).get('overall_change', 0)
        
        reasoning = f"Global markets show {sentiment.lower()} sentiment. "
        reasoning += f"US markets closed {us_change:+.2f}% yesterday, "
        reasoning += f"Asia markets are {asia_change:+.2f}%. "
        reasoning += f"NSE is expected to open with {gap.lower()} ({gap_pct:+.2f}%). "
        reasoning += gap_prediction.get('recommendation', '')
        
        return reasoning
