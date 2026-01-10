"""
Trade Strategy Planner Agent
Generates complete, actionable trade plans with entry, exit, stop-loss, and targets

Components:
- Entry price & timing
- Stop loss (initial, trailing, final)
- Target prices (T1, T2, T3 with booking percentages)
- Position sizing
- Risk/reward ratio
- Time horizon
- Exit strategy
- Invalidation conditions
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from .base import BaseAgent, AgentResult


class TradeStrategyAgent(BaseAgent):
    """
    Creates comprehensive trading strategies based on technical analysis,
    patterns, and market regime.
    """
    
    def __init__(self, weight: float = 0.12):
        super().__init__(name="trade_strategy", weight=weight)
        self.risk_per_trade = 0.02  # 2% risk per trade default
    
    async def analyze(
        self,
        symbol: str,
        context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Generate a complete trade plan for the symbol.
        
        Args:
            symbol: Stock symbol
            context: Market context including other agent results
            
        Returns:
            AgentResult with trade plan
        """
        context = context or {}
        
        # Get current price and candles
        current_price = context.get('current_price', 0)
        candles = context.get('candles')
        
        # Fetch data if not in context
        if candles is None or current_price == 0:
            try:
                from ..services.chart_data_service import chart_data_service
                chart_data = await chart_data_service.fetch_chart_data(symbol, '1M')
                if chart_data and 'candles' in chart_data:
                    candles = pd.DataFrame(chart_data['candles'])
                    current_price = chart_data.get('current', {}).get('price', 0)
                else:
                    return self._no_trade_response(symbol, "Insufficient data")
            except Exception as e:
                return self._no_trade_response(symbol, f"Data fetch error: {e}")
        
        if isinstance(candles, list):
            candles = pd.DataFrame(candles)
        
        if len(candles) < 20 or current_price == 0:
            return self._no_trade_response(symbol, "Insufficient data for strategy")
        
        # Analyze other agents' inputs
        other_agents = context.get('agent_results', {})
        
        # Determine trade direction
        direction = self._determine_trade_direction(candles, other_agents, current_price)
        
        if direction == 'NEUTRAL':
            return self._no_trade_response(symbol, "No clear setup - mixed signals")
        
        # Calculate support and resistance
        support, resistance = self._calculate_support_resistance(candles)
        
        # Generate trade plan
        trade_plan = self._generate_trade_plan(
            symbol,
            current_price,
            direction,
            support,
            resistance,
            candles,
            other_agents
        )
        
        # Calculate score based on risk/reward and setup quality
        score = self._calculate_strategy_score(trade_plan, direction, other_agents)
        
        # Determine confidence
        confidence = self._calculate_confidence(trade_plan, other_agents)
        
        # Generate signals
        signals = self._generate_signals(trade_plan, direction)
        
        # Generate reasoning
        reasoning = self._generate_reasoning(trade_plan, direction, other_agents)
        
        return AgentResult(
            agent_type=self.name,
            symbol=symbol,
            score=float(score),
            confidence=confidence,
            signals=signals,
            reasoning=reasoning,
            metadata={
                'trade_plan': trade_plan,
                'direction': direction,
                'setup_quality': trade_plan.get('setup_quality', 'MODERATE')
            }
        )
    
    # ==================== Trade Direction ====================
    
    def _determine_trade_direction(
        self,
        candles: pd.DataFrame,
        other_agents: Dict,
        current_price: float
    ) -> str:
        """Determine if we should go long, short, or neutral"""
        
        bullish_votes = 0
        bearish_votes = 0
        
        # Check technical agent
        technical = other_agents.get('technical', {})
        if technical.get('score', 50) > 60:
            bullish_votes += 2
        elif technical.get('score', 50) < 40:
            bearish_votes += 2
        
        # Check pattern recognition
        patterns = other_agents.get('pattern_recognition', {})
        if patterns.get('score', 50) > 60:
            bullish_votes += 2
        elif patterns.get('score', 50) < 40:
            bearish_votes += 2
        
        # Check market regime
        regime = other_agents.get('market_regime', {})
        regime_type = regime.get('metadata', {}).get('regime', 'SIDEWAYS')
        if regime_type in ['BULL', 'WEAK_BULL']:
            bullish_votes += 1
        elif regime_type in ['BEAR', 'WEAK_BEAR']:
            bearish_votes += 1
        
        # Check price trend
        sma_20 = candles['close'].rolling(window=20).mean().iloc[-1]
        if current_price > sma_20:
            bullish_votes += 1
        else:
            bearish_votes += 1
        
        # Determine direction
        if bullish_votes >= bearish_votes + 2:
            return 'LONG'
        elif bearish_votes >= bullish_votes + 2:
            return 'SHORT'
        else:
            return 'NEUTRAL'
    
    def _calculate_support_resistance(self, candles: pd.DataFrame) -> tuple:
        """Calculate key support and resistance levels"""
        
        recent = candles.tail(50)
        
        # Support: recent lows
        support = recent['low'].min()
        
        # Resistance: recent highs
        resistance = recent['high'].max()
        
        # Refine with pivot points
        pivot = (recent['high'].iloc[-1] + recent['low'].iloc[-1] + recent['close'].iloc[-1]) / 3
        
        return support, resistance
    
    # ==================== Trade Plan Generation ====================
    
    def _generate_trade_plan(
        self,
        symbol: str,
        current_price: float,
        direction: str,
        support: float,
        resistance: float,
        candles: pd.DataFrame,
        other_agents: Dict
    ) -> Dict[str, Any]:
        """Generate comprehensive trade plan"""
        
        if direction == 'LONG':
            return self._generate_long_plan(
                symbol, current_price, support, resistance, candles, other_agents
            )
        else:  # SHORT
            return self._generate_short_plan(
                symbol, current_price, support, resistance, candles, other_agents
            )
    
    def _generate_long_plan(
        self,
        symbol: str,
        current_price: float,
        support: float,
        resistance: float,
        candles: pd.DataFrame,
        other_agents: Dict
    ) -> Dict[str, Any]:
        """Generate long position trade plan"""
        
        # Entry: Current price or breakout
        entry_price = current_price
        
        # Check for breakout setup
        if current_price >= resistance * 0.98:
            entry_price = resistance * 1.01  # Enter on breakout
            entry_timing = f"On breakout above {resistance:.2f} with volume"
        else:
            entry_timing = "At current levels or on pullback to support"
        
        # Stop Loss: Below support with buffer
        atr = self._calculate_atr(candles)
        stop_loss = max(support * 0.98, current_price - (2 * atr))
        
        # Risk per share
        risk_per_share = entry_price - stop_loss
        
        # Targets based on risk/reward
        target_1 = entry_price + (risk_per_share * 1.5)  # 1:1.5 RR
        target_2 = entry_price + (risk_per_share * 2.5)  # 1:2.5 RR
        target_3 = entry_price + (risk_per_share * 4.0)  # 1:4 RR
        
        # Position sizing (2% risk)
        capital = 100000  # Assume 1L capital
        position_size = int((capital * self.risk_per_trade) / risk_per_share)
        
        # Determine setup quality
        rr_ratio = (target_2 - entry_price) / risk_per_share
        if rr_ratio >= 3:
            setup_quality = 'EXCELLENT'
        elif rr_ratio >= 2:
            setup_quality = 'GOOD'
        else:
            setup_quality = 'MODERATE'
        
        return {
            'direction': 'LONG',
            'entry': {
                'price': round(entry_price, 2),
                'timing': entry_timing,
                'position_size': position_size,
                'quantity': int(position_size / entry_price)
            },
            'stop_loss': {
                'initial': round(stop_loss, 2),
                'trailing': f"Move to breakeven after +{((target_1 - entry_price) / entry_price * 100):.1f}%",
                'final': round(entry_price, 2)
            },
            'targets': {
                'T1': {
                    'price': round(target_1, 2),
                    'booking': '33%',
                    'rr_ratio': 1.5,
                    'gain': round(((target_1 - entry_price) / entry_price) * 100, 1)
                },
                'T2': {
                    'price': round(target_2, 2),
                    'booking': '33%',
                    'rr_ratio': 2.5,
                    'gain': round(((target_2 - entry_price) / entry_price) * 100, 1)
                },
                'T3': {
                    'price': round(target_3, 2),
                    'booking': '34%',
                    'rr_ratio': 4.0,
                    'gain': round(((target_3 - entry_price) / entry_price) * 100, 1)
                }
            },
            'risk_reward': round(rr_ratio, 2),
            'time_horizon': '5-15 days',
            'risk_percent': 2.0,
            'invalidation': f"Close below {stop_loss:.2f} on daily chart",
            'setup_quality': setup_quality
        }
    
    def _generate_short_plan(
        self,
        symbol: str,
        current_price: float,
        support: float,
        resistance: float,
        candles: pd.DataFrame,
        other_agents: Dict
    ) -> Dict[str, Any]:
        """Generate short position trade plan"""
        
        # Entry: Current price or breakdown
        entry_price = current_price
        
        # Check for breakdown setup
        if current_price <= support * 1.02:
            entry_price = support * 0.99  # Enter on breakdown
            entry_timing = f"On breakdown below {support:.2f} with volume"
        else:
            entry_timing = "At current levels or on rally to resistance"
        
        # Stop Loss: Above resistance with buffer
        atr = self._calculate_atr(candles)
        stop_loss = min(resistance * 1.02, current_price + (2 * atr))
        
        # Risk per share
        risk_per_share = stop_loss - entry_price
        
        # Targets based on risk/reward
        target_1 = entry_price - (risk_per_share * 1.5)
        target_2 = entry_price - (risk_per_share * 2.5)
        target_3 = entry_price - (risk_per_share * 4.0)
        
        # Position sizing
        capital = 100000
        position_size = int((capital * self.risk_per_trade) / risk_per_share)
        
        # Setup quality
        rr_ratio = (entry_price - target_2) / risk_per_share
        if rr_ratio >= 3:
            setup_quality = 'EXCELLENT'
        elif rr_ratio >= 2:
            setup_quality = 'GOOD'
        else:
            setup_quality = 'MODERATE'
        
        return {
            'direction': 'SHORT',
            'entry': {
                'price': round(entry_price, 2),
                'timing': entry_timing,
                'position_size': position_size,
                'quantity': int(position_size / entry_price)
            },
            'stop_loss': {
                'initial': round(stop_loss, 2),
                'trailing': f"Move to breakeven after -{((entry_price - target_1) / entry_price * 100):.1f}%",
                'final': round(entry_price, 2)
            },
            'targets': {
                'T1': {
                    'price': round(target_1, 2),
                    'booking': '33%',
                    'rr_ratio': 1.5,
                    'gain': round(((entry_price - target_1) / entry_price) * 100, 1)
                },
                'T2': {
                    'price': round(target_2, 2),
                    'booking': '33%',
                    'rr_ratio': 2.5,
                    'gain': round(((entry_price - target_2) / entry_price) * 100, 1)
                },
                'T3': {
                    'price': round(target_3, 2),
                    'booking': '34%',
                    'rr_ratio': 4.0,
                    'gain': round(((entry_price - target_3) / entry_price) * 100, 1)
                }
            },
            'risk_reward': round(rr_ratio, 2),
            'time_horizon': '5-15 days',
            'risk_percent': 2.0,
            'invalidation': f"Close above {stop_loss:.2f} on daily chart",
            'setup_quality': setup_quality
        }
    
    # ==================== Scoring & Signals ====================
    
    def _calculate_strategy_score(
        self,
        trade_plan: Dict,
        direction: str,
        other_agents: Dict
    ) -> float:
        """Calculate strategy quality score"""
        
        base_score = 50
        
        # Risk/reward bonus
        rr = trade_plan.get('risk_reward', 1)
        if rr >= 3:
            base_score += 20
        elif rr >= 2:
            base_score += 15
        elif rr >= 1.5:
            base_score += 10
        
        # Setup quality bonus
        quality = trade_plan.get('setup_quality', 'MODERATE')
        if quality == 'EXCELLENT':
            base_score += 15
        elif quality == 'GOOD':
            base_score += 10
        
        # Agent consensus bonus
        if direction == 'LONG':
            avg_agent_score = np.mean([
                other_agents.get('technical', {}).get('score', 50),
                other_agents.get('pattern_recognition', {}).get('score', 50),
                other_agents.get('market_regime', {}).get('score', 50)
            ])
            if avg_agent_score > 60:
                base_score += 10
        else:  # SHORT
            avg_agent_score = np.mean([
                other_agents.get('technical', {}).get('score', 50),
                other_agents.get('pattern_recognition', {}).get('score', 50),
                other_agents.get('market_regime', {}).get('score', 50)
            ])
            if avg_agent_score < 40:
                base_score += 10
        
        return min(100, max(0, base_score))
    
    def _calculate_confidence(self, trade_plan: Dict, other_agents: Dict) -> str:
        """Calculate confidence level"""
        
        quality = trade_plan.get('setup_quality', 'MODERATE')
        rr = trade_plan.get('risk_reward', 1)
        
        if quality == 'EXCELLENT' and rr >= 3:
            return 'High'
        elif quality in ['GOOD', 'EXCELLENT'] and rr >= 2:
            return 'Medium'
        else:
            return 'Low'
    
    def _generate_signals(self, trade_plan: Dict, direction: str) -> List[Dict]:
        """Generate trading signals"""
        
        signals = []
        
        entry = trade_plan['entry']
        targets = trade_plan['targets']
        stop_loss = trade_plan['stop_loss']
        
        # Entry signal
        signals.append({
            'type': 'Entry',
            'signal': f"{direction} @ {entry['price']}",
            'description': entry['timing']
        })
        
        # Target signal
        signals.append({
            'type': 'Target',
            'signal': f"T1: {targets['T1']['price']} ({targets['T1']['gain']}%)",
            'description': f"Book {targets['T1']['booking']} at T1"
        })
        
        # Stop loss signal
        signals.append({
            'type': 'Risk Management',
            'signal': f"SL: {stop_loss['initial']}",
            'description': stop_loss['trailing']
        })
        
        return signals
    
    def _generate_reasoning(
        self,
        trade_plan: Dict,
        direction: str,
        other_agents: Dict
    ) -> str:
        """Generate reasoning for trade plan"""
        
        entry = trade_plan['entry']
        targets = trade_plan['targets']
        rr = trade_plan['risk_reward']
        quality = trade_plan['setup_quality']
        
        return f"{quality} {direction.lower()} setup with 1:{rr} risk/reward. " \
               f"Entry: {entry['price']}, Target: {targets['T2']['price']} (+{targets['T2']['gain']}%). " \
               f"Stop loss: {trade_plan['stop_loss']['initial']}. " \
               f"{trade_plan['time_horizon']} holding period expected."
    
    # ==================== Helpers ====================
    
    def _calculate_atr(self, candles: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range"""
        try:
            high = candles['high']
            low = candles['low']
            close = candles['close']
            
            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            
            atr = tr.rolling(window=period).mean().iloc[-1]
            return float(atr)
        except:
            return 0.0
    
    def _no_trade_response(self, symbol: str, reason: str) -> AgentResult:
        """Return no-trade response"""
        return AgentResult(
            agent_type=self.name,
            symbol=symbol,
            score=50.0,
            confidence='Low',
            signals=[],
            reasoning=f"No trade setup: {reason}",
            metadata={
                'trade_plan': None,
                'direction': 'NEUTRAL',
                'setup_quality': 'NONE'
            }
        )


# Global instance
trade_strategy_agent = TradeStrategyAgent()
