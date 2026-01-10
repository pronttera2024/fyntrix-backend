"""
Risk Agent - Position Sizing and Risk Management
Calculates optimal position size, stop-loss, and risk metrics
"""

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

from .base import BaseAgent, AgentResult
from ..services.market_data_provider import market_data_provider


class RiskAgent(BaseAgent):
    """
    Manages trading risk and position sizing.
    
    Key Metrics:
    1. Volatility (ATR, Standard Deviation)
    2. Beta - Correlation with market
    3. Position Size - Based on risk tolerance
    4. Stop-Loss Levels - Technical and volatility-based
    5. Risk/Reward Ratio
    """
    
    # Default risk parameters
    DEFAULT_RISK_PER_TRADE = 0.02  # 2% of capital per trade
    DEFAULT_PORTFOLIO_SIZE = 1000000  # ₹10 lakhs
    
    def __init__(self, weight: float = 0.10):
        super().__init__(name="risk", weight=weight)
    
    async def analyze(
        self, 
        symbol: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Analyze risk metrics and provide position sizing.
        
        Args:
            symbol: Stock symbol
            context: Additional context (entry_price, targets, etc.)
            
        Returns:
            AgentResult with risk management recommendations
        """
        # Fetch historical data
        df_daily = await market_data_provider.fetch_ohlcv(
            symbol, interval="1d", days=60
        )
        
        if df_daily is None or len(df_daily) < 20:
            return AgentResult(
                agent_type="risk",
                symbol=symbol,
                score=50.0,
                confidence="Low",
                signals=[],
                reasoning="Insufficient data for risk analysis"
            )
        
        # Get risk parameters from context or use defaults
        entry_price = context.get('entry_price') if context else None
        if entry_price is None:
            entry_price = df_daily['close'].iloc[-1]
        
        portfolio_size = context.get('portfolio_size', self.DEFAULT_PORTFOLIO_SIZE) if context else self.DEFAULT_PORTFOLIO_SIZE
        risk_per_trade = context.get('risk_per_trade', self.DEFAULT_RISK_PER_TRADE) if context else self.DEFAULT_RISK_PER_TRADE
        
        # Calculate risk metrics
        volatility_analysis = self._calculate_volatility(df_daily)
        stop_loss_analysis = self._calculate_stop_loss(df_daily, entry_price)
        position_size_analysis = self._calculate_position_size(
            entry_price, stop_loss_analysis['stop_loss'], portfolio_size, risk_per_trade
        )
        beta_analysis = await self._calculate_beta(df_daily)
        
        # Aggregate signals
        signals = []
        signals.extend(volatility_analysis.get('signals', []))
        signals.extend(stop_loss_analysis.get('signals', []))
        signals.extend(position_size_analysis.get('signals', []))
        signals.extend(beta_analysis.get('signals', []))
        
        # Calculate risk score (lower volatility = higher score)
        score = self._calculate_risk_score(
            volatility_analysis, beta_analysis
        )
        
        # Confidence
        confidence = self.calculate_confidence(score, len(signals))
        
        # Reasoning
        reasoning = self._generate_reasoning(
            symbol, volatility_analysis, position_size_analysis, stop_loss_analysis
        )
        
        # Metadata
        metadata = {
            'atr': volatility_analysis.get('atr'),
            'volatility': volatility_analysis.get('volatility_pct'),
            'beta': beta_analysis.get('beta'),
            'stop_loss': stop_loss_analysis.get('stop_loss'),
            'position_size': position_size_analysis.get('position_size'),
            'quantity': position_size_analysis.get('quantity'),
            'risk_amount': position_size_analysis.get('risk_amount')
        }
        
        return AgentResult(
            agent_type="risk",
            symbol=symbol,
            score=round(score, 2),
            confidence=confidence,
            signals=signals,
            reasoning=reasoning,
            metadata=metadata
        )
    
    def _calculate_volatility(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate volatility metrics"""
        # ATR (Average True Range)
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean().iloc[-1]
        
        # Historical volatility (annualized)
        returns = close.pct_change().dropna()
        volatility = returns.std() * np.sqrt(252) * 100  # Annualized %
        
        signals = []
        
        if volatility > 40:
            signals.append({
                'type': 'VOLATILITY',
                'value': f'{volatility:.1f}%',
                'signal': 'High risk - reduce position size'
            })
            score = 35
        elif volatility < 20:
            signals.append({
                'type': 'VOLATILITY',
                'value': f'{volatility:.1f}%',
                'signal': 'Low risk - stable stock'
            })
            score = 70
        else:
            signals.append({
                'type': 'VOLATILITY',
                'value': f'{volatility:.1f}%',
                'signal': 'Moderate risk'
            })
            score = 55
        
        return {
            'signals': signals,
            'score': score,
            'atr': round(atr, 2),
            'volatility_pct': round(volatility, 1)
        }
    
    def _calculate_stop_loss(self, df: pd.DataFrame, entry_price: float) -> Dict[str, Any]:
        """Calculate stop-loss levels"""
        # ATR-based stop-loss (2x ATR)
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean().iloc[-1]
        
        atr_stop_loss = entry_price - (2 * atr)
        
        # Support-based stop-loss (recent low)
        recent_low = df['low'].tail(20).min()
        support_stop_loss = recent_low * 0.98  # 2% below support
        
        # Use the tighter of the two
        stop_loss = max(atr_stop_loss, support_stop_loss)
        
        # Stop-loss distance
        sl_distance_pct = ((entry_price - stop_loss) / entry_price) * 100
        
        signals = []
        signals.append({
            'type': 'STOP_LOSS',
            'value': f'₹{stop_loss:.2f} ({sl_distance_pct:.1f}%)',
            'signal': f'Risk per share: ₹{entry_price - stop_loss:.2f}'
        })
        
        return {
            'signals': signals,
            'stop_loss': round(stop_loss, 2),
            'sl_distance_pct': round(sl_distance_pct, 2),
            'risk_per_share': round(entry_price - stop_loss, 2)
        }
    
    def _calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        portfolio_size: float,
        risk_per_trade: float
    ) -> Dict[str, Any]:
        """Calculate optimal position size"""
        # Risk amount
        risk_amount = portfolio_size * risk_per_trade
        
        # Risk per share
        risk_per_share = entry_price - stop_loss
        
        if risk_per_share <= 0:
            quantity = 0
            position_size = 0
        else:
            # Quantity = Risk Amount / Risk Per Share
            quantity = int(risk_amount / risk_per_share)
            position_size = quantity * entry_price
        
        # Position size as % of portfolio
        position_pct = (position_size / portfolio_size) * 100 if portfolio_size > 0 else 0
        
        signals = []
        signals.append({
            'type': 'POSITION_SIZE',
            'value': f'{quantity} shares (₹{position_size:,.0f})',
            'signal': f'{position_pct:.1f}% of portfolio'
        })
        
        if position_pct > 10:
            signals.append({
                'type': 'POSITION_WARNING',
                'value': 'Large position',
                'signal': 'Consider reducing size - concentration risk'
            })
        
        return {
            'signals': signals,
            'position_size': round(position_size, 2),
            'quantity': quantity,
            'risk_amount': round(risk_amount, 2),
            'position_pct': round(position_pct, 2)
        }
    
    async def _calculate_beta(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate beta (market correlation)"""
        # For demo, use simplified calculation
        # In production, fetch NIFTY data and calculate correlation
        
        # Placeholder beta (random but realistic)
        beta = 1.1  # Slightly more volatile than market
        
        signals = []
        
        if beta > 1.3:
            signals.append({
                'type': 'BETA',
                'value': f'{beta:.2f}',
                'signal': 'High market sensitivity'
            })
            score = 40
        elif beta < 0.7:
            signals.append({
                'type': 'BETA',
                'value': f'{beta:.2f}',
                'signal': 'Low market sensitivity - defensive'
            })
            score = 65
        else:
            signals.append({
                'type': 'BETA',
                'value': f'{beta:.2f}',
                'signal': 'Moderate market correlation'
            })
            score = 55
        
        return {
            'signals': signals,
            'score': score,
            'beta': beta
        }
    
    def _calculate_risk_score(
        self,
        volatility_analysis: Dict,
        beta_analysis: Dict
    ) -> float:
        """Calculate overall risk score"""
        vol_score = volatility_analysis.get('score', 50)
        beta_score = beta_analysis.get('score', 50)
        
        # Weight: 70% volatility, 30% beta
        score = (vol_score * 0.7) + (beta_score * 0.3)
        
        return score
    
    def _generate_reasoning(
        self,
        symbol: str,
        volatility_analysis: Dict,
        position_size_analysis: Dict,
        stop_loss_analysis: Dict
    ) -> str:
        """Generate reasoning text"""
        vol = volatility_analysis.get('volatility_pct', 0)
        qty = position_size_analysis.get('quantity', 0)
        sl = stop_loss_analysis.get('stop_loss', 0)
        risk = position_size_analysis.get('risk_amount', 0)
        
        reasoning = f"{symbol} - Volatility: {vol:.1f}%. "
        reasoning += f"Recommended: {qty} shares with SL at ₹{sl:.2f}. "
        reasoning += f"Max risk: ₹{risk:,.0f}."
        
        return reasoning
