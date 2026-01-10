"""
Options Agent - Advanced Options Strategies & Flow Analysis
Analyzes IV, OI changes, Put/Call ratio, Greeks, and multi-leg strategies

Strategies Covered:
1. Iron Condor - Range-bound income strategy
2. Butterfly Spreads - Limited risk directional play
3. Straddles/Strangles - Volatility plays
4. Ratio Spreads - Leveraged directional bets
5. Calendar Spreads - Time decay strategies
6. Basic Options Flow - IV, OI, PCR, Max Pain
"""

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import numpy as np

from .base import BaseAgent, AgentResult


class OptionsAgent(BaseAgent):
    """
    Analyzes options market data for directional signals and strategy opportunities.

    Basic Analysis:
    1. Implied Volatility (IV) - High IV = uncertainty
    2. Open Interest (OI) Changes - Build-up patterns
    3. Put/Call Ratio - Sentiment indicator
    4. Max Pain - Pin risk level
    5. Greeks - Delta, Gamma, Theta, Vega exposure

    Advanced Strategies:
    6. Iron Condor - Sell OTM put & call spreads for range-bound income
    7. Butterfly Spreads - Limited risk, capped profit directional play
    8. Straddles/Strangles - Profit from large moves in either direction
    9. Ratio Spreads - Sell more options than bought for credit
    10. Calendar Spreads - Exploit time decay differences
    """

    def __init__(self, weight: float = 0.15):
        super().__init__(name="options", weight=weight)

    async def analyze(
        self, 
        symbol: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Analyze options data for trading signals.

        Args:
            symbol: Stock symbol
            context: Additional context

        Returns:
            AgentResult with options signals
        """
        # Fetch options data (will implement API calls later)
        options_data = await self._fetch_options_data(symbol)

        if not options_data:
            return AgentResult(
                agent_type="options",
                symbol=symbol,
                score=50.0,
                confidence="Low",
                signals=[],
                reasoning="Options data not available for this symbol"
            )

        # Basic Options Flow Analysis
        iv_analysis = self._analyze_iv(options_data)
        oi_analysis = self._analyze_oi_changes(options_data)
        pcr_analysis = self._analyze_put_call_ratio(options_data)
        max_pain_analysis = self._analyze_max_pain(options_data)

        # Advanced Strategy Analysis
        iron_condor = self._analyze_iron_condor(options_data)
        butterfly = self._analyze_butterfly_spread(options_data)
        straddle = self._analyze_straddle_strangle(options_data)
        ratio_spread = self._analyze_ratio_spread(options_data)
        calendar = self._analyze_calendar_spread(options_data)

        # Aggregate signals
        signals = []
        signals.extend(iv_analysis.get('signals', []))
        signals.extend(oi_analysis.get('signals', []))
        signals.extend(pcr_analysis.get('signals', []))
        signals.extend(max_pain_analysis.get('signals', []))
        signals.extend(iron_condor.get('signals', []))
        signals.extend(butterfly.get('signals', []))
        signals.extend(straddle.get('signals', []))
        signals.extend(ratio_spread.get('signals', []))
        signals.extend(calendar.get('signals', []))

        # Calculate score (weighted combination)
        # Basic flow: 40%, Advanced strategies: 60%
        basic_scores = [
            iv_analysis.get('score', 50),
            oi_analysis.get('score', 50),
            pcr_analysis.get('score', 50),
            max_pain_analysis.get('score', 50)
        ]
        basic_score = sum(basic_scores) / len(basic_scores)

        strategy_scores = [
            iron_condor.get('score', 50),
            butterfly.get('score', 50),
            straddle.get('score', 50),
            ratio_spread.get('score', 50),
            calendar.get('score', 50)
        ]
        strategy_score = sum(strategy_scores) / len(strategy_scores)

        # Weighted blend
        score = (basic_score * 0.4) + (strategy_score * 0.6)

        # Confidence
        confidence = self.calculate_confidence(score, len(signals))

        # Reasoning
        reasoning = self._generate_reasoning(
            symbol, iv_analysis, oi_analysis, pcr_analysis, max_pain_analysis,
            iron_condor, butterfly, straddle, ratio_spread, calendar
        )

        # Metadata
        metadata = {
            'iv_percentile': iv_analysis.get('iv_percentile'),
            'pcr': pcr_analysis.get('pcr_value'),
            'max_pain': max_pain_analysis.get('max_pain_level'),
            'call_oi': oi_analysis.get('call_oi'),
            'put_oi': oi_analysis.get('put_oi'),
            'best_strategy': self._identify_best_strategy([
                iron_condor, butterfly, straddle, ratio_spread, calendar
            ]),
            'strategy_scores': {
                'iron_condor': iron_condor.get('score'),
                'butterfly': butterfly.get('score'),
                'straddle': straddle.get('score'),
                'ratio_spread': ratio_spread.get('score'),
                'calendar': calendar.get('score')
            }
        }

        return AgentResult(
            agent_type="options",
            symbol=symbol,
            score=round(score, 2),
            confidence=confidence,
            signals=signals,
            reasoning=reasoning,
            metadata=metadata
        )
    
    async def _fetch_options_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch options chain data"""
        # TODO: Implement actual API calls to NSE options API
        # For now, return demo data
        
        # Demo data structure
        return {
            'symbol': symbol,
            'spot_price': 2500,
            'iv': 25.5,  # Implied Volatility
            'iv_30d_avg': 22.0,
            'pcr': 0.85,  # Put/Call Ratio
            'call_oi': 15000000,
            'put_oi': 12750000,
            'call_oi_change': 1500000,
            'put_oi_change': -500000,
            'max_pain': 2450,
            'strikes': [
                {'strike': 2400, 'call_oi': 5000, 'put_oi': 20000},
                {'strike': 2450, 'call_oi': 8000, 'put_oi': 15000},
                {'strike': 2500, 'call_oi': 12000, 'put_oi': 10000},
                {'strike': 2550, 'call_oi': 15000, 'put_oi': 6000},
                {'strike': 2600, 'call_oi': 10000, 'put_oi': 3000}
            ]
        }
    
    def _analyze_iv(self, data: Dict) -> Dict[str, Any]:
        """Analyze Implied Volatility"""
        iv = data.get('iv', 25)
        iv_avg = data.get('iv_30d_avg', 20)
        
        # IV Percentile
        iv_percentile = ((iv - iv_avg) / iv_avg) * 100
        
        signals = []
        
        if iv_percentile > 30:
            signals.append({
                'type': 'IV',
                'value': f'{iv:.1f}% (High)',
                'signal': 'High uncertainty - potential reversal'
            })
            score = 45  # High IV = caution
        elif iv_percentile < -20:
            signals.append({
                'type': 'IV',
                'value': f'{iv:.1f}% (Low)',
                'signal': 'Low volatility - breakout possible'
            })
            score = 60  # Low IV = potential move
        else:
            signals.append({
                'type': 'IV',
                'value': f'{iv:.1f}% (Normal)',
                'signal': 'Normal volatility'
            })
            score = 50
        
        return {
            'signals': signals,
            'score': score,
            'iv_percentile': round(iv_percentile, 1)
        }
    
    def _analyze_oi_changes(self, data: Dict) -> Dict[str, Any]:
        """Analyze Open Interest changes"""
        call_oi_chg = data.get('call_oi_change', 0)
        put_oi_chg = data.get('put_oi_change', 0)
        
        signals = []
        
        if call_oi_chg > 1000000 and put_oi_chg < -500000:
            signals.append({
                'type': 'OI_BUILD_UP',
                'value': 'Call build-up + Put unwinding',
                'signal': 'Strong Bullish'
            })
            score = 80
        elif put_oi_chg > 1000000 and call_oi_chg < -500000:
            signals.append({
                'type': 'OI_BUILD_UP',
                'value': 'Put build-up + Call unwinding',
                'signal': 'Strong Bearish'
            })
            score = 25
        elif call_oi_chg > 500000:
            signals.append({
                'type': 'OI_BUILD_UP',
                'value': 'Call build-up',
                'signal': 'Bullish'
            })
            score = 65
        elif put_oi_chg > 500000:
            signals.append({
                'type': 'OI_BUILD_UP',
                'value': 'Put build-up',
                'signal': 'Bearish'
            })
            score = 35
        else:
            signals.append({
                'type': 'OI_BUILD_UP',
                'value': 'Minimal changes',
                'signal': 'Neutral'
            })
            score = 50
        
        return {
            'signals': signals,
            'score': score,
            'call_oi': data.get('call_oi'),
            'put_oi': data.get('put_oi')
        }
    
    def _analyze_put_call_ratio(self, data: Dict) -> Dict[str, Any]:
        """Analyze Put/Call Ratio"""
        pcr = data.get('pcr', 1.0)
        
        signals = []
        
        if pcr > 1.5:
            signals.append({
                'type': 'PCR',
                'value': f'{pcr:.2f} (Oversold)',
                'signal': 'Bullish reversal likely'
            })
            score = 75
        elif pcr < 0.5:
            signals.append({
                'type': 'PCR',
                'value': f'{pcr:.2f} (Overbought)',
                'signal': 'Bearish reversal likely'
            })
            score = 30
        elif 0.7 <= pcr <= 1.0:
            signals.append({
                'type': 'PCR',
                'value': f'{pcr:.2f} (Balanced)',
                'signal': 'Neutral sentiment'
            })
            score = 50
        else:
            signals.append({
                'type': 'PCR',
                'value': f'{pcr:.2f}',
                'signal': 'Mixed sentiment'
            })
            score = 50
        
        return {
            'signals': signals,
            'score': score,
            'pcr_value': pcr
        }
    
    def _analyze_max_pain(self, data: Dict) -> Dict[str, Any]:
        """Analyze Max Pain level"""
        spot = data.get('spot_price', 2500)
        max_pain = data.get('max_pain', 2450)
        
        distance_pct = ((spot - max_pain) / max_pain) * 100
        
        signals = []
        
        if distance_pct > 5:
            signals.append({
                'type': 'MAX_PAIN',
                'value': f'₹{max_pain} ({distance_pct:+.1f}%)',
                'signal': 'Downward pressure possible'
            })
            score = 40
        elif distance_pct < -5:
            signals.append({
                'type': 'MAX_PAIN',
                'value': f'₹{max_pain} ({distance_pct:+.1f}%)',
                'signal': 'Upward pull expected'
            })
            score = 65
        else:
            signals.append({
                'type': 'MAX_PAIN',
                'value': f'₹{max_pain} (Near spot)',
                'signal': 'Trading near max pain'
            })
            score = 50
        
        return {
            'signals': signals,
            'score': score,
            'max_pain_level': max_pain
        }
    
    def _analyze_iron_condor(self, data: Dict) -> Dict[str, Any]:
        """
        Analyze Iron Condor opportunity (range-bound income strategy)
        
        Setup: Sell OTM put spread + Sell OTM call spread
        Best when: Low IV, range-bound market, high theta decay
        """
        spot = data.get('spot_price', 2500)
        iv = data.get('iv', 25)
        iv_avg = data.get('iv_30d_avg', 20)
        
        signals = []
        
        # Iron Condor is best in low IV, range-bound conditions
        iv_percentile = ((iv - iv_avg) / iv_avg) * 100
        
        if iv_percentile < -15 and abs(iv_percentile) < 30:
            # Low IV + not too volatile = good for Iron Condor
            signals.append({
                'type': 'IRON_CONDOR',
                'value': f'IV {iv:.1f}% (Low)',
                'signal': 'Excellent for range income - sell OTM spreads'
            })
            score = 75
        elif iv_percentile < 10:
            signals.append({
                'type': 'IRON_CONDOR',
                'value': f'IV {iv:.1f}% (Moderate)',
                'signal': 'Favorable for income - watch breakout risk'
            })
            score = 60
        else:
            signals.append({
                'type': 'IRON_CONDOR',
                'value': f'IV {iv:.1f}% (High)',
                'signal': 'Risky - high IV increases assignment risk'
            })
            score = 35
        
        return {
            'signals': signals,
            'score': score,
            'strategy': 'iron_condor'
        }
    
    def _analyze_butterfly_spread(self, data: Dict) -> Dict[str, Any]:
        """
        Analyze Butterfly Spread opportunity (limited risk directional play)
        
        Setup: Buy 1 ITM, Sell 2 ATM, Buy 1 OTM (same expiry)
        Best when: Expecting minimal movement, max profit at middle strike
        """
        spot = data.get('spot_price', 2500)
        max_pain = data.get('max_pain', 2450)
        
        signals = []
        
        # Butterfly profits when price stays at middle strike
        distance_to_pain = abs((spot - max_pain) / max_pain) * 100
        
        if distance_to_pain < 2:
            # Price very close to max pain - perfect for butterfly
            signals.append({
                'type': 'BUTTERFLY',
                'value': f'Near max pain ₹{max_pain}',
                'signal': 'Excellent - high probability of pinning'
            })
            score = 80
        elif distance_to_pain < 5:
            signals.append({
                'type': 'BUTTERFLY',
                'value': f'{distance_to_pain:.1f}% from max pain',
                'signal': 'Good setup - low risk/reward defined'
            })
            score = 65
        else:
            signals.append({
                'type': 'BUTTERFLY',
                'value': f'{distance_to_pain:.1f}% from max pain',
                'signal': 'Lower probability - wide range'
            })
            score = 45
        
        return {
            'signals': signals,
            'score': score,
            'strategy': 'butterfly'
        }
    
    def _analyze_straddle_strangle(self, data: Dict) -> Dict[str, Any]:
        """
        Analyze Straddle/Strangle opportunity (volatility play)
        
        Straddle: Buy ATM call + ATM put (same strike)
        Strangle: Buy OTM call + OTM put (different strikes)
        Best when: Expecting large move, before events, low IV
        """
        iv = data.get('iv', 25)
        iv_avg = data.get('iv_30d_avg', 20)
        
        signals = []
        
        iv_percentile = ((iv - iv_avg) / iv_avg) * 100
        
        if iv_percentile < -20:
            # Very low IV - cheap options, great for volatility plays
            signals.append({
                'type': 'STRADDLE',
                'value': f'IV {iv:.1f}% (Very Low)',
                'signal': 'Excellent - cheap vol, buy straddle before move'
            })
            score = 85
        elif iv_percentile < 0:
            signals.append({
                'type': 'STRADDLE',
                'value': f'IV {iv:.1f}% (Below avg)',
                'signal': 'Good - strangle for lower cost'
            })
            score = 70
        elif iv_percentile > 30:
            signals.append({
                'type': 'STRADDLE',
                'value': f'IV {iv:.1f}% (High)',
                'signal': 'Expensive - consider selling straddle instead'
            })
            score = 30
        else:
            signals.append({
                'type': 'STRADDLE',
                'value': f'IV {iv:.1f}% (Normal)',
                'signal': 'Neutral - wait for IV compression'
            })
            score = 50
        
        return {
            'signals': signals,
            'score': score,
            'strategy': 'straddle'
        }
    
    def _analyze_ratio_spread(self, data: Dict) -> Dict[str, Any]:
        """
        Analyze Ratio Spread opportunity (leveraged directional play)
        
        Setup: Buy 1 ATM, Sell 2+ OTM (same expiry)
        Best when: Strong directional view but want to reduce cost
        Risk: Unlimited if moves beyond short strikes
        """
        call_oi = data.get('call_oi', 0)
        put_oi = data.get('put_oi', 0)
        call_oi_chg = data.get('call_oi_change', 0)
        put_oi_chg = data.get('put_oi_change', 0)
        
        signals = []
        
        # Bullish ratio spread: Strong call OI suggests resistance
        if call_oi_chg > 1000000:
            signals.append({
                'type': 'RATIO_SPREAD',
                'value': 'Heavy call writing',
                'signal': 'Bullish ratio: Buy ATM call, sell 2x OTM calls'
            })
            score = 70
        # Bearish ratio spread: Strong put OI suggests support
        elif put_oi_chg > 1000000:
            signals.append({
                'type': 'RATIO_SPREAD',
                'value': 'Heavy put writing',
                'signal': 'Bearish ratio: Buy ATM put, sell 2x OTM puts'
            })
            score = 70
        else:
            signals.append({
                'type': 'RATIO_SPREAD',
                'value': 'Balanced OI',
                'signal': 'No clear ratio opportunity'
            })
            score = 50
        
        return {
            'signals': signals,
            'score': score,
            'strategy': 'ratio_spread'
        }
    
    def _analyze_calendar_spread(self, data: Dict) -> Dict[str, Any]:
        """
        Analyze Calendar Spread opportunity (time decay strategy)
        
        Setup: Sell near-term option, Buy far-term option (same strike)
        Best when: High near-term theta, expecting range-bound short-term
        Profit: From faster decay of near-term option
        """
        iv = data.get('iv', 25)
        spot = data.get('spot_price', 2500)
        max_pain = data.get('max_pain', 2450)
        
        signals = []
        
        # Calendar spreads work best when:
        # 1. Near max pain (price stays stable)
        # 2. Moderate IV (not too high or low)
        
        distance_to_pain = abs((spot - max_pain) / max_pain) * 100
        
        if distance_to_pain < 3 and 20 < iv < 35:
            signals.append({
                'type': 'CALENDAR',
                'value': f'Near pain ₹{max_pain}, IV {iv:.1f}%',
                'signal': 'Excellent - sell weekly, buy monthly ATM'
            })
            score = 80
        elif distance_to_pain < 5:
            signals.append({
                'type': 'CALENDAR',
                'value': f'Moderate range, IV {iv:.1f}%',
                'signal': 'Good - theta decay favorable'
            })
            score = 65
        else:
            signals.append({
                'type': 'CALENDAR',
                'value': f'Wide range {distance_to_pain:.1f}%',
                'signal': 'Risky - price may breach short strike'
            })
            score = 40
        
        return {
            'signals': signals,
            'score': score,
            'strategy': 'calendar'
        }
    
    def _identify_best_strategy(self, strategies: List[Dict]) -> str:
        """Identify the highest scoring strategy"""
        best = max(strategies, key=lambda x: x.get('score', 0))
        return best.get('strategy', 'none')
    
    def _generate_reasoning(
        self,
        symbol: str,
        iv_analysis: Dict,
        oi_analysis: Dict,
        pcr_analysis: Dict,
        max_pain_analysis: Dict,
        iron_condor: Dict,
        butterfly: Dict,
        straddle: Dict,
        ratio_spread: Dict,
        calendar: Dict
    ) -> str:
        """Generate reasoning text"""
        parts = []
        
        # IV insight
        if iv_analysis.get('signals'):
            parts.append(iv_analysis['signals'][0]['signal'])
        
        # Best strategy
        strategy_scores = {
            'Iron Condor': iron_condor.get('score', 0),
            'Butterfly': butterfly.get('score', 0),
            'Straddle': straddle.get('score', 0),
            'Ratio Spread': ratio_spread.get('score', 0),
            'Calendar': calendar.get('score', 0)
        }
        best_strat = max(strategy_scores, key=strategy_scores.get)
        if strategy_scores[best_strat] > 60:
            parts.append(f"Best: {best_strat}")
        
        # PCR insight
        pcr_val = pcr_analysis.get('pcr_value', 1.0)
        parts.append(f"PCR {pcr_val:.2f}")
        
        return f"{symbol} options: " + ". ".join(parts) + "."


# Note: Full implementation requires NSE Options API integration
# NSE provides options chain data at:
# https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY
# https://www.nseindia.com/api/option-chain-equities?symbol=RELIANCE
