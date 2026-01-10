"""
Pattern Recognition Agent - Phase 1 Complete
Detects 27+ technical chart patterns for trading signals (125% increase)

Original Patterns (12):
- Reversal: Head & Shoulders, Inverse H&S, Double Top/Bottom, Cup & Handle
- Continuation: Triangles, Flags, Pennants, Rectangles
- Candlesticks: Doji, Hammer, Shooting Star, Engulfing

Phase 1 Enhancements (15 new patterns):

Advanced Candlestick Patterns (5):
1. Three White Soldiers / Three Black Crows - Strong trend reversal
2. Morning Star / Evening Star - Reversal at extremes
3. Bullish/Bearish Harami - Trend exhaustion
4. Piercing Pattern / Dark Cloud Cover - Reversal confirmation
5. Tweezer Tops / Bottoms - Support/resistance rejection

Volume-Based Patterns (5):
6. Climax Volume Reversal - Exhaustion with 3x volume
7. Volume Breakout/Breakdown - 2x volume confirmation
8. Volume Dry-Up - Low volume before breakout
9. Accumulation/Distribution Zones - Smart money detection
10. Volume Profile Analysis - High volume nodes as S/R

Harmonic Patterns (5):
11. Gartley Pattern - 78.6% Fibonacci reversal
12. Butterfly Pattern - 127.2% extension reversal
13. Bat Pattern - 88.6% precise reversal
14. Crab Pattern - 161.8% extreme reversal
15. AB=CD Pattern - Equal legs harmonic
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

from .base import BaseAgent, AgentResult


class PatternRecognitionAgent(BaseAgent):
    """
    Advanced pattern recognition using price action and volume analysis
    """
    
    def __init__(self, weight: float = 0.18):
        super().__init__(name="pattern_recognition", weight=weight)
        self.min_candles = 50  # Minimum candles needed for pattern detection
    
    async def analyze(
        self,
        symbol: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Analyze chart patterns and generate trading signals
        
        Args:
            symbol: Stock symbol
            context: Market data including candles, current_price, etc.
            
        Returns:
            Analysis with detected patterns, score, and signal
        """
        context = context or {}
        debug_mode = bool(context.get('debug_mode'))
        
        # Extract candles from context
        candles = context.get('candles')
        current_price = context.get('current_price', 0)
        
        # If no candles in context, fetch them
        if candles is None or len(candles) == 0:
            # Try to get from chart data service
            # Use 1Y timeframe to get enough data for pattern recognition (50+ candles)
            try:
                from ..services.chart_data_service import chart_data_service
                chart_data = await chart_data_service.fetch_chart_data(symbol, '1Y')
                if chart_data and 'candles' in chart_data:
                    candles = pd.DataFrame(chart_data['candles'])
                    current_price = chart_data.get('current', {}).get('price', current_price)
                else:
                    return self._insufficient_data_response(0)
            except Exception as e:
                print(f"  Pattern Recognition: Could not fetch candles: {e}")
                return self._insufficient_data_response(0)
        
        # Convert to DataFrame if it's a list of dicts
        if isinstance(candles, list):
            candles = pd.DataFrame(candles)
        
        if len(candles) < self.min_candles:
            return self._insufficient_data_response(len(candles))
        
        # Detect all patterns
        patterns = []
        
        # Reversal Patterns (Original)
        patterns.extend(self._detect_head_and_shoulders(candles))
        patterns.extend(self._detect_double_top_bottom(candles))
        patterns.extend(self._detect_triple_top_bottom(candles))
        patterns.extend(self._detect_cup_and_handle(candles))
        
        # Continuation Patterns (Original)
        patterns.extend(self._detect_triangles(candles))
        patterns.extend(self._detect_flags_pennants(candles))
        patterns.extend(self._detect_rectangles(candles))

        # Structural Patterns (Wedges, Rounding, Channels, Gaps/Islands)
        patterns.extend(self._detect_wedges(candles))
        patterns.extend(self._detect_rounding_patterns(candles))
        patterns.extend(self._detect_channels(candles))
        patterns.extend(self._detect_gaps_islands(candles))
        
        # Candlestick Patterns (Original)
        patterns.extend(self._detect_candlestick_patterns(candles))
        
        # Phase 1 Enhancements - Advanced Candlestick Patterns (5)
        patterns.extend(self._detect_three_soldiers_crows(candles))
        patterns.extend(self._detect_morning_evening_star(candles))
        patterns.extend(self._detect_harami(candles))
        patterns.extend(self._detect_piercing_dark_cloud(candles))
        patterns.extend(self._detect_tweezer_tops_bottoms(candles))
        
        # Phase 1 Enhancements - Volume-Based Patterns (5)
        patterns.extend(self._detect_climax_volume(candles))
        patterns.extend(self._detect_volume_breakout(candles))
        patterns.extend(self._detect_volume_dryup(candles))
        patterns.extend(self._detect_accumulation_distribution(candles))
        patterns.extend(self._detect_volume_profile(candles))
        
        # Phase 1 Enhancements - Harmonic Patterns (5)
        patterns.extend(self._detect_gartley(candles))
        patterns.extend(self._detect_butterfly(candles))
        patterns.extend(self._detect_bat(candles))
        patterns.extend(self._detect_crab(candles))
        patterns.extend(self._detect_abcd(candles))
        
        # Sort by confidence
        patterns = sorted(patterns, key=lambda x: x['confidence'], reverse=True)
        
        # Build a de-duplicated view by pattern name for presentation, so that
        # repeated occurrences of the same pattern (e.g. multiple Three Black
        # Crows instances) don't crowd out other meaningful patterns.
        patterns_unique: List[Dict] = []
        seen_names: set = set()
        for p in patterns:
            name = p.get('name')
            if name in seen_names:
                continue
            seen_names.add(name)
            patterns_unique.append(p)
        
        # Calculate overall score and signal using the full pattern list so that
        # duplicates still contribute appropriately to the weighting logic.
        score, signal = self._calculate_score_and_signal(patterns, current_price)
        
        # Generate reasoning
        reasoning = self._generate_reasoning(patterns, signal)
        
        # Get key signals from the top 3 unique patterns
        key_signals = self._extract_key_signals(patterns_unique[:3])  # Top 3 unique patterns
        
        # Determine confidence
        confidence = "High" if score >= 70 else "Medium" if score >= 50 else "Low"
        
        # Format signals for AgentResult based on unique patterns
        formatted_signals = []
        for pattern in patterns_unique[:5]:
            formatted_signals.append({
                "type": pattern['name'],
                "direction": pattern.get('type', 'NEUTRAL'),
                "confidence": pattern.get('confidence', 0),
                "description": pattern.get('description', '')
            })

        metadata: Dict[str, Any] = {
            "total_patterns": len(patterns),
            "bullish_count": len([p for p in patterns if p.get('type') == 'BULLISH']),
            "bearish_count": len([p for p in patterns if p.get('type') == 'BEARISH']),
            "strongest_pattern": patterns[0]['name'] if patterns else None,
            # Top 5 unique patterns with all details (presentation only)
            "patterns_detail": patterns_unique[:5],
            "key_signals": key_signals,
        }

        if debug_mode:
            from collections import Counter
            name_counts = Counter(p.get('name', 'UNKNOWN') for p in patterns)
            metadata["patterns_by_name"] = dict(name_counts)
        
        return AgentResult(
            agent_type=self.name,
            symbol=symbol,
            score=float(score),
            confidence=confidence,
            signals=formatted_signals,
            reasoning=reasoning,
            metadata=metadata,
        )
    
    # ==================== Pattern Detection Methods ====================
    
    def _detect_head_and_shoulders(self, df: pd.DataFrame) -> List[Dict]:
        """Detect Head & Shoulders (bearish) and Inverse H&S (bullish)"""
        patterns = []
        
        # Need at least 30 candles for H&S
        if len(df) < 30:
            return patterns
        
        # Use last 50 candles for pattern detection
        data = df.tail(50).copy()
        data['high_roll'] = data['high'].rolling(window=5).max()
        data['low_roll'] = data['low'].rolling(window=5).min()
        
        # Bearish H&S: Three peaks, middle one highest
        peaks = self._find_peaks(data['high'].values, distance=5)
        
        if len(peaks) >= 3:
            # Check last 3 peaks
            peak_prices = data['high'].iloc[peaks[-3:]].values
            
            # Head should be higher than both shoulders
            if peak_prices[1] > peak_prices[0] and peak_prices[1] > peak_prices[2]:
                # Check if shoulders are relatively equal (within 5%)
                shoulder_ratio = abs(peak_prices[0] - peak_prices[2]) / peak_prices[0]
                
                if shoulder_ratio < 0.05:
                    # Find neckline (support connecting the troughs)
                    troughs = self._find_troughs(data['low'].values, distance=5)
                    
                    if len(troughs) >= 2:
                        neckline = (data['low'].iloc[troughs[-2]] + data['low'].iloc[troughs[-1]]) / 2
                        current_price = data['close'].iloc[-1]
                        
                        # Pattern valid if price hasn't broken neckline significantly
                        if current_price > neckline * 0.97:
                            target = neckline - (peak_prices[1] - neckline)
                            
                            patterns.append({
                                "name": "Head & Shoulders",
                                "type": "BEARISH",
                                "confidence": 75 + (shoulder_ratio * 100),  # Better symmetry = higher confidence
                                "target": round(target, 2),
                                "neckline": round(neckline, 2),
                                "status": "FORMING" if current_price > neckline else "CONFIRMED",
                                "description": f"Bearish H&S pattern with neckline at {neckline:.2f}"
                            })
        
        # Inverse H&S (bullish): Three troughs, middle one lowest
        troughs = self._find_troughs(data['low'].values, distance=5)
        
        if len(troughs) >= 3:
            trough_prices = data['low'].iloc[troughs[-3:]].values
            
            # Head (middle trough) should be lower than both shoulders
            if trough_prices[1] < trough_prices[0] and trough_prices[1] < trough_prices[2]:
                shoulder_ratio = abs(trough_prices[0] - trough_prices[2]) / trough_prices[0]
                
                if shoulder_ratio < 0.05:
                    peaks = self._find_peaks(data['high'].values, distance=5)
                    
                    if len(peaks) >= 2:
                        neckline = (data['high'].iloc[peaks[-2]] + data['high'].iloc[peaks[-1]]) / 2
                        current_price = data['close'].iloc[-1]
                        
                        if current_price < neckline * 1.03:
                            target = neckline + (neckline - trough_prices[1])
                            
                            patterns.append({
                                "name": "Inverse Head & Shoulders",
                                "type": "BULLISH",
                                "confidence": 75 + (shoulder_ratio * 100),
                                "target": round(target, 2),
                                "neckline": round(neckline, 2),
                                "status": "FORMING" if current_price < neckline else "CONFIRMED",
                                "description": f"Bullish inverse H&S with neckline at {neckline:.2f}"
                            })
        
        return patterns
    
    def _detect_wedges(self, df: pd.DataFrame) -> List[Dict]:
        """Detect Rising Wedge (bearish) and Falling Wedge (bullish) patterns"""
        patterns: List[Dict] = []

        # Need a decent window for trendline estimation
        if len(df) < 40:
            return patterns

        # Use last 60 candles for wedge detection
        data = df.tail(60).copy()
        if len(data) < 20:
            return patterns

        # Focus analysis on last N candles
        N = min(40, len(data))
        segment = data.tail(N)
        highs = segment['high'].values
        lows = segment['low'].values

        # Basic safety checks
        if len(highs) < 10 or len(lows) < 10:
            return patterns

        resistance_slope = self._calculate_slope(highs)
        support_slope = self._calculate_slope(lows)

        # Check for contracting price range between first and second half
        first_half = segment.head(N // 2)
        second_half = segment.tail(N // 2)
        if len(first_half) < 5 or len(second_half) < 5:
            return patterns

        range1 = first_half['high'].max() - first_half['low'].min()
        range2 = second_half['high'].max() - second_half['low'].min()
        if range1 <= 0 or range2 <= 0:
            return patterns

        is_contracting = range2 < range1 * 0.9

        # Require multiple swings to avoid random noise
        peaks = self._find_peaks(highs, distance=3)
        troughs = self._find_troughs(lows, distance=3)
        if len(peaks) < 3 or len(troughs) < 3:
            return patterns

        current_price = float(segment['close'].iloc[-1])
        recent_highs = segment['high'].tail(5).values
        recent_lows = segment['low'].tail(5).values
        resistance_level = float(np.mean(recent_highs))
        support_level = float(np.mean(recent_lows))

        # Rising Wedge: both trendlines up, but support steeper than resistance
        if (
            is_contracting
            and resistance_slope > 0
            and support_slope > 0
            and support_slope > resistance_slope * 1.2
        ):
            status = "FORMING"
            if current_price < support_level * 0.99:
                status = "CONFIRMED"

            confidence = 70.0
            # Increase confidence for clean breakdown
            if status == "CONFIRMED":
                confidence += 5.0

            patterns.append({
                "name": "Rising Wedge",
                "type": "BEARISH",
                "confidence": round(confidence, 1),
                "support": round(support_level, 2),
                "resistance": round(resistance_level, 2),
                "status": status,
                "description": f"Rising wedge after advance with contracting range; support near {support_level:.2f}",
                "label": "Rising Wedge breakdown" if status == "CONFIRMED" else "Rising Wedge (forming)",
            })

        # Falling Wedge: both trendlines down, but resistance steeper than support
        if (
            is_contracting
            and resistance_slope < 0
            and support_slope < 0
            and abs(resistance_slope) > abs(support_slope) * 1.2
        ):
            status = "FORMING"
            if current_price > resistance_level * 1.01:
                status = "CONFIRMED"

            confidence = 70.0
            if status == "CONFIRMED":
                confidence += 5.0

            patterns.append({
                "name": "Falling Wedge",
                "type": "BULLISH",
                "confidence": round(confidence, 1),
                "support": round(support_level, 2),
                "resistance": round(resistance_level, 2),
                "status": status,
                "description": f"Falling wedge within downtrend; resistance near {resistance_level:.2f}",
                "label": "Falling Wedge breakout" if status == "CONFIRMED" else "Falling Wedge (forming)",
            })

        return patterns
    
    def _detect_double_top_bottom(self, df: pd.DataFrame) -> List[Dict]:
        """Detect Double Top (bearish) and Double Bottom (bullish)"""
        patterns = []
        
        if len(df) < 20:
            return patterns
        
        data = df.tail(40).copy()
        
        # Double Top: Two peaks at similar levels
        peaks = self._find_peaks(data['high'].values, distance=5)
        
        if len(peaks) >= 2:
            peak1_price = data['high'].iloc[peaks[-2]]
            peak2_price = data['high'].iloc[peaks[-1]]
            
            # Peaks should be within 3% of each other
            price_diff = abs(peak1_price - peak2_price) / peak1_price
            
            if price_diff < 0.03:
                # Find trough between peaks
                trough_idx = data['low'].iloc[peaks[-2]:peaks[-1]].idxmin()
                trough_price = data.loc[trough_idx, 'low']
                
                current_price = data['close'].iloc[-1]
                
                # Target is trough level
                target = trough_price
                
                patterns.append({
                    "name": "Double Top",
                    "type": "BEARISH",
                    "confidence": 70 - (price_diff * 1000),  # Closer peaks = higher confidence
                    "target": round(target, 2),
                    "resistance": round((peak1_price + peak2_price) / 2, 2),
                    "status": "FORMING" if current_price > trough_price else "CONFIRMED",
                    "description": f"Double top at {peak1_price:.2f}, target {target:.2f}"
                })
        
        # Double Bottom: Two troughs at similar levels
        troughs = self._find_troughs(data['low'].values, distance=5)
        
        if len(troughs) >= 2:
            trough1_price = data['low'].iloc[troughs[-2]]
            trough2_price = data['low'].iloc[troughs[-1]]
            
            price_diff = abs(trough1_price - trough2_price) / trough1_price
            
            if price_diff < 0.03:
                # Find peak between troughs
                peak_idx = data['high'].iloc[troughs[-2]:troughs[-1]].idxmax()
                peak_price = data.loc[peak_idx, 'high']
                
                current_price = data['close'].iloc[-1]
                target = peak_price
                
                patterns.append({
                    "name": "Double Bottom",
                    "type": "BULLISH",
                    "confidence": 70 - (price_diff * 1000),
                    "target": round(target, 2),
                    "support": round((trough1_price + trough2_price) / 2, 2),
                    "status": "FORMING" if current_price < peak_price else "CONFIRMED",
                    "description": f"Double bottom at {trough1_price:.2f}, target {target:.2f}"
                })
        
        return patterns

    def _detect_triple_top_bottom(self, df: pd.DataFrame) -> List[Dict]:
        """Detect Triple Top (bearish) and Triple Bottom (bullish)"""
        patterns: List[Dict] = []

        # Need a bit more history to confirm three swings
        if len(df) < 30:
            return patterns

        data = df.tail(60).copy()

        # Triple Top: Three peaks at similar levels with pullbacks in between
        peaks = self._find_peaks(data['high'].values, distance=5)
        if len(peaks) >= 3:
            last_three = peaks[-3:]
            peak_prices = data['high'].iloc[last_three].values
            avg_peak = float(np.mean(peak_prices)) if len(peak_prices) > 0 else 0.0

            if avg_peak > 0:
                max_dev = max(abs(p - avg_peak) / avg_peak for p in peak_prices)
            else:
                max_dev = 1.0

            # Require reasonably flat resistance (within ~3%)
            if max_dev < 0.03:
                # Neckline from lows between peaks
                segment1_lows = data['low'].iloc[last_three[0]:last_three[1]]
                segment2_lows = data['low'].iloc[last_three[1]:last_three[2]]

                if not segment1_lows.empty and not segment2_lows.empty:
                    trough1 = float(segment1_lows.min())
                    trough2 = float(segment2_lows.min())
                    neckline = (trough1 + trough2) / 2.0

                    current_price = float(data['close'].iloc[-1])
                    status = "FORMING" if current_price > neckline else "CONFIRMED"

                    # Slightly higher base confidence than double top
                    confidence = 75.0 - (max_dev * 1000)

                    patterns.append({
                        "name": "Triple Top",
                        "type": "BEARISH",
                        "confidence": round(confidence, 1),
                        "target": round(neckline, 2),
                        "resistance": round(avg_peak, 2),
                        "status": status,
                        "description": f"Triple top near {avg_peak:.2f}, neckline around {neckline:.2f}",
                    })

        # Triple Bottom: Three troughs at similar levels with rallies in between
        troughs = self._find_troughs(data['low'].values, distance=5)
        if len(troughs) >= 3:
            last_three = troughs[-3:]
            trough_prices = data['low'].iloc[last_three].values
            avg_trough = float(np.mean(trough_prices)) if len(trough_prices) > 0 else 0.0

            if avg_trough > 0:
                max_dev = max(abs(t - avg_trough) / avg_trough for t in trough_prices)
            else:
                max_dev = 1.0

            if max_dev < 0.03:
                # Neckline from highs between troughs
                segment1_highs = data['high'].iloc[last_three[0]:last_three[1]]
                segment2_highs = data['high'].iloc[last_three[1]:last_three[2]]

                if not segment1_highs.empty and not segment2_highs.empty:
                    peak1 = float(segment1_highs.max())
                    peak2 = float(segment2_highs.max())
                    neckline = (peak1 + peak2) / 2.0

                    current_price = float(data['close'].iloc[-1])
                    status = "FORMING" if current_price < neckline else "CONFIRMED"

                    confidence = 75.0 - (max_dev * 1000)

                    patterns.append({
                        "name": "Triple Bottom",
                        "type": "BULLISH",
                        "confidence": round(confidence, 1),
                        "target": round(neckline, 2),
                        "support": round(avg_trough, 2),
                        "status": status,
                        "description": f"Triple bottom near {avg_trough:.2f}, neckline around {neckline:.2f}",
                    })

        return patterns

    def _detect_rounding_patterns(self, df: pd.DataFrame) -> List[Dict]:
        patterns: List[Dict] = []

        if len(df) < 40:
            return patterns

        data = df.tail(120).copy()
        if len(data) < 40:
            return patterns

        smooth = data['close'].rolling(window=5, min_periods=3).mean().dropna()
        if len(smooth) < 30:
            return patterns

        s = smooth.values
        n = len(s)
        mid = n // 2

        # Rounding Top: edges lower, center higher, left slope up, right slope down
        idx_top = int(np.argmax(s))
        top_price = float(s[idx_top])
        edge_min = float(min(s[0], s[-1]))

        if edge_min > 0:
            top_amplitude = (top_price - edge_min) / edge_min
        else:
            top_amplitude = 0.0

        if (
            0.3 * n <= idx_top <= 0.7 * n
            and top_amplitude >= 0.10
        ):
            left_slope = self._calculate_slope(s[:mid]) if mid > 2 else 0.0
            right_slope = self._calculate_slope(s[mid:]) if n - mid > 2 else 0.0

            if left_slope > 0 and right_slope < 0:
                current_price = float(data['close'].iloc[-1])
                base_level = edge_min
                midpoint = base_level + (top_price - base_level) * 0.5
                status = "FORMING" if current_price > midpoint else "CONFIRMED"

                confidence = 70.0 + min(top_amplitude * 50, 5.0)

                patterns.append({
                    "name": "Rounding Top",
                    "type": "BEARISH",
                    "confidence": round(confidence, 1),
                    "resistance": round(top_price, 2),
                    "status": status,
                    "description": f"Rounding top with resistance near {top_price:.2f}",
                })

        # Rounding Bottom: edges higher, center lower, left slope down, right slope up
        idx_bottom = int(np.argmin(s))
        bottom_price = float(s[idx_bottom])
        edge_max = float(max(s[0], s[-1]))

        if edge_max > 0:
            bottom_amplitude = (edge_max - bottom_price) / edge_max
        else:
            bottom_amplitude = 0.0

        if (
            0.3 * n <= idx_bottom <= 0.7 * n
            and bottom_amplitude >= 0.10
        ):
            left_slope_b = self._calculate_slope(s[:mid]) if mid > 2 else 0.0
            right_slope_b = self._calculate_slope(s[mid:]) if n - mid > 2 else 0.0

            if left_slope_b < 0 and right_slope_b > 0:
                current_price = float(data['close'].iloc[-1])
                base_level = bottom_price
                top_level = edge_max
                midpoint = base_level + (top_level - base_level) * 0.5
                status = "FORMING" if current_price < midpoint else "CONFIRMED"

                confidence = 70.0 + min(bottom_amplitude * 50, 5.0)

                patterns.append({
                    "name": "Rounding Bottom",
                    "type": "BULLISH",
                    "confidence": round(confidence, 1),
                    "support": round(bottom_price, 2),
                    "status": status,
                    "description": f"Rounding bottom with support near {bottom_price:.2f}",
                })

        return patterns

    def _detect_channels(self, df: pd.DataFrame) -> List[Dict]:
        patterns: List[Dict] = []

        if len(df) < 40:
            return patterns

        data = df.tail(80).copy()
        if len(data) < 40:
            return patterns

        highs = data['high'].values
        lows = data['low'].values
        closes = data['close'].values

        length = min(40, len(data))
        h_seg = highs[-length:]
        l_seg = lows[-length:]
        c_seg = closes[-length:]

        resistance_slope = self._calculate_slope(h_seg)
        support_slope = self._calculate_slope(l_seg)

        hi_max = float(h_seg.max())
        lo_min = float(l_seg.min())
        if lo_min <= 0:
            return patterns

        width = hi_max - lo_min
        if width <= 0:
            return patterns

        rel_width = width / lo_min
        if not (0.03 <= rel_width <= 0.30):
            return patterns

        norm_pos = (c_seg - lo_min) / width
        touches_top = int((norm_pos > 0.8).sum())
        touches_bottom = int((norm_pos < 0.2).sum())

        if touches_top < 3 or touches_bottom < 3:
            return patterns

        slope_ratio = 0.0
        if resistance_slope != 0 and support_slope != 0 and resistance_slope * support_slope > 0:
            slope_ratio = abs(resistance_slope / support_slope)

        # Rising Channel: both trendlines up, roughly parallel
        if (
            resistance_slope > 0.002
            and support_slope > 0.002
            and 0.7 <= slope_ratio <= 1.3
        ):
            conf = 60.0 + min(min(touches_top, touches_bottom) * 2.0, 6.0)
            patterns.append({
                "name": "Rising Channel",
                "type": "BULLISH",
                "confidence": round(conf, 1),
                "support": round(lo_min, 2),
                "resistance": round(hi_max, 2),
                "status": "ACTIVE",
                "description": f"Price oscillating in rising channel between {lo_min:.2f} and {hi_max:.2f}",
            })

        # Falling Channel: both trendlines down, roughly parallel
        if (
            resistance_slope < -0.002
            and support_slope < -0.002
            and 0.7 <= slope_ratio <= 1.3
        ):
            conf = 60.0 + min(min(touches_top, touches_bottom) * 2.0, 6.0)
            patterns.append({
                "name": "Falling Channel",
                "type": "BEARISH",
                "confidence": round(conf, 1),
                "support": round(lo_min, 2),
                "resistance": round(hi_max, 2),
                "status": "ACTIVE",
                "description": f"Price oscillating in falling channel between {lo_min:.2f} and {hi_max:.2f}",
            })

        return patterns

    def _detect_gaps_islands(self, df: pd.DataFrame) -> List[Dict]:
        patterns: List[Dict] = []

        if len(df) < 10:
            return patterns

        data = df.tail(60).copy()
        if len(data) < 10:
            return patterns

        highs = data['high'].values
        lows = data['low'].values
        opens = data['open'].values
        closes = data['close'].values

        gap_up_idx: List[int] = []
        gap_down_idx: List[int] = []

        for i in range(1, len(data)):
            prev_high = highs[i - 1]
            prev_low = lows[i - 1]
            cur_low = lows[i]
            cur_high = highs[i]

            if prev_high <= 0 or prev_low <= 0:
                continue

            # Significant gap up
            if cur_low > prev_high * 1.015:
                gap_up_idx.append(i)

            # Significant gap down
            if cur_high < prev_low * 0.985:
                gap_down_idx.append(i)

        # Last gap up
        if gap_up_idx:
            i = gap_up_idx[-1]
            prev_high = highs[i - 1]
            cur_low = lows[i]
            gap_pct = (cur_low - prev_high) / prev_high if prev_high > 0 else 0.0
            level = float(opens[i])
            conf = 65.0 + min(gap_pct * 200, 5.0)
            patterns.append({
                "name": "Gap Up",
                "type": "BULLISH",
                "confidence": round(conf, 1),
                "status": "ACTIVE",
                "description": f"Gap up of {gap_pct*100:.1f}% near {level:.2f}",
            })

        # Last gap down
        if gap_down_idx:
            i = gap_down_idx[-1]
            prev_low = lows[i - 1]
            cur_high = highs[i]
            gap_pct = (prev_low - cur_high) / prev_low if prev_low > 0 else 0.0
            level = float(opens[i])
            conf = 65.0 + min(gap_pct * 200, 5.0)
            patterns.append({
                "name": "Gap Down",
                "type": "BEARISH",
                "confidence": round(conf, 1),
                "status": "ACTIVE",
                "description": f"Gap down of {gap_pct*100:.1f}% near {level:.2f}",
            })

        # Simple island reversals: gap one way then opposite gap next bar
        for i in range(1, len(data) - 1):
            prev_high = highs[i - 1]
            prev_low = lows[i - 1]
            cur_low = lows[i]
            cur_high = highs[i]
            next_low = lows[i + 1]
            next_high = highs[i + 1]

            if prev_high <= 0 or prev_low <= 0:
                continue

            # Bearish island top: gap up then gap down
            is_gap_up = cur_low > prev_high * 1.015
            is_gap_down_next = next_high < cur_low * 0.985
            if is_gap_up and is_gap_down_next:
                level = float(closes[i])
                patterns.append({
                    "name": "Bearish Island Reversal",
                    "type": "BEARISH",
                    "confidence": 75.0,
                    "status": "ACTIVE",
                    "description": f"Bearish island reversal near {level:.2f}",
                })

            # Bullish island bottom: gap down then gap up
            is_gap_down = cur_high < prev_low * 0.985
            is_gap_up_next = next_low > cur_high * 1.015
            if is_gap_down and is_gap_up_next:
                level = float(closes[i])
                patterns.append({
                    "name": "Bullish Island Reversal",
                    "type": "BULLISH",
                    "confidence": 75.0,
                    "status": "ACTIVE",
                    "description": f"Bullish island reversal near {level:.2f}",
                })

        return patterns

    def _detect_cup_and_handle(self, df: pd.DataFrame) -> List[Dict]:
        """Detect Cup and Handle pattern (bullish)"""
        patterns = []
        
        if len(df) < 30:
            return patterns
        
        data = df.tail(60).copy()
        
        # Cup: U-shaped recovery
        # Handle: Small consolidation near cup rim
        
        # Find the cup
        mid_point = len(data) // 2
        first_half = data.iloc[:mid_point]
        second_half = data.iloc[mid_point:]
        
        # Cup bottom should be in first half
        cup_bottom_idx = first_half['low'].idxmin()
        cup_bottom = first_half.loc[cup_bottom_idx, 'low']
        
        # Cup rim (peak before bottom)
        cup_left_rim = first_half['high'].iloc[:first_half.index.get_loc(cup_bottom_idx)].max()
        
        # Price should recover to near cup rim
        cup_right_rim = second_half['high'].max()
        
        # Rims should be similar (within 5%)
        rim_diff = abs(cup_left_rim - cup_right_rim) / cup_left_rim
        
        if rim_diff < 0.05:
            # Depth check: Cup should be at least 10% deep
            cup_depth = (cup_left_rim - cup_bottom) / cup_left_rim
            
            if cup_depth > 0.10 and cup_depth < 0.40:
                # Look for handle in last 10-15 candles
                handle_data = data.tail(15)
                handle_low = handle_data['low'].min()
                handle_high = handle_data['high'].max()
                
                # Handle should be shallow (< 15% of cup depth)
                handle_depth = (handle_high - handle_low) / handle_high
                
                if handle_depth < 0.15:
                    target = cup_right_rim + (cup_left_rim - cup_bottom)
                    
                    patterns.append({
                        "name": "Cup and Handle",
                        "type": "BULLISH",
                        "confidence": 65 + (rim_diff * 100),
                        "target": round(target, 2),
                        "breakout_level": round(cup_right_rim, 2),
                        "status": "FORMING",
                        "description": f"Cup formed, handle consolidating. Breakout level {cup_right_rim:.2f}"
                    })
        
        return patterns
    
    def _detect_triangles(self, df: pd.DataFrame) -> List[Dict]:
        """Detect triangle patterns (ascending, descending, symmetrical)"""
        patterns = []
        
        if len(df) < 20:
            return patterns
        
        data = df.tail(30).copy()
        
        # Find trend lines
        highs = data['high'].values
        lows = data['low'].values
        
        # Ascending Triangle: Flat resistance, rising support
        resistance_slope = self._calculate_slope(highs[-10:])
        support_slope = self._calculate_slope(lows[-10:])
        
        if abs(resistance_slope) < 0.001 and support_slope > 0.002:
            resistance_level = np.mean(highs[-10:])
            target = resistance_level + (resistance_level - lows[-10])
            
            patterns.append({
                "name": "Ascending Triangle",
                "type": "BULLISH",
                "confidence": 65,
                "target": round(target, 2),
                "breakout_level": round(resistance_level, 2),
                "status": "FORMING",
                "description": f"Ascending triangle, breakout expected above {resistance_level:.2f}"
            })
        
        # Descending Triangle: Flat support, falling resistance
        if abs(support_slope) < 0.001 and resistance_slope < -0.002:
            support_level = np.mean(lows[-10:])
            target = support_level - (highs[-10] - support_level)
            
            patterns.append({
                "name": "Descending Triangle",
                "type": "BEARISH",
                "confidence": 65,
                "target": round(target, 2),
                "breakdown_level": round(support_level, 2),
                "status": "FORMING",
                "description": f"Descending triangle, breakdown expected below {support_level:.2f}"
            })
        
        return patterns
    
    def _detect_flags_pennants(self, df: pd.DataFrame) -> List[Dict]:
        """Detect flag and pennant patterns (continuation)"""
        patterns = []
        
        if len(df) < 20:
            return patterns
        
        data = df.tail(30).copy()
        
        # Flag: Consolidation after strong move
        # Check for strong prior move (pole)
        pole_start = len(data) - 20
        pole_end = len(data) - 10
        pole_move = (data['close'].iloc[pole_end] - data['close'].iloc[pole_start]) / data['close'].iloc[pole_start]
        
        # Need at least 8% move to form pole
        if abs(pole_move) > 0.08:
            # Check consolidation in last 10 candles
            consolidation = data.tail(10)
            price_range = (consolidation['high'].max() - consolidation['low'].min()) / consolidation['close'].mean()
            
            # Consolidation should be tight (< 5%)
            if price_range < 0.05:
                if pole_move > 0:
                    # Bullish flag
                    target = data['close'].iloc[-1] + abs(pole_move) * data['close'].iloc[pole_start]
                    
                    patterns.append({
                        "name": "Bull Flag",
                        "type": "BULLISH",
                        "confidence": 60,
                        "target": round(target, 2),
                        "breakout_level": round(consolidation['high'].max(), 2),
                        "status": "FORMING",
                        "description": "Bull flag forming after strong uptrend"
                    })
                else:
                    # Bearish flag
                    target = data['close'].iloc[-1] - abs(pole_move) * data['close'].iloc[pole_start]
                    
                    patterns.append({
                        "name": "Bear Flag",
                        "type": "BEARISH",
                        "confidence": 60,
                        "target": round(target, 2),
                        "breakdown_level": round(consolidation['low'].min(), 2),
                        "status": "FORMING",
                        "description": "Bear flag forming after strong downtrend"
                    })
        
        return patterns
    
    def _detect_rectangles(self, df: pd.DataFrame) -> List[Dict]:
        """Detect rectangle/range patterns"""
        patterns = []
        
        if len(df) < 15:
            return patterns
        
        data = df.tail(20).copy()
        
        # Rectangle: Price bouncing between support and resistance
        resistance = data['high'].quantile(0.95)
        support = data['low'].quantile(0.05)
        
        # Check if price is range-bound
        price_range = (resistance - support) / support
        
        # Range should be significant but not too wide (5-15%)
        if 0.05 < price_range < 0.15:
            # Count bounces
            touches_resistance = (data['high'] >= resistance * 0.99).sum()
            touches_support = (data['low'] <= support * 1.01).sum()
            
            if touches_resistance >= 2 and touches_support >= 2:
                patterns.append({
                    "name": "Rectangle/Range",
                    "type": "NEUTRAL",
                    "confidence": 55,
                    "resistance": round(resistance, 2),
                    "support": round(support, 2),
                    "status": "ACTIVE",
                    "description": f"Range-bound between {support:.2f} and {resistance:.2f}"
                })
        
        return patterns
    
    def _detect_candlestick_patterns(self, df: pd.DataFrame) -> List[Dict]:
        """Detect single and multi-candle patterns"""
        patterns = []
        
        if len(df) < 3:
            return patterns
        
        # Get last 5 candles for pattern detection
        data = df.tail(5).copy()
        
        # Calculate candle bodies and shadows
        data['body'] = abs(data['close'] - data['open'])
        data['upper_shadow'] = data['high'] - data[['open', 'close']].max(axis=1)
        data['lower_shadow'] = data[['open', 'close']].min(axis=1) - data['low']
        data['range'] = data['high'] - data['low']
        
        # Last candle
        last = data.iloc[-1]
        prev = data.iloc[-2] if len(data) > 1 else None
        
        # Doji: Small body, indicates indecision
        if last['body'] / last['range'] < 0.1 and last['range'] > 0:
            patterns.append({
                "name": "Doji",
                "type": "NEUTRAL",
                "confidence": 50,
                "description": "Indecision candle, potential reversal"
            })
        
        # Hammer: Small body at top, long lower shadow (bullish at bottom)
        if last['lower_shadow'] > last['body'] * 2 and last['upper_shadow'] < last['body']:
            patterns.append({
                "name": "Hammer",
                "type": "BULLISH",
                "confidence": 55,
                "description": "Hammer candle, potential bottom reversal"
            })
        
        # Shooting Star: Small body at bottom, long upper shadow (bearish at top)
        if last['upper_shadow'] > last['body'] * 2 and last['lower_shadow'] < last['body']:
            patterns.append({
                "name": "Shooting Star",
                "type": "BEARISH",
                "confidence": 55,
                "description": "Shooting star, potential top reversal"
            })
        
        # Engulfing patterns (need previous candle)
        if prev is not None:
            # Bullish Engulfing: Large green candle engulfs previous red candle
            if (last['close'] > last['open'] and prev['close'] < prev['open'] and
                last['open'] < prev['close'] and last['close'] > prev['open']):
                patterns.append({
                    "name": "Bullish Engulfing",
                    "type": "BULLISH",
                    "confidence": 65,
                    "description": "Strong bullish reversal pattern"
                })
            
            # Bearish Engulfing: Large red candle engulfs previous green candle
            if (last['close'] < last['open'] and prev['close'] > prev['open'] and
                last['open'] > prev['close'] and last['close'] < prev['open']):
                patterns.append({
                    "name": "Bearish Engulfing",
                    "type": "BEARISH",
                    "confidence": 65,
                    "description": "Strong bearish reversal pattern"
                })
        
        return patterns
    
    # ==================== Helper Methods ====================
    
    def _find_peaks(self, data: np.ndarray, distance: int = 5) -> np.ndarray:
        """Find local maxima (peaks) in price data"""
        peaks = []
        for i in range(distance, len(data) - distance):
            if all(data[i] >= data[i-distance:i]) and all(data[i] >= data[i+1:i+distance+1]):
                peaks.append(i)
        return np.array(peaks)
    
    def _find_troughs(self, data: np.ndarray, distance: int = 5) -> np.ndarray:
        """Find local minima (troughs) in price data"""
        troughs = []
        for i in range(distance, len(data) - distance):
            if all(data[i] <= data[i-distance:i]) and all(data[i] <= data[i+1:i+distance+1]):
                troughs.append(i)
        return np.array(troughs)
    
    def _calculate_slope(self, data: np.ndarray) -> float:
        """Calculate slope of data points using linear regression"""
        if len(data) < 2:
            return 0
        
        x = np.arange(len(data))
        slope = np.polyfit(x, data, 1)[0]
        return slope
    
    def _calculate_score_and_signal(
        self,
        patterns: List[Dict],
        current_price: float
    ) -> Tuple[int, str]:
        """Calculate overall score and signal from detected patterns"""
        
        if not patterns:
            return 50, "HOLD"
        
        # Weight by confidence
        bullish_score = sum(p['confidence'] for p in patterns if p.get('type') == 'BULLISH')
        bearish_score = sum(p['confidence'] for p in patterns if p.get('type') == 'BEARISH')
        
        # Normalize to 0-100
        total = bullish_score + bearish_score
        
        if total == 0:
            return 50, "HOLD"
        
        score = int((bullish_score / total) * 100)
        
        # Determine signal
        if score >= 70:
            signal = "BUY"
        elif score >= 55:
            signal = "WEAK BUY"
        elif score >= 45:
            signal = "HOLD"
        elif score >= 30:
            signal = "WEAK SELL"
        else:
            signal = "SELL"
        
        return score, signal
    
    def _generate_reasoning(self, patterns: List[Dict], signal: str) -> str:
        """Generate human-readable reasoning"""
        
        if not patterns:
            return "No significant patterns detected"
        
        top_pattern = patterns[0]
        
        if signal in ["BUY", "WEAK BUY"]:
            return f"Bullish pattern detected: {top_pattern['name']} with {top_pattern['confidence']:.0f}% confidence. {top_pattern.get('description', '')}"
        elif signal in ["SELL", "WEAK SELL"]:
            return f"Bearish pattern detected: {top_pattern['name']} with {top_pattern['confidence']:.0f}% confidence. {top_pattern.get('description', '')}"
        else:
            return f"Mixed signals. Primary pattern: {top_pattern['name']} ({top_pattern.get('type', 'NEUTRAL')})"
    
    def _extract_key_signals(self, patterns: List[Dict]) -> List[str]:
        """Extract key signals from top patterns"""
        
        signals = []
        
        for pattern in patterns:
            pattern_type = pattern.get('type', 'NEUTRAL')
            name = pattern['name']
            confidence = pattern['confidence']
            
            if pattern_type == 'BULLISH':
                signals.append(f"🟢 {name} (Bullish, {confidence:.0f}%)")
            elif pattern_type == 'BEARISH':
                signals.append(f"🔴 {name} (Bearish, {confidence:.0f}%)")
            else:
                signals.append(f"⚪ {name} (Neutral, {confidence:.0f}%)")
        
        return signals[:3]  # Top 3 signals
    
    # ==================== PHASE 1 ENHANCEMENTS - ADVANCED CANDLESTICK PATTERNS ====================
    
    def _detect_three_soldiers_crows(self, df: pd.DataFrame) -> List[Dict]:
        """Three White Soldiers (bullish) / Three Black Crows (bearish)"""
        patterns = []
        if len(df) < 5:
            return patterns
        
        for i in range(len(df) - 3):
            candle1, candle2, candle3 = df.iloc[i], df.iloc[i+1], df.iloc[i+2]
            
            # Three White Soldiers (Bullish)
            if (candle1['close'] > candle1['open'] and 
                candle2['close'] > candle2['open'] and 
                candle3['close'] > candle3['open'] and
                candle2['close'] > candle1['close'] and
                candle3['close'] > candle2['close']):
                patterns.append({
                    'name': 'Three White Soldiers',
                    'type': 'BULLISH',
                    'confidence': 78,
                    'description': 'Strong bullish reversal - three consecutive green candles'
                })
            
            # Three Black Crows (Bearish)
            elif (candle1['close'] < candle1['open'] and 
                  candle2['close'] < candle2['open'] and 
                  candle3['close'] < candle3['open'] and
                  candle2['close'] < candle1['close'] and
                  candle3['close'] < candle2['close']):
                patterns.append({
                    'name': 'Three Black Crows',
                    'type': 'BEARISH',
                    'confidence': 78,
                    'description': 'Strong bearish reversal - three consecutive red candles'
                })
        
        return patterns[:3]  # Return top 3
    
    def _detect_morning_evening_star(self, df: pd.DataFrame) -> List[Dict]:
        """Morning Star (bullish) / Evening Star (bearish)"""
        patterns = []
        if len(df) < 5:
            return patterns
        
        for i in range(len(df) - 3):
            candle1, candle2, candle3 = df.iloc[i], df.iloc[i+1], df.iloc[i+2]
            
            # Morning Star (Bullish)
            body1 = abs(candle1['close'] - candle1['open'])
            body2 = abs(candle2['close'] - candle2['open'])
            body3 = abs(candle3['close'] - candle3['open'])
            
            if (candle1['close'] < candle1['open'] and  # Red candle
                body2 < body1 * 0.3 and  # Small body (star)
                candle3['close'] > candle3['open'] and  # Green candle
                candle3['close'] > (candle1['open'] + candle1['close']) / 2):  # Closes above midpoint
                patterns.append({
                    'name': 'Morning Star',
                    'type': 'BULLISH',
                    'confidence': 74,
                    'description': 'Bullish reversal at bottom - strong buy signal'
                })
            
            # Evening Star (Bearish)
            elif (candle1['close'] > candle1['open'] and  # Green candle
                  body2 < body1 * 0.3 and  # Small body (star)
                  candle3['close'] < candle3['open'] and  # Red candle
                  candle3['close'] < (candle1['open'] + candle1['close']) / 2):  # Closes below midpoint
                patterns.append({
                    'name': 'Evening Star',
                    'type': 'BEARISH',
                    'confidence': 74,
                    'description': 'Bearish reversal at top - strong sell signal'
                })
        
        return patterns[:3]
    
    def _detect_harami(self, df: pd.DataFrame) -> List[Dict]:
        """Bullish/Bearish Harami - Small candle inside previous large candle"""
        patterns = []
        if len(df) < 3:
            return patterns
        
        for i in range(len(df) - 2):
            candle1, candle2 = df.iloc[i], df.iloc[i+1]
            
            body1 = abs(candle1['close'] - candle1['open'])
            body2 = abs(candle2['close'] - candle2['open'])
            
            # Bullish Harami
            if (candle1['close'] < candle1['open'] and  # Large red candle
                candle2['close'] > candle2['open'] and  # Small green candle
                body2 < body1 * 0.5 and  # Small body inside
                candle2['open'] > candle1['close'] and
                candle2['close'] < candle1['open']):
                patterns.append({
                    'name': 'Bullish Harami',
                    'type': 'BULLISH',
                    'confidence': 68,
                    'description': 'Trend exhaustion - potential bullish reversal'
                })
            
            # Bearish Harami
            elif (candle1['close'] > candle1['open'] and  # Large green candle
                  candle2['close'] < candle2['open'] and  # Small red candle
                  body2 < body1 * 0.5 and  # Small body inside
                  candle2['open'] < candle1['close'] and
                  candle2['close'] > candle1['open']):
                patterns.append({
                    'name': 'Bearish Harami',
                    'type': 'BEARISH',
                    'confidence': 68,
                    'description': 'Trend exhaustion - potential bearish reversal'
                })
        
        return patterns[:3]
    
    def _detect_piercing_dark_cloud(self, df: pd.DataFrame) -> List[Dict]:
        """Piercing Pattern (bullish) / Dark Cloud Cover (bearish)"""
        patterns = []
        if len(df) < 3:
            return patterns
        
        for i in range(len(df) - 2):
            candle1, candle2 = df.iloc[i], df.iloc[i+1]
            
            # Piercing Pattern (Bullish)
            if (candle1['close'] < candle1['open'] and  # Red candle
                candle2['close'] > candle2['open'] and  # Green candle
                candle2['open'] < candle1['close'] and  # Opens below previous close
                candle2['close'] > (candle1['open'] + candle1['close']) / 2 and  # Closes above midpoint
                candle2['close'] < candle1['open']):  # But not above previous open
                patterns.append({
                    'name': 'Piercing Pattern',
                    'type': 'BULLISH',
                    'confidence': 71,
                    'description': 'Bullish reversal confirmation'
                })
            
            # Dark Cloud Cover (Bearish)
            elif (candle1['close'] > candle1['open'] and  # Green candle
                  candle2['close'] < candle2['open'] and  # Red candle
                  candle2['open'] > candle1['close'] and  # Opens above previous close
                  candle2['close'] < (candle1['open'] + candle1['close']) / 2 and  # Closes below midpoint
                  candle2['close'] > candle1['open']):  # But not below previous open
                patterns.append({
                    'name': 'Dark Cloud Cover',
                    'type': 'BEARISH',
                    'confidence': 71,
                    'description': 'Bearish reversal confirmation'
                })
        
        return patterns[:3]
    
    def _detect_tweezer_tops_bottoms(self, df: pd.DataFrame) -> List[Dict]:
        """Tweezer Tops (bearish) / Tweezer Bottoms (bullish)"""
        patterns = []
        if len(df) < 3:
            return patterns
        
        for i in range(len(df) - 2):
            candle1, candle2 = df.iloc[i], df.iloc[i+1]
            
            # Tweezer Bottoms (Bullish)
            low_diff = abs(candle1['low'] - candle2['low'])
            low_avg = (candle1['low'] + candle2['low']) / 2
            if low_diff / low_avg < 0.005:  # Lows within 0.5%
                if candle1['close'] < candle1['open'] and candle2['close'] > candle2['open']:
                    patterns.append({
                        'name': 'Tweezer Bottoms',
                        'type': 'BULLISH',
                        'confidence': 72,
                        'description': 'Support level confirmed - bullish reversal'
                    })
            
            # Tweezer Tops (Bearish)
            high_diff = abs(candle1['high'] - candle2['high'])
            high_avg = (candle1['high'] + candle2['high']) / 2
            if high_diff / high_avg < 0.005:  # Highs within 0.5%
                if candle1['close'] > candle1['open'] and candle2['close'] < candle2['open']:
                    patterns.append({
                        'name': 'Tweezer Tops',
                        'type': 'BEARISH',
                        'confidence': 72,
                        'description': 'Resistance level confirmed - bearish reversal'
                    })
        
        return patterns[:3]
    
    # ==================== PHASE 1 ENHANCEMENTS - VOLUME-BASED PATTERNS ====================
    
    def _detect_climax_volume(self, df: pd.DataFrame) -> List[Dict]:
        """Climax Volume Reversal - Exhaustion with 3x volume"""
        patterns = []
        if len(df) < 20:
            return patterns
        
        avg_volume = df['volume'].rolling(window=20).mean()
        
        for i in range(20, len(df)):
            current_vol = df.iloc[i]['volume']
            avg_vol = avg_volume.iloc[i]
            
            if current_vol > avg_vol * 3:  # 3x average volume
                price_change = (df.iloc[i]['close'] - df.iloc[i]['open']) / df.iloc[i]['open']
                
                if abs(price_change) > 0.03:  # Big price move (>3%)
                    pattern_type = 'BEARISH' if price_change > 0 else 'BULLISH'  # Reversal expected
                    patterns.append({
                        'name': 'Climax Volume',
                        'type': pattern_type,
                        'confidence': 77,
                        'description': f'Exhaustion move - {pattern_type.lower()} reversal expected'
                    })
        
        return patterns[:2]
    
    def _detect_volume_breakout(self, df: pd.DataFrame) -> List[Dict]:
        """Volume Spike Breakout - 2x volume on breakout"""
        patterns = []
        if len(df) < 20:
            return patterns
        
        avg_volume = df['volume'].rolling(window=20).mean()
        high_20 = df['high'].rolling(window=20).max()
        low_20 = df['low'].rolling(window=20).min()
        
        for i in range(20, len(df)):
            current_vol = df.iloc[i]['volume']
            avg_vol = avg_volume.iloc[i]
            
            if current_vol > avg_vol * 2:  # 2x volume
                if df.iloc[i]['close'] > high_20.iloc[i-1]:  # Breakout above
                    patterns.append({
                        'name': 'Volume Breakout (Bullish)',
                        'type': 'BULLISH',
                        'confidence': 82,
                        'description': 'Strong volume breakout above resistance'
                    })
                elif df.iloc[i]['close'] < low_20.iloc[i-1]:  # Breakdown below
                    patterns.append({
                        'name': 'Volume Breakdown (Bearish)',
                        'type': 'BEARISH',
                        'confidence': 82,
                        'description': 'Strong volume breakdown below support'
                    })
        
        return patterns[:2]
    
    def _detect_volume_dryup(self, df: pd.DataFrame) -> List[Dict]:
        """Volume Dry-Up - Low volume before breakout"""
        patterns = []
        if len(df) < 20:
            return patterns
        
        avg_volume = df['volume'].rolling(window=20).mean()
        recent_vol = df['volume'].tail(5).mean()
        avg_vol_20 = avg_volume.iloc[-1]
        
        if recent_vol < avg_vol_20 * 0.5:  # Volume < 50% of average
            # Check price consolidation
            high_5 = df['high'].tail(5).max()
            low_5 = df['low'].tail(5).min()
            price_range = (high_5 - low_5) / low_5
            
            if price_range < 0.03:  # Tight range (<3%)
                patterns.append({
                    'name': 'Volume Dry-Up',
                    'type': 'NEUTRAL',
                    'confidence': 73,
                    'description': 'Low volume + tight range - breakout imminent'
                })
        
        return patterns
    
    def _detect_accumulation_distribution(self, df: pd.DataFrame) -> List[Dict]:
        """Accumulation/Distribution Zones - Smart money detection"""
        patterns = []
        if len(df) < 20:
            return patterns
        
        # Calculate Accumulation/Distribution Line
        clv = ((df['close'] - df['low']) - (df['high'] - df['close'])) / (df['high'] - df['low'])
        clv = clv.fillna(0)
        ad_line = (clv * df['volume']).cumsum()
        
        # Check recent trend
        ad_recent = ad_line.tail(10)
        ad_slope = (ad_recent.iloc[-1] - ad_recent.iloc[0]) / 10
        
        if ad_slope > 0:
            patterns.append({
                'name': 'Accumulation Zone',
                'type': 'BULLISH',
                'confidence': 76,
                'description': 'Smart money accumulating - bullish'
            })
        elif ad_slope < 0:
            patterns.append({
                'name': 'Distribution Zone',
                'type': 'BEARISH',
                'confidence': 76,
                'description': 'Smart money distributing - bearish'
            })
        
        return patterns
    
    def _detect_volume_profile(self, df: pd.DataFrame) -> List[Dict]:
        """Volume Profile - High volume nodes as support/resistance"""
        patterns = []
        if len(df) < 30:
            return patterns
        
        # Calculate volume at price levels
        recent_data = df.tail(30)
        price_bins = pd.cut(recent_data['close'], bins=10)
        volume_profile = recent_data.groupby(price_bins)['volume'].sum()
        
        max_volume_idx = volume_profile.idxmax()
        max_volume_price = (max_volume_idx.left + max_volume_idx.right) / 2
        current_price = df.iloc[-1]['close']
        
        if current_price < max_volume_price:
            patterns.append({
                'name': 'Below High Volume Node',
                'type': 'BULLISH',
                'confidence': 70,
                'description': f'Price below POC (₹{max_volume_price:.2f}) - strong support'
            })
        elif current_price > max_volume_price:
            patterns.append({
                'name': 'Above High Volume Node',
                'type': 'BEARISH',
                'confidence': 70,
                'description': f'Price above POC (₹{max_volume_price:.2f}) - resistance ahead'
            })
        
        return patterns
    
    # ==================== PHASE 1 ENHANCEMENTS - HARMONIC PATTERNS ====================
    
    def _detect_gartley(self, df: pd.DataFrame) -> List[Dict]:
        """Gartley Pattern - Fibonacci-based reversal (simplified)"""
        patterns = []
        if len(df) < 30:
            return patterns
        
        # Simplified Gartley detection using swing highs/lows
        recent = df.tail(30)
        highs = recent['high'].values
        lows = recent['low'].values
        
        # Look for XABCD pattern structure
        swing_high = np.max(highs[-20:])
        swing_low = np.min(lows[-20:])
        current_price = df.iloc[-1]['close']
        
        # Check if price is at potential reversal zone
        fib_level = swing_low + (swing_high - swing_low) * 0.786  # 78.6% retracement
        
        if abs(current_price - fib_level) / fib_level < 0.02:  # Within 2% of Fib level
            if current_price < swing_high:
                patterns.append({
                    'name': 'Bullish Gartley',
                    'type': 'BULLISH',
                    'confidence': 72,
                    'description': 'Harmonic reversal at 78.6% Fib level'
                })
        
        return patterns[:1]
    
    def _detect_butterfly(self, df: pd.DataFrame) -> List[Dict]:
        """Butterfly Pattern - Extended move reversal (simplified)"""
        patterns = []
        if len(df) < 30:
            return patterns
        
        recent = df.tail(30)
        swing_high = recent['high'].max()
        swing_low = recent['low'].min()
        current_price = df.iloc[-1]['close']
        
        # Butterfly completes at 127.2% extension
        extension_level = swing_high + (swing_high - swing_low) * 0.272
        
        if abs(current_price - extension_level) / extension_level < 0.02:
            patterns.append({
                'name': 'Butterfly Pattern',
                'type': 'BEARISH',
                'confidence': 70,
                'description': 'Extended move - reversal expected'
            })
        
        return patterns[:1]
    
    def _detect_bat(self, df: pd.DataFrame) -> List[Dict]:
        """Bat Pattern - Precise reversal zone (simplified)"""
        patterns = []
        if len(df) < 30:
            return patterns
        
        recent = df.tail(30)
        swing_high = recent['high'].max()
        swing_low = recent['low'].min()
        current_price = df.iloc[-1]['close']
        
        # Bat completes at 88.6% retracement
        bat_level = swing_low + (swing_high - swing_low) * 0.886
        
        if abs(current_price - bat_level) / bat_level < 0.015:  # Within 1.5%
            patterns.append({
                'name': 'Bat Pattern',
                'type': 'BULLISH',
                'confidence': 74,
                'description': 'Precise reversal at 88.6% level'
            })
        
        return patterns[:1]
    
    def _detect_crab(self, df: pd.DataFrame) -> List[Dict]:
        """Crab Pattern - Extreme reversal (simplified)"""
        patterns = []
        if len(df) < 30:
            return patterns
        
        recent = df.tail(30)
        swing_high = recent['high'].max()
        swing_low = recent['low'].min()
        current_price = df.iloc[-1]['close']
        
        # Crab completes at 161.8% extension (extreme)
        crab_level = swing_high + (swing_high - swing_low) * 0.618
        
        if abs(current_price - crab_level) / crab_level < 0.02:
            patterns.append({
                'name': 'Crab Pattern',
                'type': 'BEARISH',
                'confidence': 72,
                'description': 'Extreme extension - strong reversal zone'
            })
        
        return patterns[:1]
    
    def _detect_abcd(self, df: pd.DataFrame) -> List[Dict]:
        """AB=CD Pattern - Simple harmonic (simplified)"""
        patterns = []
        if len(df) < 20:
            return patterns
        
        recent = df.tail(20)
        highs = recent['high'].values
        lows = recent['low'].values
        
        # Find AB and CD legs
        ab_move = highs[-15] - lows[-10]
        cd_move = highs[-5] - lows[-1]
        
        # Check if CD = AB (within 10%)
        if abs(cd_move - ab_move) / ab_move < 0.1:
            current_price = df.iloc[-1]['close']
            if current_price > (highs[-5] + lows[-1]) / 2:
                patterns.append({
                    'name': 'Bullish AB=CD',
                    'type': 'BULLISH',
                    'confidence': 76,
                    'description': 'Equal legs pattern - continuation likely'
                })
            else:
                patterns.append({
                    'name': 'Bearish AB=CD',
                    'type': 'BEARISH',
                    'confidence': 76,
                    'description': 'Equal legs pattern - reversal likely'
                })
        
        return patterns[:1]
    
    # ==================== HELPER METHODS ====================
    
    def _insufficient_data_response(self, candle_count: int) -> AgentResult:
        """Return response when insufficient data"""
        return AgentResult(
            agent_type=self.name,
            symbol="UNKNOWN",
            score=50.0,
            confidence="Low",
            signals=[],
            reasoning=f"Insufficient data for pattern recognition (need {self.min_candles}, have {candle_count})",
            metadata={
                "total_patterns": 0,
                "bullish_count": 0,
                "bearish_count": 0,
                "strongest_pattern": None,
                "patterns_detail": [],
                "key_signals": ["Waiting for more data"]
            }
        )


# Global instance
pattern_recognition_agent = PatternRecognitionAgent()
