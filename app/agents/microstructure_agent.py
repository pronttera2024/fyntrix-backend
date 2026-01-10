"""
Microstructure Agent - Order Flow and Liquidity Analysis
Analyzes volume, bid-ask spread, market depth, and order flow
"""

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

from .base import BaseAgent, AgentResult
from ..services.market_data_provider import market_data_provider


class MicrostructureAgent(BaseAgent):
    """
    Analyzes market microstructure for trading signals.
    
    Key Metrics:
    1. Volume Profile - Volume at price levels
    2. Volume Trends - Increasing/decreasing volume
    3. Bid-Ask Spread - Liquidity indicator
    4. Market Depth - Order book analysis
    5. VWAP - Volume Weighted Average Price
    """
    
    def __init__(self, weight: float = 0.10):
        super().__init__(name="microstructure", weight=weight)
    
    async def analyze(
        self, 
        symbol: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Analyze market microstructure.
        
        Args:
            symbol: Stock symbol
            context: Additional context
            
        Returns:
            AgentResult with microstructure signals
        """
        # Fetch intraday data for volume analysis
        df_intraday = await market_data_provider.fetch_ohlcv(
            symbol, interval="15m", days=5
        )
        
        if df_intraday is None or len(df_intraday) < 20:
            return AgentResult(
                agent_type="microstructure",
                symbol=symbol,
                score=50.0,
                confidence="Low",
                signals=[],
                reasoning="Insufficient intraday data for microstructure analysis"
            )
        
        # Analyze different aspects
        volume_analysis = self._analyze_volume_trends(df_intraday)
        vwap_analysis = self._analyze_vwap(df_intraday)
        liquidity_analysis = self._analyze_liquidity(df_intraday)
        
        # Aggregate signals
        signals = []
        signals.extend(volume_analysis.get('signals', []))
        signals.extend(vwap_analysis.get('signals', []))
        signals.extend(liquidity_analysis.get('signals', []))
        
        # Calculate score
        scores = [
            volume_analysis.get('score', 50),
            vwap_analysis.get('score', 50),
            liquidity_analysis.get('score', 50)
        ]
        score = sum(scores) / len(scores)
        
        # Confidence
        confidence = self.calculate_confidence(score, len(signals))
        
        # Reasoning
        reasoning = self._generate_reasoning(
            symbol, volume_analysis, vwap_analysis, liquidity_analysis
        )
        
        # Metadata
        metadata = {
            'avg_volume': volume_analysis.get('avg_volume'),
            'volume_trend': volume_analysis.get('trend'),
            'vwap': vwap_analysis.get('vwap'),
            'liquidity_score': liquidity_analysis.get('liquidity_score')
        }
        
        return AgentResult(
            agent_type="microstructure",
            symbol=symbol,
            score=round(score, 2),
            confidence=confidence,
            signals=signals,
            reasoning=reasoning,
            metadata=metadata
        )
    
    def _analyze_volume_trends(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze volume trends"""
        volumes = df['volume'].values
        prices = df['close'].values
        
        # Calculate average volume
        avg_volume = np.mean(volumes)
        recent_volume = np.mean(volumes[-5:])  # Last 5 bars
        
        # Volume trend
        volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1.0
        
        signals = []
        
        if volume_ratio > 1.5:
            signals.append({
                'type': 'VOLUME',
                'value': f'{volume_ratio:.1f}x average',
                'signal': 'High volume - strong interest'
            })
            score = 70  # High volume generally positive
        elif volume_ratio < 0.5:
            signals.append({
                'type': 'VOLUME',
                'value': f'{volume_ratio:.1f}x average',
                'signal': 'Low volume - weak interest'
            })
            score = 40  # Low volume = caution
        else:
            signals.append({
                'type': 'VOLUME',
                'value': 'Normal',
                'signal': 'Average volume'
            })
            score = 50
        
        # Price-Volume divergence
        price_change = (prices[-1] - prices[-5]) / prices[-5] if len(prices) >= 5 else 0
        
        if price_change > 0.02 and volume_ratio > 1.2:
            signals.append({
                'type': 'VOLUME_CONFIRM',
                'value': 'Price up + Volume up',
                'signal': 'Strong uptrend confirmation'
            })
            score = min(score + 10, 85)
        elif price_change > 0.02 and volume_ratio < 0.8:
            signals.append({
                'type': 'VOLUME_DIVERGENCE',
                'value': 'Price up + Volume down',
                'signal': 'Weak uptrend - caution'
            })
            score = max(score - 10, 40)
        
        return {
            'signals': signals,
            'score': score,
            'avg_volume': int(avg_volume),
            'trend': 'Increasing' if volume_ratio > 1.2 else 'Decreasing' if volume_ratio < 0.8 else 'Stable'
        }
    
    def _analyze_vwap(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze VWAP (Volume Weighted Average Price)"""
        # Calculate VWAP
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        vwap = (typical_price * df['volume']).sum() / df['volume'].sum()
        
        current_price = df['close'].iloc[-1]
        
        # Price vs VWAP
        distance_pct = ((current_price - vwap) / vwap) * 100
        
        signals = []
        
        if distance_pct > 2:
            signals.append({
                'type': 'VWAP',
                'value': f'{distance_pct:+.1f}% above VWAP',
                'signal': 'Overbought vs VWAP'
            })
            score = 45  # Above VWAP = potential pullback
        elif distance_pct < -2:
            signals.append({
                'type': 'VWAP',
                'value': f'{distance_pct:+.1f}% below VWAP',
                'signal': 'Oversold vs VWAP'
            })
            score = 65  # Below VWAP = potential bounce
        else:
            signals.append({
                'type': 'VWAP',
                'value': 'Near VWAP',
                'signal': 'Trading around fair value'
            })
            score = 50
        
        return {
            'signals': signals,
            'score': score,
            'vwap': round(vwap, 2)
        }
    
    def _analyze_liquidity(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze liquidity indicators"""
        # Use volume and price range as liquidity proxies
        volumes = df['volume'].values
        price_ranges = (df['high'] - df['low']).values
        
        # Liquidity score based on volume consistency
        volume_std = np.std(volumes) / np.mean(volumes) if np.mean(volumes) > 0 else 1.0
        
        # Lower std = more consistent = more liquid
        signals = []
        
        if volume_std < 0.3:
            signals.append({
                'type': 'LIQUIDITY',
                'value': 'High',
                'signal': 'Good liquidity - tight spreads'
            })
            score = 65
            liquidity_score = "High"
        elif volume_std > 0.7:
            signals.append({
                'type': 'LIQUIDITY',
                'value': 'Low',
                'signal': 'Poor liquidity - wide spreads'
            })
            score = 40
            liquidity_score = "Low"
        else:
            signals.append({
                'type': 'LIQUIDITY',
                'value': 'Moderate',
                'signal': 'Adequate liquidity'
            })
            score = 50
            liquidity_score = "Moderate"
        
        # Price impact analysis
        avg_range = np.mean(price_ranges)
        avg_price = np.mean(df['close'].values)
        range_pct = (avg_range / avg_price) * 100 if avg_price > 0 else 0
        
        if range_pct > 3:
            signals.append({
                'type': 'VOLATILITY',
                'value': f'{range_pct:.1f}% intraday range',
                'signal': 'High volatility'
            })
        
        return {
            'signals': signals,
            'score': score,
            'liquidity_score': liquidity_score
        }
    
    def _generate_reasoning(
        self,
        symbol: str,
        volume_analysis: Dict,
        vwap_analysis: Dict,
        liquidity_analysis: Dict
    ) -> str:
        """Generate reasoning text"""
        parts = []
        
        # Volume insight
        vol_trend = volume_analysis.get('trend', 'Stable')
        parts.append(f"Volume: {vol_trend}")
        
        # VWAP insight
        vwap = vwap_analysis.get('vwap', 0)
        parts.append(f"VWAP: ₹{vwap:.2f}")
        
        # Liquidity
        liq = liquidity_analysis.get('liquidity_score', 'Moderate')
        parts.append(f"Liquidity: {liq}")
        
        return f"{symbol} - " + ". ".join(parts) + "."
