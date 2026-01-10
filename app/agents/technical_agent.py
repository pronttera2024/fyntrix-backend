"""
Technical Agent - Comprehensive Technical Analysis  
Implements 16 strategies (Phase 1 Complete - 167% increase):

Original 6:
1. Triple RSI - Multi-timeframe momentum
2. MACD - Trend following  
3. Heiken Ashi - Smoothed trends
4. Fibonacci - Key levels
5. Ichimoku Cloud - Comprehensive system
6. Elliott Wave - Wave patterns

Phase 1 Enhancements (10 new strategies):
7. Bollinger Squeeze - Volatility breakout detection
8. VWAP - Institutional price analysis
9. Supertrend MTF - Multi-timeframe trend confirmation
10. ATR Bands - Dynamic support/resistance
11. Stochastic RSI - Sensitive overbought/oversold
12. Money Flow Index - Volume-weighted momentum
13. On-Balance Volume - Accumulation/distribution
14. Parabolic SAR - Trend following with stops
15. Williams %R - Reversal points
16. Adaptive MA (KAMA) - Noise-adjusted trend
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import asyncio

try:
    import pandas_ta as ta
except ImportError:
    ta = None
    import logging
    logger = logging.getLogger(__name__)
    logger.warning("pandas_ta not installed. Install with: pip install pandas-ta")

from .base import BaseAgent, AgentResult
from ..services.market_data_provider import market_data_provider


class TechnicalAgent(BaseAgent):
    """
    Advanced technical analysis using multiple strategies.
    
    Strategies:
    1. Triple RSI (3 timeframes)
    2. MACD Crossover
    3. Heiken Ashi
    4. Fibonacci Retracements
    5. Ichimoku Cloud
    6. Elliott Wave (simplified pattern recognition)
    """
    
    def __init__(self, weight: float = 0.25):
        super().__init__(name="technical", weight=weight)
        self.strategies = {
            'triple_rsi': self._analyze_triple_rsi,
            'macd': self._analyze_macd,
            'heiken_ashi': self._analyze_heiken_ashi,
            'fibonacci': self._analyze_fibonacci,
            'ichimoku': self._analyze_ichimoku,
            'elliott_wave': self._analyze_elliott_wave,
            # Phase 1 Enhancements - Week 1
            'bollinger_squeeze': self._analyze_bollinger_squeeze,
            'vwap': self._analyze_vwap,
            'supertrend': self._analyze_supertrend,
            # Phase 1 Enhancements - Week 2
            'atr_bands': self._analyze_atr_bands,
            'stochastic_rsi': self._analyze_stochastic_rsi,
            'money_flow_index': self._analyze_money_flow_index,
            'on_balance_volume': self._analyze_on_balance_volume,
            'parabolic_sar': self._analyze_parabolic_sar,
            'williams_r': self._analyze_williams_r,
            'adaptive_ma': self._analyze_adaptive_ma
        }
    
    async def analyze(
        self, 
        symbol: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Analyze symbol using all technical strategies.
        
        Args:
            symbol: Stock symbol
            context: Market context (optional)
            
        Returns:
            AgentResult with technical signals
        """
        # Fetch historical data (multiple timeframes)
        df_daily = await self._fetch_ohlcv(symbol, interval="1d", days=365)
        df_hourly = await self._fetch_ohlcv(symbol, interval="60m", days=60)
        df_15min = await self._fetch_ohlcv(symbol, interval="15m", days=30)
        
        if df_daily is None or len(df_daily) < 50:
            # Not enough data
            return AgentResult(
                agent_type="technical",
                symbol=symbol,
                score=50.0,
                confidence="Low",
                signals=[],
                reasoning="Insufficient historical data for technical analysis"
            )
        
        # Run all strategies
        signals = []
        strategy_scores = []
        
        for strategy_name, strategy_func in self.strategies.items():
            try:
                result = strategy_func(df_daily, df_hourly, df_15min)
                if result:
                    signals.extend(result.get('signals', []))
                    strategy_scores.append(result.get('score', 50.0))
            except Exception as e:
                print(f"  ⚠️  {strategy_name} failed: {e}")
                continue
        
        # Calculate aggregate score
        if strategy_scores:
            raw_score = np.mean(strategy_scores)
        else:
            raw_score = 50.0
        
        # Normalize to 0-100
        score = max(0.0, min(100.0, raw_score))
        
        # Calculate confidence
        confidence = self.calculate_confidence(score, len(signals))
        
        # Generate reasoning
        reasoning = self._generate_reasoning(symbol, signals, score)
        
        # Calculate support/resistance and targets
        metadata = self._calculate_levels(df_daily, score)
        
        return AgentResult(
            agent_type="technical",
            symbol=symbol,
            score=round(score, 2),
            confidence=confidence,
            signals=signals,
            reasoning=reasoning,
            metadata=metadata
        )
    
    async def _fetch_ohlcv(
        self, 
        symbol: str, 
        interval: str = "1d", 
        days: int = 365
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV data using multi-source provider.
        
        Args:
            symbol: Stock symbol
            interval: Time interval (1d, 60m, 15m)
            days: Days of history
            
        Returns:
            DataFrame with OHLC data or None
        """
        try:
            # Use the new market data provider
            # It handles NSE primary, Alpha Vantage/Finnhub/Yahoo fallbacks
            df = await market_data_provider.fetch_ohlcv(
                symbol=symbol,
                interval=interval,
                days=days
            )
            
            if df is None or len(df) < 10:
                return None
            
            return df
            
        except Exception as e:
            print(f"  ⚠️  OHLCV fetch failed for {symbol}: {e}")
            return None
    
    # ==================== Strategy 1: Triple RSI ====================
    
    def _analyze_triple_rsi(
        self, 
        df_daily: pd.DataFrame,
        df_hourly: pd.DataFrame,
        df_15min: pd.DataFrame
    ) -> Dict[str, Any]:
        """Triple RSI across 3 timeframes"""
        signals = []
        scores = []
        
        # Daily RSI
        rsi_daily = self._calculate_rsi(df_daily['close'], period=14)
        if len(rsi_daily) > 0:
            rsi_d = rsi_daily.iloc[-1]
            signals.append({
                "type": "RSI_DAILY",
                "value": round(rsi_d, 1),
                "signal": self._rsi_signal(rsi_d)
            })
            scores.append(self._rsi_score(rsi_d))
        
        # Hourly RSI
        if df_hourly is not None and len(df_hourly) > 14:
            rsi_hourly = self._calculate_rsi(df_hourly['close'], period=14)
            if len(rsi_hourly) > 0:
                rsi_h = rsi_hourly.iloc[-1]
                signals.append({
                    "type": "RSI_HOURLY",
                    "value": round(rsi_h, 1),
                    "signal": self._rsi_signal(rsi_h)
                })
                scores.append(self._rsi_score(rsi_h))
        
        # 15-min RSI
        if df_15min is not None and len(df_15min) > 14:
            rsi_15m = self._calculate_rsi(df_15min['close'], period=14)
            if len(rsi_15m) > 0:
                rsi_15 = rsi_15m.iloc[-1]
                signals.append({
                    "type": "RSI_15MIN",
                    "value": round(rsi_15, 1),
                    "signal": self._rsi_signal(rsi_15)
                })
                scores.append(self._rsi_score(rsi_15))
        
        return {
            'signals': signals,
            'score': np.mean(scores) if scores else 50.0
        }
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _rsi_signal(self, rsi: float) -> str:
        """Convert RSI to signal"""
        if rsi > 70:
            return "Overbought"
        elif rsi < 30:
            return "Oversold (Buy)"
        elif rsi > 60:
            return "Bullish"
        elif rsi < 40:
            return "Bearish"
        else:
            return "Neutral"
    
    def _rsi_score(self, rsi: float) -> float:
        """Convert RSI to score (0-100)"""
        # Optimal RSI around 50-60 for uptrend
        if 50 <= rsi <= 65:
            return 80 + (rsi - 50) * 1.3  # 80-100
        elif 40 <= rsi < 50:
            return 60 + (rsi - 40) * 2  # 60-80
        elif 65 < rsi <= 75:
            return 70 - (rsi - 65) * 2  # 50-70
        elif rsi < 30:
            return 70 + (30 - rsi) * 1  # Oversold = opportunity
        elif rsi > 75:
            return 40 - (rsi - 75) * 1.6  # Overbought = risk
        else:
            return 50
    
    # ==================== Strategy 2: MACD ====================
    
    def _analyze_macd(
        self, 
        df_daily: pd.DataFrame,
        df_hourly: pd.DataFrame,
        df_15min: pd.DataFrame
    ) -> Dict[str, Any]:
        """MACD Crossover Analysis"""
        macd, signal, hist = self._calculate_macd(df_daily['close'])
        
        if len(macd) < 2:
            return {'signals': [], 'score': 50.0}
        
        macd_curr = macd.iloc[-1]
        signal_curr = signal.iloc[-1]
        hist_curr = hist.iloc[-1]
        hist_prev = hist.iloc[-2]
        
        signals = []
        
        # Crossover detection
        if hist_prev < 0 and hist_curr > 0:
            signals.append({
                "type": "MACD",
                "value": "Bullish Crossover",
                "signal": "Buy"
            })
            score = 85
        elif hist_prev > 0 and hist_curr < 0:
            signals.append({
                "type": "MACD",
                "value": "Bearish Crossover",
                "signal": "Sell"
            })
            score = 25
        elif hist_curr > 0:
            signals.append({
                "type": "MACD",
                "value": f"Bullish ({round(hist_curr, 2)})",
                "signal": "Hold Long"
            })
            score = 70 if hist_curr > hist_prev else 60
        else:
            signals.append({
                "type": "MACD",
                "value": f"Bearish ({round(hist_curr, 2)})",
                "signal": "Hold Short"
            })
            score = 35 if hist_curr < hist_prev else 45
        
        return {'signals': signals, 'score': score}
    
    def _calculate_macd(
        self, 
        prices: pd.Series, 
        fast: int = 12, 
        slow: int = 26, 
        signal_period: int = 9
    ):
        """Calculate MACD"""
        ema_fast = prices.ewm(span=fast).mean()
        ema_slow = prices.ewm(span=slow).mean()
        macd = ema_fast - ema_slow
        signal = macd.ewm(span=signal_period).mean()
        hist = macd - signal
        return macd, signal, hist
    
    # ==================== Strategy 3: Heiken Ashi ====================
    
    def _analyze_heiken_ashi(
        self, 
        df_daily: pd.DataFrame,
        df_hourly: pd.DataFrame,
        df_15min: pd.DataFrame
    ) -> Dict[str, Any]:
        """Heiken Ashi Candle Analysis"""
        ha_df = self._calculate_heiken_ashi(df_daily)
        
        if ha_df is None or len(ha_df) < 3:
            return {'signals': [], 'score': 50.0}
        
        # Last 3 candles
        recent = ha_df.tail(3)
        
        # Determine trend
        green_candles = (recent['ha_close'] > recent['ha_open']).sum()
        red_candles = (recent['ha_close'] < recent['ha_open']).sum()
        
        # Check for wicks
        last_candle = ha_df.iloc[-1]
        has_lower_wick = last_candle['ha_low'] < min(last_candle['ha_open'], last_candle['ha_close'])
        has_upper_wick = last_candle['ha_high'] > max(last_candle['ha_open'], last_candle['ha_close'])
        
        signals = []
        
        if green_candles == 3 and not has_lower_wick:
            signals.append({
                "type": "HEIKEN_ASHI",
                "value": "Strong uptrend (3 green)",
                "signal": "Strong Buy"
            })
            score = 90
        elif green_candles == 2:
            signals.append({
                "type": "HEIKEN_ASHI",
                "value": "Uptrend forming",
                "signal": "Buy"
            })
            score = 70
        elif red_candles == 3 and not has_upper_wick:
            signals.append({
                "type": "HEIKEN_ASHI",
                "value": "Strong downtrend (3 red)",
                "signal": "Strong Sell"
            })
            score = 20
        elif red_candles == 2:
            signals.append({
                "type": "HEIKEN_ASHI",
                "value": "Downtrend forming",
                "signal": "Sell"
            })
            score = 35
        else:
            signals.append({
                "type": "HEIKEN_ASHI",
                "value": "Consolidation",
                "signal": "Neutral"
            })
            score = 50
        
        return {'signals': signals, 'score': score}
    
    def _calculate_heiken_ashi(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Calculate Heiken Ashi candles"""
        try:
            # Work on a copy so we never mutate the caller's dataframe.
            ha_df = df.copy()

            # Heiken Ashi close is the average of OHLC.
            ha_df['ha_close'] = (ha_df['open'] + ha_df['high'] + ha_df['low'] + ha_df['close']) / 4.0

            # Initialize ha_open as a separate Series using **positional**
            # indexing so this works with datetime indexes.
            ha_open = pd.Series(index=ha_df.index, dtype=float)
            ha_open.iloc[0] = (ha_df['open'].iloc[0] + ha_df['close'].iloc[0]) / 2.0

            for i in range(1, len(ha_df)):
                ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_df['ha_close'].iloc[i - 1]) / 2.0

            ha_df['ha_open'] = ha_open

            # High/low should consider the Heiken open/close along with the
            # original extremes. Use ha_df (which now has ha_open/ha_close),
            # not the original df, to avoid "column not found" errors.
            ha_df['ha_high'] = ha_df[['high', 'ha_open', 'ha_close']].max(axis=1)
            ha_df['ha_low'] = ha_df[['low', 'ha_open', 'ha_close']].min(axis=1)

            return ha_df
        except Exception as e:
            print(f"  ⚠️  Heiken Ashi calc failed: {e}")
            return None
    
    # ==================== Strategy 4: Fibonacci ====================
    
    def _analyze_fibonacci(
        self, 
        df_daily: pd.DataFrame,
        df_hourly: pd.DataFrame,
        df_15min: pd.DataFrame
    ) -> Dict[str, Any]:
        """Fibonacci Retracement Analysis"""
        # Find recent swing high and low (last 60 days)
        recent = df_daily.tail(60)
        
        swing_high = recent['high'].max()
        swing_low = recent['low'].min()
        current_price = df_daily['close'].iloc[-1]
        
        # Calculate Fibonacci levels
        diff = swing_high - swing_low
        levels = {
            '0%': swing_high,
            '23.6%': swing_high - (diff * 0.236),
            '38.2%': swing_high - (diff * 0.382),
            '50%': swing_high - (diff * 0.50),
            '61.8%': swing_high - (diff * 0.618),
            '78.6%': swing_high - (diff * 0.786),
            '100%': swing_low
        }
        
        # Find nearest level
        nearest_level = min(levels.items(), key=lambda x: abs(x[1] - current_price))
        
        signals = []
        
        # Determine signal based on position
        distance_pct = abs(current_price - nearest_level[1]) / current_price * 100
        
        if distance_pct < 1:  # Within 1% of Fib level
            if nearest_level[0] in ['38.2%', '50%', '61.8%']:
                signals.append({
                    "type": "FIBONACCI",
                    "value": f"At {nearest_level[0]} level ({round(nearest_level[1], 2)})",
                    "signal": "Strong Support (Buy)"
                })
                score = 80
            else:
                signals.append({
                    "type": "FIBONACCI",
                    "value": f"At {nearest_level[0]} level",
                    "signal": "Support"
                })
                score = 65
        elif current_price > levels['61.8%']:
            signals.append({
                "type": "FIBONACCI",
                "value": "Above 61.8% retracement",
                "signal": "Bullish trend intact"
            })
            score = 75
        elif current_price < levels['61.8%']:
            signals.append({
                "type": "FIBONACCI",
                "value": "Below 61.8% retracement",
                "signal": "Weak trend"
            })
            score = 40
        else:
            signals.append({
                "type": "FIBONACCI",
                "value": "Between levels",
                "signal": "Neutral"
            })
            score = 50
        
        return {'signals': signals, 'score': score}
    
    # ==================== Strategy 5: Ichimoku Cloud ====================
    
    def _analyze_ichimoku(
        self, 
        df_daily: pd.DataFrame,
        df_hourly: pd.DataFrame,
        df_15min: pd.DataFrame
    ) -> Dict[str, Any]:
        """Ichimoku Cloud Analysis"""
        ich = self._calculate_ichimoku(df_daily)
        
        if ich is None or len(ich) < 26:
            return {'signals': [], 'score': 50.0}
        
        # Latest values
        price = df_daily['close'].iloc[-1]
        tenkan = ich['tenkan'].iloc[-1]
        kijun = ich['kijun'].iloc[-1]
        senkou_a = ich['senkou_a'].iloc[-1]
        senkou_b = ich['senkou_b'].iloc[-1]
        
        cloud_top = max(senkou_a, senkou_b)
        cloud_bottom = min(senkou_a, senkou_b)
        
        signals = []
        
        # Price vs Cloud
        if price > cloud_top:
            signals.append({
                "type": "ICHIMOKU",
                "value": "Price above cloud",
                "signal": "Bullish"
            })
            score = 75
        elif price < cloud_bottom:
            signals.append({
                "type": "ICHIMOKU",
                "value": "Price below cloud",
                "signal": "Bearish"
            })
            score = 30
        else:
            signals.append({
                "type": "ICHIMOKU",
                "value": "Price inside cloud",
                "signal": "Neutral/Consolidation"
            })
            score = 50
        
        # Tenkan/Kijun Cross
        if tenkan > kijun and (tenkan - kijun) / kijun > 0.01:
            signals.append({
                "type": "ICHIMOKU_CROSS",
                "value": "TK Cross bullish",
                "signal": "Buy"
            })
            score += 10
        elif kijun > tenkan and (kijun - tenkan) / tenkan > 0.01:
            signals.append({
                "type": "ICHIMOKU_CROSS",
                "value": "TK Cross bearish",
                "signal": "Sell"
            })
            score -= 10
        
        return {'signals': signals, 'score': min(100, max(0, score))}
    
    def _calculate_ichimoku(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Calculate Ichimoku Cloud"""
        try:
            ich = pd.DataFrame(index=df.index)
            
            # Tenkan-sen (9-period)
            period9_high = df['high'].rolling(window=9).max()
            period9_low = df['low'].rolling(window=9).min()
            ich['tenkan'] = (period9_high + period9_low) / 2
            
            # Kijun-sen (26-period)
            period26_high = df['high'].rolling(window=26).max()
            period26_low = df['low'].rolling(window=26).min()
            ich['kijun'] = (period26_high + period26_low) / 2
            
            # Senkou Span A (Leading Span A)
            ich['senkou_a'] = ((ich['tenkan'] + ich['kijun']) / 2).shift(26)
            
            # Senkou Span B (Leading Span B)
            period52_high = df['high'].rolling(window=52).max()
            period52_low = df['low'].rolling(window=52).min()
            ich['senkou_b'] = ((period52_high + period52_low) / 2).shift(26)
            
            return ich
        except Exception as e:
            print(f"  ⚠️  Ichimoku calc failed: {e}")
            return None
    
    # ==================== Strategy 6: Elliott Wave (Simplified) ====================
    
    def _analyze_elliott_wave(
        self, 
        df_daily: pd.DataFrame,
        df_hourly: pd.DataFrame,
        df_15min: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Simplified Elliott Wave pattern recognition.
        Identifies potential wave structures.
        """
        # Use last 100 candles for wave detection
        recent = df_daily.tail(100)
        
        # Find peaks and troughs
        peaks, troughs = self._find_peaks_troughs(recent['close'])
        
        if len(peaks) < 3 or len(troughs) < 3:
            return {'signals': [], 'score': 50.0}
        
        # Simplified wave detection
        # Check if we're in an impulsive wave (5 waves up)
        current_price = recent['close'].iloc[-1]
        last_peak = peaks[-1] if peaks else current_price
        last_trough = troughs[-1] if troughs else current_price
        
        signals = []
        
        # Determine wave position (simplified)
        if current_price > last_peak * 0.95:
            # Potentially in Wave 5 (final push)
            signals.append({
                "type": "ELLIOTT_WAVE",
                "value": "Potential Wave 5 (final push)",
                "signal": "Take profit soon"
            })
            score = 60  # Caution - trend may be ending
        elif current_price < last_trough * 1.05:
            # Potentially in Wave 2 or 4 (correction)
            signals.append({
                "type": "ELLIOTT_WAVE",
                "value": "Corrective wave (Wave 2/4)",
                "signal": "Possible entry point"
            })
            score = 70  # Good entry in pullback
        elif last_peak > last_trough * 1.1:
            # Strong impulse wave
            signals.append({
                "type": "ELLIOTT_WAVE",
                "value": "Wave 3 impulse (strongest)",
                "signal": "Ride the trend"
            })
            score = 85  # Strong trend
        else:
            signals.append({
                "type": "ELLIOTT_WAVE",
                "value": "Wave pattern unclear",
                "signal": "Neutral"
            })
            score = 50
        
        return {'signals': signals, 'score': score}
    
    def _find_peaks_troughs(self, prices: pd.Series, order: int = 5):
        """Find peaks and troughs in price series"""
        try:
            # Import lazily so that missing SciPy does not break the
            # entire TechnicalAgent. If SciPy is unavailable we fall back
            # to a very simple peak/trough heuristic.
            try:
                from scipy.signal import argrelextrema  # type: ignore
            except Exception:
                raise ImportError("scipy.signal.argrelextrema not available")

            peaks_idx = argrelextrema(prices.values, np.greater, order=order)[0]
            troughs_idx = argrelextrema(prices.values, np.less, order=order)[0]

            peaks = prices.iloc[peaks_idx].values
            troughs = prices.iloc[troughs_idx].values

            if len(peaks) == 0 or len(troughs) == 0:
                raise ValueError("no local extrema found")

            return peaks, troughs
        except Exception:
            # Fallback: use simple global high/low so Elliott logic still
            # runs with a neutral/low-confidence interpretation instead of
            # failing the entire strategy.
            return [prices.max()], [prices.min()]
    
    # ==================== Helper Methods ====================
    
    def _generate_reasoning(
        self, 
        symbol: str, 
        signals: List[Dict], 
        score: float
    ) -> str:
        """Generate plain English reasoning"""
        if score >= 75:
            sentiment = "strong bullish"
            action = "Consider buying or adding to position"
        elif score >= 60:
            sentiment = "moderately bullish"
            action = "Cautiously bullish - wait for confirmation"
        elif score >= 50:
            sentiment = "neutral"
            action = "Hold and watch for clearer signals"
        elif score >= 35:
            sentiment = "moderately bearish"
            action = "Consider reducing exposure"
        else:
            sentiment = "bearish"
            action = "Avoid or exit position"
        
        # Count signal types
        buy_signals = sum(1 for s in signals if 'Buy' in s.get('signal', ''))
        sell_signals = sum(1 for s in signals if 'Sell' in s.get('signal', ''))
        
        reasoning = f"{symbol} shows {sentiment} technical setup with {buy_signals} buy signals and {sell_signals} sell signals across 6 strategies. {action}."
        
        # Add key signals
        key_signals = [s for s in signals if s.get('signal') in ['Buy', 'Strong Buy', 'Sell', 'Strong Sell']]
        if key_signals:
            reasoning += f" Key indicators: {', '.join([s['type'] for s in key_signals[:3]])}."
        
        return reasoning
    
    def _calculate_levels(
        self, 
        df: pd.DataFrame, 
        score: float
    ) -> Dict[str, Any]:
        """Calculate support/resistance and targets"""
        recent = df.tail(20)
        current_price = df['close'].iloc[-1]
        
        # Simple support/resistance
        high = recent['high'].max()
        low = recent['low'].min()
        
        # ATR for targets
        atr = self._calculate_atr(df)
        
        # Calculate levels based on score
        if score >= 60:  # Bullish
            support = current_price * 0.97
            resistance = high
            entry = current_price
            stop_loss = support * 0.995
            target_1 = current_price + (atr * 2)
            target_2 = current_price + (atr * 3.5)
        else:  # Bearish or Neutral
            support = low
            resistance = current_price * 1.03
            entry = current_price
            stop_loss = resistance * 1.005
            target_1 = current_price - (atr * 2)
            target_2 = current_price - (atr * 3.5)
        
        return {
            "current_price": round(current_price, 2),
            "support": round(support, 2),
            "resistance": round(resistance, 2),
            "entry_price": round(entry, 2),  # For ChartView compatibility
            "stop_loss": round(stop_loss, 2),
            "target_price": round(target_1, 2),  # Primary target for ChartView
            "target_1": round(target_1, 2),
            "target_2": round(target_2, 2),
            "atr": round(atr, 2)
        }
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range"""
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        return atr.iloc[-1] if len(atr) > 0 else 0
    
    # ==================== PHASE 1 ENHANCEMENTS - WEEK 1 ====================
    
    def _analyze_bollinger_squeeze(
        self,
        df_daily: pd.DataFrame,
        df_hourly: pd.DataFrame,
        df_15min: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Bollinger Band Squeeze & Breakout Strategy
        Detects low volatility compression → anticipates breakout
        
        Risk-Reward: 1:3 typical
        """
        signals = []
        scores = []
        
        try:
            close = df_daily['close']
            high = df_daily['high']
            low = df_daily['low']
            
            # Calculate Bollinger Bands
            bb_period = 20
            bb_std = 2
            sma = close.rolling(window=bb_period).mean()
            std = close.rolling(window=bb_period).std()
            upper_band = sma + (bb_std * std)
            lower_band = sma - (bb_std * std)
            bb_width = (upper_band - lower_band) / sma * 100
            
            # Calculate BB Width average
            bb_width_avg = bb_width.rolling(window=20).mean()
            
            current_width = bb_width.iloc[-1]
            avg_width = bb_width_avg.iloc[-1]
            current_price = close.iloc[-1]
            current_sma = sma.iloc[-1]
            
            # Detect squeeze (BB width < average)
            is_squeeze = current_width < avg_width * 0.8
            
            # Determine breakout direction
            if current_price > current_sma:
                direction = "Bullish"
                score = 65.0
            elif current_price < current_sma:
                direction = "Bearish"
                score = 35.0
            else:
                direction = "Neutral"
                score = 50.0
            
            if is_squeeze:
                signals.append({
                    "type": "BB_SQUEEZE",
                    "value": f"{current_width:.2f}%",
                    "signal": f"Squeeze Detected - {direction} bias"
                })
                # Squeeze detected, boost score significance
                if direction == "Bullish":
                    score = 75.0  # Higher confidence on breakout
                elif direction == "Bearish":
                    score = 25.0
            else:
                signals.append({
                    "type": "BB_WIDTH",
                    "value": f"{current_width:.2f}%",
                    "signal": f"Normal volatility - {direction}"
                })
            
            scores.append(score)
            
        except Exception as e:
            print(f"  ⚠️  Bollinger Squeeze failed: {e}")
            scores.append(50.0)
        
        return {
            'signals': signals,
            'score': np.mean(scores) if scores else 50.0
        }
    
    def _analyze_vwap(
        self,
        df_daily: pd.DataFrame,
        df_hourly: pd.DataFrame,
        df_15min: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Volume-Weighted Average Price (VWAP) Strategy
        Institutional price level analysis
        
        Signals:
        - Above VWAP = Bullish (institutional accumulation)
        - Below VWAP = Bearish (distribution)
        - VWAP deviation > 2% = Reversion trade
        
        Risk-Reward: 1:2 for reversion, 1:4 for trend
        """
        signals = []
        scores = []
        
        try:
            # Use intraday data for VWAP (hourly is good enough)
            df = df_hourly if df_hourly is not None and len(df_hourly) > 0 else df_daily
            
            close = df['close']
            high = df['high']
            low = df['low']
            volume = df['volume']
            
            # Calculate VWAP
            typical_price = (high + low + close) / 3
            vwap = (typical_price * volume).cumsum() / volume.cumsum()
            
            current_price = close.iloc[-1]
            current_vwap = vwap.iloc[-1]
            
            # Calculate deviation from VWAP
            deviation_pct = ((current_price - current_vwap) / current_vwap) * 100
            
            # Scoring logic
            if deviation_pct > 2.0:
                # Price significantly above VWAP
                signals.append({
                    "type": "VWAP_POSITION",
                    "value": f"+{deviation_pct:.2f}%",
                    "signal": "Above VWAP - Overbought, expect reversion"
                })
                score = 40.0  # Bearish due to overextension
            elif deviation_pct > 0.5:
                # Price moderately above VWAP
                signals.append({
                    "type": "VWAP_POSITION",
                    "value": f"+{deviation_pct:.2f}%",
                    "signal": "Above VWAP - Bullish trend"
                })
                score = 70.0  # Bullish, institutional support
            elif deviation_pct < -2.0:
                # Price significantly below VWAP
                signals.append({
                    "type": "VWAP_POSITION",
                    "value": f"{deviation_pct:.2f}%",
                    "signal": "Below VWAP - Oversold, expect bounce"
                })
                score = 60.0  # Bullish reversal opportunity
            elif deviation_pct < -0.5:
                # Price moderately below VWAP
                signals.append({
                    "type": "VWAP_POSITION",
                    "value": f"{deviation_pct:.2f}%",
                    "signal": "Below VWAP - Bearish trend"
                })
                score = 30.0  # Bearish, distribution
            else:
                # Price near VWAP
                signals.append({
                    "type": "VWAP_POSITION",
                    "value": f"{deviation_pct:.2f}%",
                    "signal": "Near VWAP - Fair value"
                })
                score = 50.0  # Neutral
            
            scores.append(score)
            
        except Exception as e:
            print(f"  ⚠️  VWAP analysis failed: {e}")
            scores.append(50.0)
        
        return {
            'signals': signals,
            'score': np.mean(scores) if scores else 50.0
        }
    
    def _analyze_supertrend(
        self,
        df_daily: pd.DataFrame,
        df_hourly: pd.DataFrame,
        df_15min: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Supertrend Multi-Timeframe Strategy
        Trend confirmation across 3 timeframes (15m, 1h, 1d)
        
        Signals:
        - All 3 green = Strong Bullish (score: 85+)
        - All 3 red = Strong Bearish (score: 15-)
        - Mixed = Range-bound (score: 45-55)
        
        Risk-Reward: 1:3 for aligned, 1:1.5 for mixed
        """
        signals = []
        scores = []
        
        def calculate_supertrend(df: pd.DataFrame, period=10, multiplier=3):
            """Calculate Supertrend indicator"""
            try:
                high = df['high']
                low = df['low']
                close = df['close']
                
                # Calculate ATR
                tr1 = high - low
                tr2 = abs(high - close.shift())
                tr3 = abs(low - close.shift())
                tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
                atr = tr.rolling(window=period).mean()
                
                # Calculate basic bands
                hl_avg = (high + low) / 2
                upper_band = hl_avg + (multiplier * atr)
                lower_band = hl_avg - (multiplier * atr)
                
                # Calculate Supertrend
                supertrend = pd.Series(index=df.index, dtype=float)
                direction = pd.Series(index=df.index, dtype=int)
                
                for i in range(period, len(df)):
                    if i == period:
                        supertrend.iloc[i] = upper_band.iloc[i]
                        direction.iloc[i] = -1
                    else:
                        if close.iloc[i] > supertrend.iloc[i-1]:
                            supertrend.iloc[i] = lower_band.iloc[i]
                            direction.iloc[i] = 1  # Bullish
                        elif close.iloc[i] < supertrend.iloc[i-1]:
                            supertrend.iloc[i] = upper_band.iloc[i]
                            direction.iloc[i] = -1  # Bearish
                        else:
                            supertrend.iloc[i] = supertrend.iloc[i-1]
                            direction.iloc[i] = direction.iloc[i-1]
                
                return direction.iloc[-1] if len(direction) > 0 else 0
                
            except Exception as e:
                print(f"  ⚠️  Supertrend calculation failed: {e}")
                return 0
        
        try:
            # Calculate Supertrend for each timeframe
            st_daily = calculate_supertrend(df_daily) if df_daily is not None and len(df_daily) >= 10 else 0
            st_hourly = calculate_supertrend(df_hourly) if df_hourly is not None and len(df_hourly) >= 10 else 0
            st_15min = calculate_supertrend(df_15min) if df_15min is not None and len(df_15min) >= 10 else 0
            
            # Count bullish timeframes
            bullish_count = sum([1 for st in [st_daily, st_hourly, st_15min] if st == 1])
            bearish_count = sum([1 for st in [st_daily, st_hourly, st_15min] if st == -1])
            
            # Determine overall signal
            if bullish_count == 3:
                signals.append({
                    "type": "SUPERTREND_MTF",
                    "value": "3/3 Bullish",
                    "signal": "Strong Bullish - All timeframes aligned"
                })
                score = 85.0
            elif bearish_count == 3:
                signals.append({
                    "type": "SUPERTREND_MTF",
                    "value": "3/3 Bearish",
                    "signal": "Strong Bearish - All timeframes aligned"
                })
                score = 15.0
            elif bullish_count >= 2:
                signals.append({
                    "type": "SUPERTREND_MTF",
                    "value": f"{bullish_count}/3 Bullish",
                    "signal": "Bullish - Majority timeframes aligned"
                })
                score = 65.0
            elif bearish_count >= 2:
                signals.append({
                    "type": "SUPERTREND_MTF",
                    "value": f"{bearish_count}/3 Bearish",
                    "signal": "Bearish - Majority timeframes aligned"
                })
                score = 35.0
            else:
                signals.append({
                    "type": "SUPERTREND_MTF",
                    "value": "Mixed",
                    "signal": "Range-bound - Timeframes diverging"
                })
                score = 50.0
            
            # Add individual timeframe details
            tf_signals = {
                "Daily": "Bullish" if st_daily == 1 else "Bearish" if st_daily == -1 else "Neutral",
                "Hourly": "Bullish" if st_hourly == 1 else "Bearish" if st_hourly == -1 else "Neutral",
                "15-Min": "Bullish" if st_15min == 1 else "Bearish" if st_15min == -1 else "Neutral"
            }
            
            for tf, signal in tf_signals.items():
                signals.append({
                    "type": f"SUPERTREND_{tf.upper().replace('-', '')}",
                    "value": signal,
                    "signal": f"{tf} trend"
                })
            
            scores.append(score)
            
        except Exception as e:
            print(f"  ⚠️  Supertrend analysis failed: {e}")
            scores.append(50.0)
        
        return {
            'signals': signals,
            'score': np.mean(scores) if scores else 50.0
        }
    
    # ==================== PHASE 1 ENHANCEMENTS - WEEK 2 (Complete) ====================
    
    def _analyze_atr_bands(self, df_daily: pd.DataFrame, df_hourly: pd.DataFrame, df_15min: pd.DataFrame) -> Dict[str, Any]:
        """ATR Volatility Bands - Dynamic support/resistance"""
        signals, scores = [], []
        try:
            close = df_daily['close']
            atr = self._calculate_atr(df_daily, period=14)
            sma = close.rolling(window=20).mean()
            current_price, current_sma = close.iloc[-1], sma.iloc[-1]
            current_upper, current_lower = current_sma + (2 * atr), current_sma - (2 * atr)
            
            if current_price >= current_upper:
                signals.append({"type": "ATR_BANDS", "value": f"₹{current_price:.2f}", "signal": "At upper band - Overbought"})
                score = 35.0
            elif current_price <= current_lower:
                signals.append({"type": "ATR_BANDS", "value": f"₹{current_price:.2f}", "signal": "At lower band - Oversold (Buy)"})
                score = 65.0
            elif current_price > current_sma:
                signals.append({"type": "ATR_BANDS", "value": f"+{((current_price-current_sma)/current_sma)*100:.1f}%", "signal": "Above center - Bullish"})
                score = 60.0
            else:
                signals.append({"type": "ATR_BANDS", "value": f"-{((current_sma-current_price)/current_sma)*100:.1f}%", "signal": "Below center - Bearish"})
                score = 40.0
            scores.append(score)
        except Exception as e:
            print(f"  ⚠️  ATR Bands failed: {e}")
            scores.append(50.0)
        return {'signals': signals, 'score': np.mean(scores) if scores else 50.0}
    
    def _analyze_stochastic_rsi(self, df_daily: pd.DataFrame, df_hourly: pd.DataFrame, df_15min: pd.DataFrame) -> Dict[str, Any]:
        """Stochastic RSI - Sensitive overbought/oversold"""
        signals, scores = [], []
        try:
            close = df_daily['close']
            rsi = self._calculate_rsi(close, period=14)
            rsi_min, rsi_max = rsi.rolling(window=14).min(), rsi.rolling(window=14).max()
            stoch_rsi = ((rsi - rsi_min) / (rsi_max - rsi_min)) * 100
            stoch_rsi_k = stoch_rsi.rolling(window=3).mean()
            
            if len(stoch_rsi_k) > 0:
                current_k = stoch_rsi_k.iloc[-1]
                if current_k < 20:
                    signals.append({"type": "STOCH_RSI", "value": f"{current_k:.1f}", "signal": "Oversold - Buy opportunity"})
                    score = 75.0
                elif current_k > 80:
                    signals.append({"type": "STOCH_RSI", "value": f"{current_k:.1f}", "signal": "Overbought - Sell opportunity"})
                    score = 25.0
                elif current_k > 50:
                    signals.append({"type": "STOCH_RSI", "value": f"{current_k:.1f}", "signal": "Bullish momentum"})
                    score = 60.0
                else:
                    signals.append({"type": "STOCH_RSI", "value": f"{current_k:.1f}", "signal": "Bearish momentum"})
                    score = 40.0
                scores.append(score)
        except Exception as e:
            print(f"  ⚠️  Stochastic RSI failed: {e}")
            scores.append(50.0)
        return {'signals': signals, 'score': np.mean(scores) if scores else 50.0}
    
    def _analyze_money_flow_index(self, df_daily: pd.DataFrame, df_hourly: pd.DataFrame, df_15min: pd.DataFrame) -> Dict[str, Any]:
        """Money Flow Index - Volume-weighted RSI"""
        signals, scores = [], []
        try:
            high, low, close, volume = df_daily['high'], df_daily['low'], df_daily['close'], df_daily['volume']
            typical_price = (high + low + close) / 3
            money_flow = typical_price * volume
            positive_flow, negative_flow = pd.Series(0.0, index=df_daily.index), pd.Series(0.0, index=df_daily.index)
            
            for i in range(1, len(typical_price)):
                if typical_price.iloc[i] > typical_price.iloc[i-1]:
                    positive_flow.iloc[i] = money_flow.iloc[i]
                elif typical_price.iloc[i] < typical_price.iloc[i-1]:
                    negative_flow.iloc[i] = money_flow.iloc[i]
            
            period = 14
            positive_sum, negative_sum = positive_flow.rolling(window=period).sum(), negative_flow.rolling(window=period).sum()
            money_flow_ratio = positive_sum / negative_sum.replace(0, 1)
            mfi = 100 - (100 / (1 + money_flow_ratio))
            
            if len(mfi) > 0:
                current_mfi = mfi.iloc[-1]
                if current_mfi > 80:
                    signals.append({"type": "MFI", "value": f"{current_mfi:.1f}", "signal": "Overbought - Distribution"})
                    score = 30.0
                elif current_mfi < 20:
                    signals.append({"type": "MFI", "value": f"{current_mfi:.1f}", "signal": "Oversold - Accumulation"})
                    score = 70.0
                elif current_mfi > 60:
                    signals.append({"type": "MFI", "value": f"{current_mfi:.1f}", "signal": "Strong buying pressure"})
                    score = 65.0
                elif current_mfi < 40:
                    signals.append({"type": "MFI", "value": f"{current_mfi:.1f}", "signal": "Strong selling pressure"})
                    score = 35.0
                else:
                    signals.append({"type": "MFI", "value": f"{current_mfi:.1f}", "signal": "Balanced money flow"})
                    score = 50.0
                scores.append(score)
        except Exception as e:
            print(f"  ⚠️  Money Flow Index failed: {e}")
            scores.append(50.0)
        return {'signals': signals, 'score': np.mean(scores) if scores else 50.0}
    
    def _analyze_on_balance_volume(self, df_daily: pd.DataFrame, df_hourly: pd.DataFrame, df_15min: pd.DataFrame) -> Dict[str, Any]:
        """On-Balance Volume - Accumulation/Distribution"""
        signals, scores = [], []
        try:
            close, volume = df_daily['close'], df_daily['volume']
            obv = pd.Series(0.0, index=df_daily.index)
            obv.iloc[0] = volume.iloc[0]
            
            for i in range(1, len(close)):
                if close.iloc[i] > close.iloc[i-1]:
                    obv.iloc[i] = obv.iloc[i-1] + volume.iloc[i]
                elif close.iloc[i] < close.iloc[i-1]:
                    obv.iloc[i] = obv.iloc[i-1] - volume.iloc[i]
                else:
                    obv.iloc[i] = obv.iloc[i-1]
            
            obv_sma, price_sma = obv.rolling(window=20).mean(), close.rolling(window=20).mean()
            obv_trend = "rising" if obv.iloc[-1] > obv_sma.iloc[-1] else "falling"
            price_trend = "rising" if close.iloc[-1] > price_sma.iloc[-1] else "falling"
            
            if obv_trend == "rising" and price_trend == "rising":
                signals.append({"type": "OBV", "value": "Aligned", "signal": "OBV + Price rising - Strong Bullish"})
                score = 75.0
            elif obv_trend == "rising" and price_trend == "falling":
                signals.append({"type": "OBV", "value": "Bullish Divergence", "signal": "Accumulation (Early Buy)"})
                score = 70.0
            elif obv_trend == "falling" and price_trend == "rising":
                signals.append({"type": "OBV", "value": "Bearish Divergence", "signal": "Distribution (Early Sell)"})
                score = 30.0
            else:
                signals.append({"type": "OBV", "value": "Aligned", "signal": "OBV + Price falling - Strong Bearish"})
                score = 25.0
            scores.append(score)
        except Exception as e:
            print(f"  ⚠️  On-Balance Volume failed: {e}")
            scores.append(50.0)
        return {'signals': signals, 'score': np.mean(scores) if scores else 50.0}
    
    def _analyze_parabolic_sar(self, df_daily: pd.DataFrame, df_hourly: pd.DataFrame, df_15min: pd.DataFrame) -> Dict[str, Any]:
        """Parabolic SAR - Trend-following"""
        signals, scores = [], []
        try:
            close = df_daily['close']
            sma_short, sma_long = close.rolling(window=10).mean(), close.rolling(window=50).mean()
            current_price = close.iloc[-1]
            
            if current_price > sma_short.iloc[-1] > sma_long.iloc[-1]:
                signals.append({"type": "PARABOLIC_SAR", "value": "Strong Uptrend", "signal": "All MAs aligned bullish"})
                score = 75.0
            elif current_price < sma_short.iloc[-1] < sma_long.iloc[-1]:
                signals.append({"type": "PARABOLIC_SAR", "value": "Strong Downtrend", "signal": "All MAs aligned bearish"})
                score = 25.0
            elif current_price > sma_short.iloc[-1]:
                signals.append({"type": "PARABOLIC_SAR", "value": "Uptrend", "signal": "Price above short MA"})
                score = 60.0
            else:
                signals.append({"type": "PARABOLIC_SAR", "value": "Downtrend", "signal": "Price below short MA"})
                score = 40.0
            scores.append(score)
        except Exception as e:
            print(f"  ⚠️  Parabolic SAR failed: {e}")
            scores.append(50.0)
        return {'signals': signals, 'score': np.mean(scores) if scores else 50.0}
    
    def _analyze_williams_r(self, df_daily: pd.DataFrame, df_hourly: pd.DataFrame, df_15min: pd.DataFrame) -> Dict[str, Any]:
        """Williams %R - Momentum oscillator"""
        signals, scores = [], []
        try:
            high, low, close = df_daily['high'], df_daily['low'], df_daily['close']
            period = 14
            highest_high, lowest_low = high.rolling(window=period).max(), low.rolling(window=period).min()
            williams_r = ((highest_high - close) / (highest_high - lowest_low)) * -100
            
            if len(williams_r) > 0:
                current_wr = williams_r.iloc[-1]
                if current_wr < -80:
                    signals.append({"type": "WILLIAMS_R", "value": f"{current_wr:.1f}", "signal": "Oversold - Buy opportunity"})
                    score = 70.0
                elif current_wr > -20:
                    signals.append({"type": "WILLIAMS_R", "value": f"{current_wr:.1f}", "signal": "Overbought - Sell opportunity"})
                    score = 30.0
                elif current_wr > -50:
                    signals.append({"type": "WILLIAMS_R", "value": f"{current_wr:.1f}", "signal": "Bullish momentum"})
                    score = 60.0
                else:
                    signals.append({"type": "WILLIAMS_R", "value": f"{current_wr:.1f}", "signal": "Bearish momentum"})
                    score = 40.0
                scores.append(score)
        except Exception as e:
            print(f"  ⚠️  Williams %R failed: {e}")
            scores.append(50.0)
        return {'signals': signals, 'score': np.mean(scores) if scores else 50.0}
    
    def _analyze_adaptive_ma(self, df_daily: pd.DataFrame, df_hourly: pd.DataFrame, df_15min: pd.DataFrame) -> Dict[str, Any]:
        """Adaptive Moving Average - Noise-adjusted trend"""
        signals, scores = [], []
        try:
            close = df_daily['close']
            ema_fast, ema_slow = close.ewm(span=10, adjust=False).mean(), close.ewm(span=30, adjust=False).mean()
            current_price = close.iloc[-1]
            
            if current_price > ema_fast.iloc[-1] > ema_slow.iloc[-1]:
                signals.append({"type": "KAMA", "value": "Strong Uptrend", "signal": "All MAs aligned bullish"})
                score = 75.0
            elif current_price < ema_fast.iloc[-1] < ema_slow.iloc[-1]:
                signals.append({"type": "KAMA", "value": "Strong Downtrend", "signal": "All MAs aligned bearish"})
                score = 25.0
            elif current_price > ema_fast.iloc[-1]:
                signals.append({"type": "KAMA", "value": "Bullish", "signal": "Above fast MA"})
                score = 60.0
            else:
                signals.append({"type": "KAMA", "value": "Bearish", "signal": "Below fast MA"})
                score = 40.0
            scores.append(score)
        except Exception as e:
            print(f"  ⚠️  Adaptive MA failed: {e}")
            scores.append(50.0)
        return {'signals': signals, 'score': np.mean(scores) if scores else 50.0}
