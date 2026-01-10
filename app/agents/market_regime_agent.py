"""
Market Regime Agent
Detects current market regime (Bull/Bear/Sideways/Volatile) and adapts strategy recommendations

Regimes:
- Bull Market: Strong uptrend, higher highs, higher lows
- Bear Market: Strong downtrend, lower lows, lower highs
- Sideways: Range-bound, no clear direction
- Volatile: High volatility, whipsaw movements
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from .base import BaseAgent, AgentResult


class MarketRegimeAgent(BaseAgent):
    """
    Detects and analyzes current market regime using multiple indicators.
    
    Analyzes:
    - Trend direction (Moving averages)
    - Trend strength (ADX)
    - Volatility (ATR, rolling std)
    - Market breadth (Advance/Decline if available)
    - Support/Resistance levels
    """
    
    def __init__(self, weight: float = 0.15):
        super().__init__(name="market_regime", weight=weight)
        self.regimes = {
            'BULL': {'score_range': (70, 100), 'description': 'Strong uptrend'},
            'WEAK_BULL': {'score_range': (55, 70), 'description': 'Weakening uptrend'},
            'SIDEWAYS': {'score_range': (45, 55), 'description': 'Range-bound'},
            'WEAK_BEAR': {'score_range': (30, 45), 'description': 'Weakening downtrend'},
            'BEAR': {'score_range': (0, 30), 'description': 'Strong downtrend'}
        }
    
    async def analyze(
        self,
        symbol: str,
        context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Analyze market regime for symbol.
        
        Args:
            symbol: Stock symbol or index
            context: Market context
            
        Returns:
            AgentResult with regime analysis
        """
        context = context or {}
        
        # Fetch OHLCV data
        candles = context.get('candles')
        
        if candles is None or len(candles) == 0:
            # Fetch from chart data service
            try:
                from ..services.chart_data_service import chart_data_service
                chart_data = await chart_data_service.fetch_chart_data(symbol, '1Y')
                if chart_data and 'candles' in chart_data:
                    candles = pd.DataFrame(chart_data['candles'])
                else:
                    return self._insufficient_data_response(symbol)
            except Exception as e:
                print(f"  Market Regime: Could not fetch candles: {e}")
                return self._insufficient_data_response(symbol)
        
        # Convert to DataFrame if needed
        if isinstance(candles, list):
            candles = pd.DataFrame(candles)
        
        if len(candles) < 50:
            return self._insufficient_data_response(symbol, len(candles))
        
        # Analyze regime components
        trend_analysis = self._analyze_trend(candles)
        volatility_analysis = self._analyze_volatility(candles)
        momentum_analysis = self._analyze_momentum(candles)
        
        # Determine overall regime
        regime, regime_score = self._determine_regime(
            trend_analysis,
            volatility_analysis,
            momentum_analysis
        )
        
        # Calculate confidence
        confidence = self._calculate_confidence(trend_analysis, volatility_analysis)
        
        # Generate signals
        signals = self._generate_signals(regime, trend_analysis, volatility_analysis)
        
        # Generate reasoning
        reasoning = self._generate_reasoning(regime, trend_analysis, volatility_analysis)
        
        return AgentResult(
            agent_type=self.name,
            symbol=symbol,
            score=float(regime_score),
            confidence=confidence,
            signals=signals,
            reasoning=reasoning,
            metadata={
                'regime': regime,
                'regime_description': self.regimes.get(regime, {}).get('description', ''),
                'trend_direction': trend_analysis['direction'],
                'trend_strength': round(trend_analysis['strength'], 2),
                'volatility': volatility_analysis['level'],
                'momentum': momentum_analysis['direction'],
                'support_level': round(trend_analysis.get('support', 0), 2),
                'resistance_level': round(trend_analysis.get('resistance', 0), 2),
                'days_in_regime': trend_analysis.get('duration_days', 0)
            }
        )
    
    # ==================== Analysis Methods ====================
    
    def _analyze_trend(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze trend direction and strength"""
        
        # Calculate moving averages
        df = df.copy()
        df['SMA_20'] = df['close'].rolling(window=20).mean()
        df['SMA_50'] = df['close'].rolling(window=50).mean()
        df['SMA_200'] = df['close'].rolling(window=200).mean() if len(df) >= 200 else df['close'].rolling(window=len(df)//2).mean()
        
        current = df.iloc[-1]
        
        # Trend direction based on MA alignment
        if current['close'] > current['SMA_20'] > current['SMA_50']:
            direction = 'UP'
            trend_score = 75
        elif current['close'] < current['SMA_20'] < current['SMA_50']:
            direction = 'DOWN'
            trend_score = 25
        else:
            direction = 'FLAT'
            trend_score = 50
        
        # Calculate ADX (Average Directional Index) for trend strength
        adx = self._calculate_adx(df)
        
        # Trend strength: ADX > 25 = strong trend, < 20 = weak trend
        if adx > 25:
            strength = 'STRONG'
            strength_score = min(100, adx)
        elif adx > 20:
            strength = 'MODERATE'
            strength_score = adx
        else:
            strength = 'WEAK'
            strength_score = adx
        
        # Find support and resistance
        recent = df.tail(50)
        support = recent['low'].min()
        resistance = recent['high'].max()
        
        # Calculate trend duration
        duration_days = self._calculate_trend_duration(df)
        
        return {
            'direction': direction,
            'strength': strength_score,
            'strength_label': strength,
            'trend_score': trend_score,
            'sma_20': current['SMA_20'],
            'sma_50': current['SMA_50'],
            'sma_200': current['SMA_200'],
            'support': support,
            'resistance': resistance,
            'duration_days': duration_days
        }
    
    def _analyze_volatility(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze market volatility"""
        
        df = df.copy()
        
        # Calculate ATR (Average True Range)
        atr = self._calculate_atr(df)
        
        # Calculate rolling standard deviation
        returns = df['close'].pct_change()
        rolling_std = returns.rolling(window=20).std().iloc[-1]
        
        # Volatility level
        if rolling_std > 0.03:  # 3% daily volatility
            level = 'HIGH'
            volatility_score = 80
        elif rolling_std > 0.02:  # 2% daily volatility
            level = 'MEDIUM'
            volatility_score = 60
        else:
            level = 'LOW'
            volatility_score = 40
        
        # Recent volatility change
        recent_std = returns.tail(10).std()
        older_std = returns.tail(30).head(20).std()
        
        if recent_std > older_std * 1.5:
            trend = 'INCREASING'
        elif recent_std < older_std * 0.7:
            trend = 'DECREASING'
        else:
            trend = 'STABLE'
        
        return {
            'level': level,
            'score': volatility_score,
            'atr': atr,
            'std_dev': rolling_std,
            'trend': trend
        }
    
    def _analyze_momentum(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze price momentum"""
        
        df = df.copy()
        
        # Calculate RSI
        rsi = self._calculate_rsi(df['close'])
        
        # Calculate MACD
        macd_line, signal_line = self._calculate_macd(df['close'])
        
        # Momentum direction
        if rsi > 60 and macd_line > signal_line:
            direction = 'BULLISH'
            momentum_score = 75
        elif rsi < 40 and macd_line < signal_line:
            direction = 'BEARISH'
            momentum_score = 25
        else:
            direction = 'NEUTRAL'
            momentum_score = 50
        
        # Rate of change
        roc = ((df['close'].iloc[-1] - df['close'].iloc[-20]) / df['close'].iloc[-20]) * 100
        
        return {
            'direction': direction,
            'score': momentum_score,
            'rsi': rsi,
            'macd': macd_line,
            'macd_signal': signal_line,
            'roc': roc
        }
    
    def _determine_regime(
        self,
        trend: Dict,
        volatility: Dict,
        momentum: Dict
    ) -> tuple:
        """Determine overall market regime"""
        
        # Base score from trend
        base_score = trend['trend_score']
        
        # Adjust for volatility
        if volatility['level'] == 'HIGH':
            # High volatility = less confidence in trend
            base_score = base_score * 0.9 + 50 * 0.1  # Pull toward neutral
        
        # Adjust for momentum
        if momentum['direction'] == 'BULLISH':
            base_score = base_score * 0.7 + 75 * 0.3
        elif momentum['direction'] == 'BEARISH':
            base_score = base_score * 0.7 + 25 * 0.3
        
        # Determine regime
        for regime_name, regime_info in self.regimes.items():
            min_score, max_score = regime_info['score_range']
            if min_score <= base_score < max_score:
                return regime_name, base_score
        
        return 'SIDEWAYS', 50.0
    
    def _calculate_confidence(self, trend: Dict, volatility: Dict) -> str:
        """Calculate confidence level"""
        
        # High confidence if strong trend and low volatility
        if trend['strength_label'] == 'STRONG' and volatility['level'] == 'LOW':
            return 'High'
        elif trend['strength_label'] == 'WEAK' or volatility['level'] == 'HIGH':
            return 'Low'
        else:
            return 'Medium'
    
    def _generate_signals(
        self,
        regime: str,
        trend: Dict,
        volatility: Dict
    ) -> List[Dict[str, Any]]:
        """Generate trading signals based on regime"""
        
        signals = []
        
        # Regime signal
        if regime == 'BULL':
            signals.append({
                'type': 'Regime',
                'signal': 'STRONG_BULL',
                'description': f'Strong bull market, trend strength {trend["strength"]:.1f}'
            })
        elif regime == 'BEAR':
            signals.append({
                'type': 'Regime',
                'signal': 'STRONG_BEAR',
                'description': f'Strong bear market, trend strength {trend["strength"]:.1f}'
            })
        else:
            signals.append({
                'type': 'Regime',
                'signal': regime,
                'description': self.regimes[regime]['description']
            })
        
        # Volatility signal
        if volatility['level'] == 'HIGH':
            signals.append({
                'type': 'Volatility',
                'signal': 'HIGH_VOLATILITY',
                'description': 'Exercise caution, use wider stops'
            })
        elif volatility['trend'] == 'INCREASING':
            signals.append({
                'type': 'Volatility',
                'signal': 'RISING_VOLATILITY',
                'description': 'Volatility increasing, potential trend change'
            })
        
        # Trend signal
        if trend['direction'] == 'UP' and trend['strength_label'] == 'STRONG':
            signals.append({
                'type': 'Trend',
                'signal': 'STRONG_UPTREND',
                'description': 'Strong uptrend confirmed, ride the momentum'
            })
        elif trend['direction'] == 'DOWN' and trend['strength_label'] == 'STRONG':
            signals.append({
                'type': 'Trend',
                'signal': 'STRONG_DOWNTREND',
                'description': 'Strong downtrend, avoid longs or short'
            })
        
        return signals[:3]  # Top 3 signals
    
    def _generate_reasoning(
        self,
        regime: str,
        trend: Dict,
        volatility: Dict
    ) -> str:
        """Generate human-readable reasoning"""
        
        regime_desc = self.regimes[regime]['description']
        
        if regime == 'BULL':
            return f"Strong bull market detected. {regime_desc} with {trend['strength_label'].lower()} trend strength. " \
                   f"Price above key moving averages. {volatility['level'].capitalize()} volatility environment."
        elif regime == 'BEAR':
            return f"Strong bear market detected. {regime_desc} with {trend['strength_label'].lower()} trend strength. " \
                   f"Price below key moving averages. {volatility['level'].capitalize()} volatility environment."
        elif regime == 'SIDEWAYS':
            return f"Market in sideways/range-bound regime. {volatility['level'].capitalize()} volatility. " \
                   f"Look for range breakouts or use mean-reversion strategies."
        else:
            return f"Market in {regime_desc.lower()} phase. Trend showing signs of {trend['direction'].lower()} direction. " \
                   f"{volatility['level'].capitalize()} volatility."
    
    # ==================== Technical Indicators ====================
    
    def _calculate_adx(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average Directional Index"""
        try:
            high = df['high']
            low = df['low']
            close = df['close']
            
            # True Range
            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            
            # Directional Movement
            up_move = high - high.shift()
            down_move = low.shift() - low
            
            plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
            minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
            
            # Smoothed values
            atr = tr.rolling(window=period).mean()
            plus_di = 100 * (pd.Series(plus_dm).rolling(window=period).mean() / atr)
            minus_di = 100 * (pd.Series(minus_dm).rolling(window=period).mean() / atr)
            
            # ADX
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
            adx = dx.rolling(window=period).mean()
            
            return float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 20.0
        except:
            return 20.0  # Default moderate value
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range"""
        try:
            high = df['high']
            low = df['low']
            close = df['close']
            
            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            
            atr = tr.rolling(window=period).mean()
            return float(atr.iloc[-1])
        except:
            return 0.0
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        """Calculate Relative Strength Index"""
        try:
            delta = prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            return float(rsi.iloc[-1])
        except:
            return 50.0  # Neutral
    
    def _calculate_macd(self, prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
        """Calculate MACD"""
        try:
            ema_fast = prices.ewm(span=fast).mean()
            ema_slow = prices.ewm(span=slow).mean()
            
            macd_line = ema_fast - ema_slow
            signal_line = macd_line.ewm(span=signal).mean()
            
            return float(macd_line.iloc[-1]), float(signal_line.iloc[-1])
        except:
            return 0.0, 0.0
    
    def _calculate_trend_duration(self, df: pd.DataFrame) -> int:
        """Calculate how many days the current trend has been active"""
        try:
            df = df.copy()
            df['SMA_50'] = df['close'].rolling(window=50).mean()
            
            # Check if price is above or below SMA
            df['above_sma'] = df['close'] > df['SMA_50']
            
            # Count consecutive days in same state
            current_state = df['above_sma'].iloc[-1]
            count = 0
            
            for i in range(len(df) - 1, -1, -1):
                if df['above_sma'].iloc[i] == current_state:
                    count += 1
                else:
                    break
            
            return count
        except:
            return 0
    
    def _insufficient_data_response(self, symbol: str, candle_count: int = 0) -> AgentResult:
        """Return response when insufficient data"""
        return AgentResult(
            agent_type=self.name,
            symbol=symbol,
            score=50.0,
            confidence='Low',
            signals=[],
            reasoning=f'Insufficient data for regime analysis (need 50+ candles, have {candle_count})',
            metadata={
                'regime': 'UNKNOWN',
                'regime_description': 'Insufficient data',
                'trend_direction': 'UNKNOWN',
                'trend_strength': 0,
                'volatility': 'UNKNOWN'
            }
        )


# Global instance
market_regime_agent = MarketRegimeAgent()
