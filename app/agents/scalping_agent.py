"""
Scalping Agent - Ultra-Short-Term Trading Analysis
Analyzes bid-ask spread, tick volume, order flow, and microstructure for scalping opportunities

Scalping Strategy:
- Entry: Tight spread + high volume + favorable order flow
- Hold: Seconds to minutes
- Exit: Quick profit (0.1-0.5%) or tight stop-loss
- Focus: High liquidity stocks only

Key Metrics:
1. Bid-Ask Spread - Tighter = better for scalping
2. Tick Volume - Spikes indicate entry points
3. Order Flow - Buy/sell pressure
4. Microstructure - Sub-minute price action
5. Liquidity Score - Volume + turnover
"""

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import numpy as np

from .base import BaseAgent, AgentResult


class ScalpingAgent(BaseAgent):
    """
    Analyzes market microstructure for scalping opportunities.
    
    Scalping Requirements:
    1. High liquidity (tight spread, high volume)
    2. Clear momentum (directional price action)
    3. Favorable order flow (buyer/seller imbalance)
    4. Low slippage environment
    5. Quick profit potential (0.1-0.5%)
    
    Scoring:
    - 80-100: Excellent scalping setup
    - 60-79: Good scalping opportunity
    - 40-59: Marginal, risky
    - <40: Avoid scalping
    """
    
    def __init__(self, weight: float = 0.20):
        super().__init__(name="scalping", weight=weight)
    
    async def analyze(
        self, 
        symbol: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Analyze stock for scalping suitability.
        
        Args:
            symbol: Stock symbol
            context: Additional context with market data
            
        Returns:
            AgentResult with scalping signals
        """
        # Fetch real-time microstructure data
        microstructure_data = await self._fetch_microstructure_data(symbol, context)
        
        if not microstructure_data:
            return AgentResult(
                agent_type="scalping",
                symbol=symbol,
                score=30.0,
                confidence="Low",
                signals=[{
                    'type': 'LIQUIDITY',
                    'value': 'Insufficient data',
                    'signal': 'Not suitable for scalping - low liquidity'
                }],
                reasoning=f"{symbol} has insufficient liquidity or data for scalping"
            )
        
        # Analyze different aspects
        spread_analysis = self._analyze_spread(microstructure_data)
        volume_analysis = self._analyze_volume_spikes(microstructure_data)
        order_flow = self._analyze_order_flow(microstructure_data)
        momentum_analysis = self._analyze_micro_momentum(microstructure_data)
        liquidity_score = self._analyze_liquidity(microstructure_data)
        
        # Aggregate signals
        signals = []
        signals.extend(spread_analysis.get('signals', []))
        signals.extend(volume_analysis.get('signals', []))
        signals.extend(order_flow.get('signals', []))
        signals.extend(momentum_analysis.get('signals', []))
        signals.extend(liquidity_score.get('signals', []))
        
        # Calculate weighted score
        scores = {
            'spread': spread_analysis.get('score', 50),
            'volume': volume_analysis.get('score', 50),
            'order_flow': order_flow.get('score', 50),
            'momentum': momentum_analysis.get('score', 50),
            'liquidity': liquidity_score.get('score', 50)
        }
        
        # Weighted average (spread and liquidity are most important)
        score = (
            scores['spread'] * 0.30 +
            scores['liquidity'] * 0.25 +
            scores['volume'] * 0.20 +
            scores['order_flow'] * 0.15 +
            scores['momentum'] * 0.10
        )
        
        # Confidence based on score and data quality
        confidence = self.calculate_confidence(score, len(signals))
        
        # Generate reasoning
        reasoning = self._generate_reasoning(
            symbol, spread_analysis, volume_analysis, order_flow, 
            momentum_analysis, liquidity_score
        )
        
        # Metadata
        metadata = {
            'spread_pct': spread_analysis.get('spread_pct'),
            'volume_ratio': volume_analysis.get('volume_ratio'),
            'order_imbalance': order_flow.get('imbalance'),
            'liquidity_rank': liquidity_score.get('rank'),
            'scalp_type': self._determine_scalp_type(scores),
            'entry_side': order_flow.get('entry_side', 'NEUTRAL')
        }
        
        return AgentResult(
            agent_type="scalping",
            symbol=symbol,
            score=round(score, 2),
            confidence=confidence,
            signals=signals,
            reasoning=reasoning,
            metadata=metadata
        )
    
    async def _fetch_microstructure_data(
        self, 
        symbol: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch real-time microstructure data.
        
        In production, this would:
        - Get live bid-ask spreads
        - Fetch tick-by-tick volume
        - Get order book depth
        - Calculate real-time metrics
        
        For now, we'll use available market data and calculate proxies.
        """
        # Get recent candle data from context (1-min and 5-min)
        if not context or 'candles' not in context:
            return None
        
        candles = context.get('candles', [])
        if len(candles) < 20:
            return None
        
        # Calculate microstructure proxies from candle data
        recent = candles[-20:]  # Last 20 candles
        
        # Calculate average spread proxy (high-low as % of close)
        spreads = [(c['high'] - c['low']) / c['close'] * 100 for c in recent if c['close'] > 0]
        avg_spread = np.mean(spreads) if spreads else 0.5
        
        # Calculate volume metrics
        volumes = [c['volume'] for c in recent]
        avg_volume = np.mean(volumes) if volumes else 0
        recent_volume = volumes[-1] if volumes else 0
        volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1.0
        
        # Calculate price momentum (last candle change)
        last_candle = candles[-1]
        price_change_pct = ((last_candle['close'] - last_candle['open']) / last_candle['open'] * 100) if last_candle['open'] > 0 else 0
        
        # Order flow proxy (up candles vs down candles)
        up_candles = sum(1 for c in recent if c['close'] > c['open'])
        down_candles = len(recent) - up_candles
        order_imbalance = (up_candles - down_candles) / len(recent) * 100
        
        # Liquidity score (volume * price)
        turnover = recent_volume * last_candle['close']
        
        return {
            'symbol': symbol,
            'last_price': last_candle['close'],
            'avg_spread_pct': avg_spread,
            'current_spread_pct': (last_candle['high'] - last_candle['low']) / last_candle['close'] * 100,
            'avg_volume': avg_volume,
            'recent_volume': recent_volume,
            'volume_ratio': volume_ratio,
            'price_change_pct': price_change_pct,
            'order_imbalance': order_imbalance,
            'turnover': turnover,
            'up_candles': up_candles,
            'down_candles': down_candles
        }
    
    def _analyze_spread(self, data: Dict) -> Dict[str, Any]:
        """
        Analyze bid-ask spread for scalping suitability.
        
        Tight spread = easier to profit from small moves
        """
        spread_pct = data.get('current_spread_pct', 0.5)
        
        signals = []
        
        if spread_pct < 0.05:
            # Excellent spread (<0.05% = ultra-tight)
            signals.append({
                'type': 'SPREAD',
                'value': f'{spread_pct:.3f}% (Ultra-tight)',
                'signal': 'Excellent for scalping - minimal slippage'
            })
            score = 95
        elif spread_pct < 0.10:
            # Good spread (<0.10%)
            signals.append({
                'type': 'SPREAD',
                'value': f'{spread_pct:.3f}% (Tight)',
                'signal': 'Good for scalping - low transaction cost'
            })
            score = 80
        elif spread_pct < 0.20:
            # Acceptable spread (<0.20%)
            signals.append({
                'type': 'SPREAD',
                'value': f'{spread_pct:.2f}% (Moderate)',
                'signal': 'Acceptable for scalping - watch costs'
            })
            score = 60
        else:
            # Wide spread (>0.20%)
            signals.append({
                'type': 'SPREAD',
                'value': f'{spread_pct:.2f}% (Wide)',
                'signal': 'Too wide for scalping - high slippage risk'
            })
            score = 30
        
        return {
            'signals': signals,
            'score': score,
            'spread_pct': round(spread_pct, 3)
        }
    
    def _analyze_volume_spikes(self, data: Dict) -> Dict[str, Any]:
        """
        Analyze volume spikes for entry confirmation.
        
        High volume = strong participation, good for scalping
        """
        volume_ratio = data.get('volume_ratio', 1.0)
        
        signals = []
        
        if volume_ratio > 3.0:
            # Volume >3x average
            signals.append({
                'type': 'VOLUME',
                'value': f'{volume_ratio:.1f}x average',
                'signal': 'Massive volume spike - strong scalping entry'
            })
            score = 90
        elif volume_ratio > 2.0:
            # Volume >2x average
            signals.append({
                'type': 'VOLUME',
                'value': f'{volume_ratio:.1f}x average',
                'signal': 'High volume - good scalping opportunity'
            })
            score = 75
        elif volume_ratio > 1.5:
            # Volume >1.5x average
            signals.append({
                'type': 'VOLUME',
                'value': f'{volume_ratio:.1f}x average',
                'signal': 'Above average volume - favorable for scalping'
            })
            score = 60
        elif volume_ratio < 0.5:
            # Volume <0.5x average
            signals.append({
                'type': 'VOLUME',
                'value': f'{volume_ratio:.1f}x average',
                'signal': 'Low volume - avoid scalping'
            })
            score = 30
        else:
            # Normal volume
            signals.append({
                'type': 'VOLUME',
                'value': f'{volume_ratio:.1f}x average',
                'signal': 'Normal volume - neutral for scalping'
            })
            score = 50
        
        return {
            'signals': signals,
            'score': score,
            'volume_ratio': round(volume_ratio, 2)
        }
    
    def _analyze_order_flow(self, data: Dict) -> Dict[str, Any]:
        """
        Analyze order flow (buy vs sell pressure).
        
        Strong imbalance = directional move likely
        """
        imbalance = data.get('order_imbalance', 0)  # -100 to +100
        up_candles = data.get('up_candles', 10)
        down_candles = data.get('down_candles', 10)
        
        signals = []
        entry_side = 'NEUTRAL'
        
        if imbalance > 40:
            # Strong buying pressure
            signals.append({
                'type': 'ORDER_FLOW',
                'value': f'{up_candles} up / {down_candles} down',
                'signal': 'Strong buying - scalp long on dips'
            })
            score = 80
            entry_side = 'LONG'
        elif imbalance > 20:
            # Moderate buying
            signals.append({
                'type': 'ORDER_FLOW',
                'value': f'{up_candles} up / {down_candles} down',
                'signal': 'Buying pressure - favorable for long scalps'
            })
            score = 65
            entry_side = 'LONG'
        elif imbalance < -40:
            # Strong selling pressure
            signals.append({
                'type': 'ORDER_FLOW',
                'value': f'{up_candles} up / {down_candles} down',
                'signal': 'Strong selling - scalp short on rallies'
            })
            score = 80
            entry_side = 'SHORT'
        elif imbalance < -20:
            # Moderate selling
            signals.append({
                'type': 'ORDER_FLOW',
                'value': f'{up_candles} up / {down_candles} down',
                'signal': 'Selling pressure - favorable for short scalps'
            })
            score = 65
            entry_side = 'SHORT'
        else:
            # Balanced
            signals.append({
                'type': 'ORDER_FLOW',
                'value': f'{up_candles} up / {down_candles} down',
                'signal': 'Balanced flow - range-bound scalping'
            })
            score = 50
            entry_side = 'NEUTRAL'
        
        return {
            'signals': signals,
            'score': score,
            'imbalance': round(imbalance, 1),
            'entry_side': entry_side
        }
    
    def _analyze_micro_momentum(self, data: Dict) -> Dict[str, Any]:
        """
        Analyze micro-momentum (sub-minute price action).
        
        Clear momentum = easier to scalp in direction
        """
        price_change = data.get('price_change_pct', 0)
        
        signals = []
        
        abs_change = abs(price_change)
        
        if abs_change > 0.5:
            # Strong momentum
            direction = 'bullish' if price_change > 0 else 'bearish'
            signals.append({
                'type': 'MOMENTUM',
                'value': f'{price_change:+.2f}% (Strong)',
                'signal': f'Strong {direction} momentum - scalp with trend'
            })
            score = 75
        elif abs_change > 0.2:
            # Moderate momentum
            direction = 'bullish' if price_change > 0 else 'bearish'
            signals.append({
                'type': 'MOMENTUM',
                'value': f'{price_change:+.2f}% (Moderate)',
                'signal': f'Moderate {direction} momentum - scalp carefully'
            })
            score = 60
        else:
            # Weak momentum
            signals.append({
                'type': 'MOMENTUM',
                'value': f'{price_change:+.2f}% (Weak)',
                'signal': 'Weak momentum - range-bound scalping only'
            })
            score = 45
        
        return {
            'signals': signals,
            'score': score,
            'momentum_pct': round(price_change, 2)
        }
    
    def _analyze_liquidity(self, data: Dict) -> Dict[str, Any]:
        """
        Analyze overall liquidity for scalping.
        
        High liquidity = easier entry/exit, less slippage
        """
        turnover = data.get('turnover', 0)
        avg_volume = data.get('avg_volume', 0)
        
        signals = []
        
        # Liquidity categories (turnover in lakhs)
        turnover_lakhs = turnover / 100000
        
        if turnover_lakhs > 100:
            # Excellent liquidity (>1 crore turnover)
            signals.append({
                'type': 'LIQUIDITY',
                'value': f'₹{turnover_lakhs:.0f}L turnover',
                'signal': 'Excellent liquidity - ideal for scalping'
            })
            score = 90
            rank = 'A+'
        elif turnover_lakhs > 50:
            # Good liquidity (>50L turnover)
            signals.append({
                'type': 'LIQUIDITY',
                'value': f'₹{turnover_lakhs:.0f}L turnover',
                'signal': 'Good liquidity - suitable for scalping'
            })
            score = 75
            rank = 'A'
        elif turnover_lakhs > 10:
            # Moderate liquidity (>10L turnover)
            signals.append({
                'type': 'LIQUIDITY',
                'value': f'₹{turnover_lakhs:.0f}L turnover',
                'signal': 'Moderate liquidity - small scalps only'
            })
            score = 55
            rank = 'B'
        else:
            # Low liquidity (<10L turnover)
            signals.append({
                'type': 'LIQUIDITY',
                'value': f'₹{turnover_lakhs:.1f}L turnover',
                'signal': 'Low liquidity - not suitable for scalping'
            })
            score = 30
            rank = 'C'
        
        return {
            'signals': signals,
            'score': score,
            'rank': rank
        }
    
    def _determine_scalp_type(self, scores: Dict[str, float]) -> str:
        """Determine the type of scalping strategy suitable"""
        if scores['momentum'] > 70:
            return 'MOMENTUM_SCALP'  # Trade with strong trend
        elif scores['order_flow'] > 70:
            return 'FLOW_SCALP'  # Trade with order imbalance
        elif scores['spread'] > 80 and scores['liquidity'] > 70:
            return 'LIQUIDITY_SCALP'  # Range-bound scalping
        else:
            return 'GENERAL_SCALP'
    
    def _generate_reasoning(
        self,
        symbol: str,
        spread_analysis: Dict,
        volume_analysis: Dict,
        order_flow: Dict,
        momentum_analysis: Dict,
        liquidity_score: Dict
    ) -> str:
        """Generate reasoning text"""
        parts = []
        
        # Spread quality
        if spread_analysis.get('signals'):
            spread_signal = spread_analysis['signals'][0]['signal']
            if spread_analysis['score'] >= 80:
                parts.append("Tight spread ideal for scalping")
            elif spread_analysis['score'] < 60:
                parts.append("Wide spread reduces profit potential")
        
        # Volume confirmation
        if volume_analysis.get('score', 0) > 70:
            parts.append(f"High volume confirms entry")
        
        # Order flow direction
        entry_side = order_flow.get('entry_side', 'NEUTRAL')
        if entry_side != 'NEUTRAL':
            parts.append(f"{entry_side.lower()} bias from order flow")
        
        # Liquidity
        liq_rank = liquidity_score.get('rank', 'B')
        if liq_rank in ['A+', 'A']:
            parts.append("excellent liquidity")
        
        if not parts:
            parts.append("Marginal scalping setup")
        
        return f"{symbol} scalping: " + ". ".join(parts) + "."
    
    def generate_exit_strategy(
        self,
        symbol: str,
        entry_price: float,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate dynamic exit strategy based on volatility (ATR).
        
        Uses Average True Range (ATR) to set intelligent targets and stops
        based on current market volatility.
        
        Args:
            symbol: Stock symbol
            entry_price: Entry price for the trade
            context: Market data context with candles
            
        Returns:
            Dict containing exit strategy parameters
        """
        # Calculate ATR (Average True Range) for volatility measure
        if context and context.get('candles'):
            atr = self._calculate_atr(context)
            atr_pct = (atr / entry_price * 100) if entry_price > 0 else 0.3
        else:
            atr_pct = 0.3
            atr = (entry_price * atr_pct / 100) if entry_price > 0 else 0.0
        
        # Dynamic targets based on ATR
        # - Low volatility (ATR < 0.3%): Tighter targets
        # - Medium volatility (ATR 0.3-0.8%): Standard targets
        # - High volatility (ATR > 0.8%): Wider targets
        
        if atr_pct < 0.3:
            # Low volatility - tighter scalp
            target_pct = 0.3  # 0.3% target
            stop_pct = 0.25   # 0.25% stop
            scalp_type = "tight"
        elif atr_pct < 0.8:
            # Medium volatility - standard scalp
            target_pct = 0.5  # 0.5% target
            stop_pct = 0.4    # 0.4% stop
            scalp_type = "standard"
        else:
            # High volatility - wider scalp (more profit potential)
            target_pct = min(atr_pct * 0.8, 1.0)  # Target = 80% of ATR, max 1%
            stop_pct = min(atr_pct * 0.6, 0.8)    # Stop = 60% of ATR, max 0.8%
            scalp_type = "wide"
        
        # Calculate actual prices
        target_price = entry_price * (1 + target_pct / 100)
        stop_loss_price = entry_price * (1 - stop_pct / 100)

        # Rounded values for stable presentation
        target_pct_rounded = round(target_pct, 2)
        stop_pct_rounded = round(stop_pct, 2)
        atr_pct_rounded = round(atr_pct, 2)
        
        # Trailing stop parameters
        trailing_activation_pct = 0.2  # Activate trail after +0.2% profit
        trailing_distance_pct = 0.3    # Trail by 0.3% as per specification
        
        # Max hold time: 60 minutes as per specification
        max_hold_mins = 60
        
        return {
            'target_price': round(target_price, 2),
            'target_pct': target_pct_rounded,
            'stop_loss_price': round(stop_loss_price, 2),
            'stop_pct': stop_pct_rounded,
            'max_hold_mins': max_hold_mins,
            'trailing_stop': {
                'enabled': True,
                'activation_pct': trailing_activation_pct,
                'trail_distance_pct': trailing_distance_pct
            },
            'atr': round(atr, 2),
            'atr_pct': round(atr_pct, 3),
            'scalp_type': scalp_type,
            'conditions': [
                f'Exit at +{target_pct_rounded:.2f}% (target)',
                f'Exit at -{stop_pct_rounded:.2f}% (stop loss)',
                f'Trail stop by {trailing_distance_pct}% after +{trailing_activation_pct}% profit',
                f'Exit after {max_hold_mins} minutes max'
            ],
            'description': f'{scalp_type.capitalize()} scalp strategy: ATR={atr_pct_rounded:.2f}%, Target={target_pct_rounded:.2f}%, Stop={stop_pct_rounded:.2f}%'
        }
    
    def _calculate_atr(self, context: Optional[Dict[str, Any]] = None, period: int = 14) -> float:
        """
        Calculate Average True Range (ATR) for volatility measurement.
        
        ATR = Average of True Range over period
        True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
        
        Args:
            context: Market data context
            period: ATR period (default 14)
            
        Returns:
            ATR value
        """
        if not context or 'candles' not in context:
            # Default fallback ATR (0.3% of price)
            return 0.003
        
        candles = context.get('candles', [])
        if len(candles) < period + 1:
            return 0.003
        
        # Get recent candles
        recent = candles[-(period + 1):]
        
        true_ranges = []
        for i in range(1, len(recent)):
            high = recent[i]['high']
            low = recent[i]['low']
            prev_close = recent[i-1]['close']
            
            # True Range = max of these three
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)
        
        # Average True Range
        atr = np.mean(true_ranges) if true_ranges else 0.003
        
        return atr
