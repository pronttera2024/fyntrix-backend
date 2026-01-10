"""
Auto-Monitoring Agent
24/7 position and watchlist monitoring with real-time alerts

Features:
- Monitors open positions continuously
- Tracks stop-loss and target levels
- Alerts on significant price moves
- Detects breakouts/breakdowns
- Portfolio risk monitoring
- Position health scoring
- Scalping position auto-exit detection (NEW)
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, timezone

from .base import BaseAgent, AgentResult
from ..core.market_hours import now_ist, is_cash_market_open_ist
from ..models.strategy import StrategyAdvisory
from ..services.support_resistance_service import support_resistance_service
from .sentiment_agent import SentimentAgent

logger = logging.getLogger(__name__)


class AutoMonitoringAgent(BaseAgent):
    """
    Automated monitoring for positions, stops, targets, and alerts.
    
    Monitors:
    - Open positions (P&L, stop-loss distance, target proximity)
    - Watchlist breakouts/breakdowns
    - Risk exposure
    - Market regime changes
    - Critical price levels
    """
    
    def __init__(self, weight: float = 0.06):
        super().__init__(name="auto_monitoring", weight=weight)
        self.alert_thresholds = {
            'stop_loss_distance': 0.03,  # Alert if within 3% of SL
            'target_proximity': 0.05,    # Alert if within 5% of target
            'breakout_threshold': 0.02,  # 2% breakout
            'volatility_spike': 1.5      # 1.5x normal volatility
        }
        self._news_sentiment_agent = SentimentAgent(weight=0.0)
    
    async def analyze(
        self,
        symbol: str,
        context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Monitor symbol and generate alerts.
        
        Args:
            symbol: Stock symbol
            context: Market context including positions, watchlist
            
        Returns:
            AgentResult with monitoring alerts
        """
        context = context or {}
        
        # Get current price
        current_price = context.get('current_price', 0)
        
        # Get position info if available
        position = context.get('position')
        
        # Get other agent results
        other_agents = context.get('agent_results', {})
        
        # Perform monitoring checks
        alerts = []
        health_score = 100
        
        if position:
            # Monitor position
            position_alerts, pos_health = self._monitor_position(
                symbol, current_price, position, other_agents
            )
            alerts.extend(position_alerts)
            health_score = min(health_score, pos_health)
        else:
            # Monitor for entry opportunities
            entry_alerts = self._monitor_entry_opportunities(
                symbol, current_price, other_agents
            )
            alerts.extend(entry_alerts)
        
        # Monitor market conditions
        market_alerts = self._monitor_market_conditions(other_agents)
        alerts.extend(market_alerts)
        
        # Monitor technical levels
        level_alerts = self._monitor_key_levels(symbol, current_price, other_agents)
        alerts.extend(level_alerts)

        # Strategy-based advisories (e.g., S1 Heikin-Ashi + PSAR + RSI)
        try:
            strategy_alerts = await self._evaluate_strategy_advisories(
                symbol=symbol,
                current_price=current_price,
                position=position,
                context=context,
            )
            alerts.extend(strategy_alerts)
        except Exception as e:
            logger.error(
                "[AutoMonitoring] Strategy advisories failed for %s: %s",
                symbol,
                e,
                exc_info=True,
            )

        # S/R-based exit advisories (SR_EXIT) layered on top of strategy rules.
        if position and current_price:
            try:
                sr_alerts = await self._evaluate_sr_exit_advisories_for_position(
                    symbol=symbol,
                    current_price=current_price,
                    position=position,
                )
                alerts.extend(sr_alerts)
            except Exception as e:
                logger.error(
                    "[AutoMonitoring] SR advisories failed for %s: %s",
                    symbol,
                    e,
                    exc_info=True,
                )

        if position and current_price:
            try:
                news_alerts = await self._evaluate_news_exit_advisories_for_position(
                    symbol=symbol,
                    current_price=current_price,
                    position=position,
                )
                alerts.extend(news_alerts)
            except Exception as e:
                logger.error(
                    "[AutoMonitoring] NEWS advisories failed for %s: %s",
                    symbol,
                    e,
                    exc_info=True,
                )
        
        # Calculate monitoring score (based on urgency)
        monitoring_score = self._calculate_monitoring_score(alerts, health_score)
        
        # Determine confidence
        confidence = self._calculate_confidence(alerts, position is not None)
        
        # Generate signals
        signals = self._generate_signals(alerts)
        
        # Generate reasoning
        reasoning = self._generate_reasoning(alerts, health_score, position is not None)
        
        return AgentResult(
            agent_type=self.name,
            symbol=symbol,
            score=float(monitoring_score),
            confidence=confidence,
            signals=signals,
            reasoning=reasoning,
            metadata={
                'alerts': alerts[:10],  # Top 10 alerts
                'alert_count': len(alerts),
                'health_score': health_score,
                'has_position': position is not None,
                'urgency_level': self._get_urgency_level(alerts)
            }
        )
    
    # ==================== Position Monitoring ====================
    
    def _monitor_position(
        self,
        symbol: str,
        current_price: float,
        position: Dict,
        other_agents: Dict
    ) -> tuple:
        """Monitor open position"""
        
        alerts = []
        health_score = 100
        
        entry_price = position.get('entry_price', 0)
        stop_loss = position.get('stop_loss', 0)
        target = position.get('target', 0)
        quantity = position.get('quantity', 0)
        direction = position.get('direction', 'LONG')
        
        if entry_price == 0:
            return alerts, health_score
        
        # Calculate P&L
        if direction == 'LONG':
            pnl_percent = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl_percent = ((entry_price - current_price) / entry_price) * 100
        
        # Check stop loss proximity
        if stop_loss > 0:
            if direction == 'LONG':
                sl_distance = ((current_price - stop_loss) / current_price) * 100
            else:
                sl_distance = ((stop_loss - current_price) / current_price) * 100
            
            if sl_distance <= self.alert_thresholds['stop_loss_distance'] * 100:
                alerts.append({
                    'type': 'STOP_LOSS_ALERT',
                    'urgency': 'CRITICAL',
                    'message': f'Price within {sl_distance:.1f}% of stop loss!',
                    'action': 'Consider exiting or tightening stop'
                })
                health_score -= 40
        
        # Check target proximity
        if target > 0:
            if direction == 'LONG':
                target_distance = ((target - current_price) / current_price) * 100
            else:
                target_distance = ((current_price - target) / current_price) * 100
            
            if target_distance <= self.alert_thresholds['target_proximity'] * 100:
                alerts.append({
                    'type': 'TARGET_ALERT',
                    'urgency': 'MEDIUM',
                    'message': f'Price within {target_distance:.1f}% of target!',
                    'action': 'Consider booking profits'
                })
        
        return alerts, health_score
    
    def _monitor_entry_opportunities(
        self,
        symbol: str,
        current_price: float,
        other_agents: Dict
    ) -> List[Dict]:
        """Monitor for entry opportunities"""
        
        alerts = []
        
        # Check pattern recognition
        patterns = other_agents.get('pattern_recognition', {})
        pattern_score = patterns.get('score', 50)
        
        if pattern_score >= 70:
            alerts.append({
                'type': 'ENTRY_OPPORTUNITY',
                'urgency': 'MEDIUM',
                'message': 'Strong pattern detected',
                'action': 'Consider entering position'
            })
        
        return alerts
    
    def _monitor_market_conditions(self, other_agents: Dict) -> List[Dict]:
        """Monitor overall market conditions"""
        
        alerts = []
        
        regime = other_agents.get('market_regime', {})
        regime_meta = regime.get('metadata', {})
        volatility = regime_meta.get('volatility', 'LOW')
        
        if volatility == 'HIGH':
            alerts.append({
                'type': 'VOLATILITY_ALERT',
                'urgency': 'MEDIUM',
                'message': 'High market volatility detected',
                'action': 'Use wider stops and reduce position sizes'
            })
        
        return alerts
    
    def _monitor_key_levels(
        self,
        symbol: str,
        current_price: float,
        other_agents: Dict
    ) -> List[Dict]:
        """Monitor key technical levels"""
        
        alerts = []
        
        regime = other_agents.get('market_regime', {})
        regime_meta = regime.get('metadata', {})
        support = regime_meta.get('support_level', 0)
        resistance = regime_meta.get('resistance_level', 0)
        
        if current_price > 0 and support > 0:
            distance_to_support = ((current_price - support) / current_price) * 100
            if distance_to_support <= 2:
                alerts.append({
                    'type': 'SUPPORT_TEST',
                    'urgency': 'MEDIUM',
                    'message': f'Testing support at {support:.2f}',
                    'action': 'Watch for bounce or breakdown'
                })
        
        return alerts

    # ==================== STRATEGY ADVISORIES (e.g. S1) ====================

    async def _evaluate_strategy_advisories(
        self,
        symbol: str,
        current_price: float,
        position: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Evaluate strategy-specific advisories (S1/S2/S3).

        This function is **read-only**: it never mutates the position or
        exit strategy. It only returns advisory alerts that are clearly
        marked as ADVISORY_ONLY.
        """

        if not position:
            return []

        context = context or {}
        exit_strategy = position.get('exit_strategy') or context.get('exit_strategy') or {}
        strategy_profile = (
            exit_strategy.get('strategy_profile')
            or position.get('strategy_profile')
            or context.get('strategy_profile')
        )

        if not strategy_profile or not isinstance(strategy_profile, dict):
            return []

        strategy_id = str(strategy_profile.get('id') or '')
        advisories: List[StrategyAdvisory] = []

        # S1: Heikin-Ashi + PSAR + RSI (Intraday)
        if strategy_id == 'S1_HEIKIN_ASHI_PSAR_RSI_3M':
            s1_advisories = await self._evaluate_s1_advisories_for_position(
                symbol=symbol,
                current_price=current_price,
                position=position,
                strategy_profile=strategy_profile,
            )
            advisories.extend(s1_advisories)

        # S2: EMA trend pullback (Scalping/Intraday)
        elif strategy_id == 'S2_EMA_TREND_PULLBACK':
            s2_advisories = await self._evaluate_s2_advisories_for_position(
                symbol=symbol,
                current_price=current_price,
                position=position,
                strategy_profile=strategy_profile,
            )
            advisories.extend(s2_advisories)

        # S3: Bollinger Bands trend pullback (Intraday/Swing)
        elif strategy_id == 'S3_BB_TREND_PULLBACK':
            s3_advisories = await self._evaluate_s3_advisories_for_position(
                symbol=symbol,
                current_price=current_price,
                position=position,
                strategy_profile=strategy_profile,
            )
            advisories.extend(s3_advisories)

        # Convert StrategyAdvisory models to alert dicts compatible with
        # existing alert consumers (type/urgency/message/action ...)
        alert_dicts: List[Dict[str, Any]] = []
        for adv in advisories:
            data = adv.dict()
            # Map severity -> urgency used by existing UI flows
            severity = (adv.severity or 'info').lower()
            if severity == 'critical':
                urgency = 'CRITICAL'
            elif severity == 'high':
                urgency = 'HIGH'
            elif severity == 'warning':
                urgency = 'MEDIUM'
            else:
                urgency = 'LOW'

            # Strategy-specific alert type for downstream consumers
            sid = (adv.strategy_id or '').upper()
            if sid.startswith('S1_'):
                alert_type = 'S1_STRATEGY_ADVISORY'
            elif sid.startswith('S2_'):
                alert_type = 'S2_STRATEGY_ADVISORY'
            elif sid.startswith('S3_'):
                alert_type = 'S3_STRATEGY_ADVISORY'
            else:
                alert_type = 'STRATEGY_ADVISORY'

            data.update(
                {
                    'type': alert_type,
                    'urgency': urgency,
                }
            )
            alert_dicts.append(data)

        return alert_dicts

    async def _evaluate_s1_advisories_for_position(
        self,
        symbol: str,
        current_price: float,
        position: Dict[str, Any],
        strategy_profile: Dict[str, Any],
    ) -> List[StrategyAdvisory]:
        """Evaluate S1 (Heikin-Ashi + PSAR + RSI) advisory rules for a position.

        Uses intraday candles from the chart data service to compute
        Heikin-Ashi, PSAR and RSI, then emits advisory-only alerts such as
        PARTIAL_PROFIT and CONTEXT_INVALIDATED.
        """

        from ..services.chart_data_service import chart_data_service

        entry_price = float(position.get('entry_price') or 0.0)
        stop_loss = position.get('stop_loss')
        try:
            initial_sl = float(stop_loss) if stop_loss is not None else 0.0
        except Exception:
            initial_sl = 0.0

        if entry_price <= 0:
            return []

        direction = position.get('direction', 'LONG') or 'LONG'

        # Fetch short-term intraday candles (use 1D = 5m candles as proxy)
        try:
            chart = await chart_data_service.fetch_chart_data(symbol, '1D')
        except Exception as e:
            logger.error("[AutoMonitoring] S1 chart fetch failed for %s: %s", symbol, e, exc_info=True)
            return []

        candles = (chart or {}).get('candles') or []
        if not candles or len(candles) < 20:
            return []

        df = pd.DataFrame(candles)
        required_cols = {'open', 'high', 'low', 'close'}
        if not required_cols.issubset(df.columns):
            return []

        df = df.sort_values('time').reset_index(drop=True)

        # Compute indicators
        ha_df = self._compute_heikin_ashi(df)
        psar = self._compute_psar(df['high'], df['low'])
        rsi = self._compute_rsi(df['close'], length=int(strategy_profile.get('indicator_params', {}).get('rsi', {}).get('length', 14)))

        if len(ha_df) == 0 or len(psar) == 0 or len(rsi) == 0:
            return []

        last_ha = ha_df.iloc[-1]
        last_psar = float(psar.iloc[-1])
        last_rsi = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else None

        if last_rsi is None:
            return []

        last_price = float(current_price or last_ha['close'])

        ha_trend = 'green' if last_ha['ha_close'] > last_ha['ha_open'] else 'red'
        price_vs_psar = 'above' if last_price > last_psar else 'below'

        rr_multiple = self._compute_rr_multiple(direction, last_price, entry_price, initial_sl)

        exit_criteria = strategy_profile.get('exit_criteria', {}) or {}

        advisories: List[StrategyAdvisory] = []

        # 1) Partial profit advisory at configured R multiple (e.g. 1R)
        try:
            partial_rr = float(exit_criteria.get('partial_booking_at_rr', 1.0))
        except Exception:
            partial_rr = 1.0

        if rr_multiple is not None and rr_multiple >= partial_rr:
            advisories.append(
                StrategyAdvisory(
                    id='S1_PARTIAL_PROFIT',
                    strategy_id=strategy_profile.get('id', 'S1_HEIKIN_ASHI_PSAR_RSI_3M'),
                    kind='PARTIAL_PROFIT',
                    severity='info',
                    enforcement='ADVISORY_ONLY',
                    symbol=symbol,
                    direction=direction,
                    price=last_price,
                    entry_price=entry_price,
                    initial_sl=initial_sl or None,
                    rr_multiple=rr_multiple,
                    indicators={
                        'ha_trend': ha_trend,
                        'ha_open': float(last_ha['ha_open']),
                        'ha_close': float(last_ha['ha_close']),
                        'psar': last_psar,
                        'rsi': last_rsi,
                    },
                    message=f"Price reached {rr_multiple:.1f}R; consider partial booking and moving SL to breakeven.",
                    recommended_actions=[
                        {
                            'action': 'PARTIAL_BOOK',
                            'description': 'Book partial profits (e.g. 50%) around current price.',
                        },
                        {
                            'action': 'TIGHTEN_SL',
                            'description': 'Move stop-loss closer to breakeven or latest PSAR value.',
                        },
                    ],
                    recommended_exit_price=last_price,
                )
            )

        # 1b) Soft trend-weakening advisory (non-exit): EMA stack still valid
        # but fast/slow spread is compressing against the position.
        trend_weakening = False
        if direction == 'LONG' and up_stack and spread_now < spread_prev:
            trend_weakening = True
        elif direction != 'LONG' and down_stack and spread_now > spread_prev:
            trend_weakening = True

        if trend_weakening and rr_multiple is not None and rr_multiple > 0:
            try:
                advisories.append(
                    StrategyAdvisory(
                        id='S2_TREND_WEAKENING',
                        strategy_id=strategy_profile.get('id', 'S2_EMA_TREND_PULLBACK'),
                        kind='TREND_WEAKENING',
                        severity='warning',
                        enforcement='ADVISORY_ONLY',
                        is_exit=False,
                        symbol=symbol,
                        direction=direction,
                        price=last_price,
                        entry_price=entry_price,
                        initial_sl=initial_sl or None,
                        rr_multiple=rr_multiple,
                        indicators={
                            'ema_50': ef_now,
                            'ema_100': em_now,
                            'ema_150': es_now,
                            'ema_50_prev': ef_prev,
                            'ema_100_prev': em_prev,
                            'ema_150_prev': es_prev,
                            'spread_now': spread_now,
                            'spread_prev': spread_prev,
                        },
                        message='S2 trend weakening: EMA stack still aligned but momentum is fading. Monitor position closely.',
                        recommended_exit_price=last_price,
                    )
                )
            except Exception:
                pass

        # 1c) Volume fade advisory (non-exit): recent volume significantly
        # lower than prior window, signalling potential exhaustion.
        volume_fade = False
        if 'volume' in df.columns:
            try:
                vol = df['volume'].astype(float)
                window = max(5, min(20, len(vol) // 2))
                if len(vol) >= window * 2:
                    recent = float(vol.iloc[-window:].mean())
                    prior = float(vol.iloc[-2 * window : -window].mean())
                    if prior > 0 and recent < prior * 0.6:
                        volume_fade = True
                        recent_vol = recent
                        prior_vol = prior
                    else:
                        recent_vol = None
                        prior_vol = None
                else:
                    recent_vol = None
                    prior_vol = None
            except Exception:
                volume_fade = False
                recent_vol = None
                prior_vol = None
        else:
            recent_vol = None
            prior_vol = None

        if volume_fade:
            try:
                indicators_vol = {
                    'ema_50': ef_now,
                    'ema_100': em_now,
                    'ema_150': es_now,
                }
                if recent_vol is not None and prior_vol is not None:
                    indicators_vol.update(
                        {
                            'volume_recent_avg': recent_vol,
                            'volume_prior_avg': prior_vol,
                        }
                    )

                advisories.append(
                    StrategyAdvisory(
                        id='S2_VOLUME_FADE',
                        strategy_id=strategy_profile.get('id', 'S2_EMA_TREND_PULLBACK'),
                        kind='VOLUME_FADE',
                        severity='info',
                        enforcement='ADVISORY_ONLY',
                        is_exit=False,
                        symbol=symbol,
                        direction=direction,
                        price=last_price,
                        entry_price=entry_price,
                        initial_sl=initial_sl or None,
                        rr_multiple=rr_multiple,
                        indicators=indicators_vol,
                        message='S2 trend volume fading: recent participation is lower than prior window. Follow-through risk is higher.',
                        recommended_exit_price=last_price,
                    )
                )
            except Exception:
                pass

        # 2) Context invalidation advisory when S1 conditions break
        invalid_cfg_key = 'invalidated_when_long' if direction == 'LONG' else 'invalidated_when_short'
        invalid_cfg = exit_criteria.get(invalid_cfg_key, {}) or {}

        rsi_below = invalid_cfg.get('rsi_below')
        rsi_above = invalid_cfg.get('rsi_above')

        context_invalidated = False
        if direction == 'LONG':
            if (
                invalid_cfg.get('ha_trend') == ha_trend
                and invalid_cfg.get('price_vs_psar') == price_vs_psar
                and rsi_below is not None
                and last_rsi < float(rsi_below)
            ):
                context_invalidated = True
        else:
            if (
                invalid_cfg.get('ha_trend') == ha_trend
                and invalid_cfg.get('price_vs_psar') == price_vs_psar
                and rsi_above is not None
                and last_rsi > float(rsi_above)
            ):
                context_invalidated = True

        if context_invalidated:
            try:
                if direction == 'LONG':
                    rsi_thresh = rsi_below
                    rsi_cmp = '<'
                else:
                    rsi_thresh = rsi_above
                    rsi_cmp = '>'

                if rsi_thresh is not None:
                    sr_reason = (
                        f"Heikin-Ashi {ha_trend}, price {price_vs_psar} PSAR (PSAR {float(last_psar):.2f}), "
                        f"RSI {float(last_rsi):.1f} {rsi_cmp} {float(rsi_thresh):.1f}"
                    )
                else:
                    sr_reason = (
                        f"Heikin-Ashi {ha_trend}, price {price_vs_psar} PSAR (PSAR {float(last_psar):.2f}), "
                        f"RSI {float(last_rsi):.1f}"
                    )
            except Exception:
                sr_reason = None

            advisories.append(
                StrategyAdvisory(
                    id='S1_CONTEXT_INVALIDATED',
                    strategy_id=strategy_profile.get('id', 'S1_HEIKIN_ASHI_PSAR_RSI_3M'),
                    kind='CONTEXT_INVALIDATED',
                    severity='high',
                    enforcement='ADVISORY_ONLY',
                    symbol=symbol,
                    direction=direction,
                    price=last_price,
                    entry_price=entry_price,
                    initial_sl=initial_sl or None,
                    rr_multiple=rr_multiple,
                    indicators={
                        'ha_trend': ha_trend,
                        'ha_open': float(last_ha['ha_open']),
                        'ha_close': float(last_ha['ha_close']),
                        'psar': last_psar,
                        'rsi': last_rsi,
                    },
                    message='S1 context invalidated: Heikin-Ashi trend flipped and price/RSI broke S1 rules. Consider exiting or tightening SL aggressively.',
                    sr_reason=sr_reason,
                    recommended_actions=[
                        {
                            'action': 'EXIT',
                            'description': 'Consider closing most or all of the position at current market price.',
                        },
                        {
                            'action': 'TIGHTEN_SL',
                            'description': 'If not exiting fully, tighten stop-loss just beyond latest PSAR.',
                        },
                    ],
                    recommended_exit_price=last_price,
                )
            )

        return advisories

    async def _evaluate_news_exit_advisories_for_position(
        self,
        symbol: str,
        current_price: float,
        position: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not position:
            return []

        try:
            price = float(current_price or 0.0)
        except Exception:
            return []

        if price <= 0.0:
            return []

        try:
            sentiment_agent = getattr(self, "_news_sentiment_agent", None)
            if sentiment_agent is None:
                sentiment_agent = SentimentAgent(weight=0.0)
                self._news_sentiment_agent = sentiment_agent

            sent_result = await sentiment_agent.analyze(symbol)
        except Exception as e:
            logger.error(
                "[AutoMonitoring] NEWS_EXIT sentiment analysis failed for %s: %s",
                symbol,
                e,
                exc_info=True,
            )
            return []

        try:
            sent_score = float(sent_result.score)
        except Exception:
            sent_score = 50.0

        metadata = sent_result.metadata or {}
        try:
            news_count = int(metadata.get("news_count") or 0)
        except Exception:
            news_count = 0
        try:
            pos_count = int(metadata.get("positive_count") or 0)
        except Exception:
            pos_count = 0
        try:
            neg_count = int(metadata.get("negative_count") or 0)
        except Exception:
            neg_count = 0
        try:
            neu_count = int(metadata.get("neutral_count") or 0)
        except Exception:
            neu_count = 0

        sentiment_label = None
        signal_text = None
        for sig in sent_result.signals or []:
            if sig.get("type") == "NEWS_SENTIMENT":
                value = sig.get("value")
                sentiment_label = str(value).strip() if value is not None else None
                st = sig.get("signal")
                signal_text = str(st).strip() if st is not None else None
                break

        direction = (position.get("direction") or "LONG").upper()

        if direction == "LONG":
            news_risk_score = max(0.0, 100.0 - sent_score)
        else:
            try:
                news_risk_score = float(sent_score)
            except Exception:
                news_risk_score = 50.0

        if news_risk_score < 60.0:
            return []

        if sentiment_label is None:
            if news_risk_score >= 75.0:
                sentiment_label = "Bearish" if direction == "LONG" else "Bullish"
            else:
                sentiment_label = "Negative bias" if direction == "LONG" else "Positive bias"

        parts: List[str] = []
        parts.append(f"News risk score {news_risk_score:.0f}")
        if news_count > 0:
            parts.append(
                f"based on {news_count} recent headlines ({neg_count} negative, {pos_count} positive, {neu_count} neutral)"
            )
        parts.append(f"sentiment {sentiment_label}")
        if signal_text:
            parts.append(signal_text)
        news_reason = "; ".join(parts)

        advisories: List[Dict[str, Any]] = []

        indicators = {
            "news_risk_score": news_risk_score,
            "sentiment_score": sent_score,
            "sentiment": sentiment_label,
            "news_count": news_count,
            "positive_count": pos_count,
            "negative_count": neg_count,
            "neutral_count": neu_count,
        }

        if news_risk_score >= 75.0:
            severity = "high"
            if news_risk_score >= 85.0:
                severity = "critical"

            advisories.append(
                {
                    "id": "NEWS_CONTEXT_INVALIDATED",
                    "strategy_id": "NEWS_EXIT",
                    "kind": "CONTEXT_INVALIDATED",
                    "severity": severity,
                    "enforcement": "ADVISORY_ONLY",
                    "is_exit": True,
                    "symbol": symbol,
                    "direction": direction,
                    "price": price,
                    "entry_price": position.get("entry_price"),
                    "initial_sl": position.get("stop_loss"),
                    "rr_multiple": None,
                    "indicators": indicators,
                    "message": news_reason
                    + ". Consider exiting or hedging the position due to adverse news.",
                    "recommended_actions": [
                        {
                            "action": "EXIT",
                            "description": "Consider closing most or all of the position at current market price.",
                        },
                        {
                            "action": "TIGHTEN_SL",
                            "description": "If not exiting fully, tighten stop just beyond key technical levels.",
                        },
                    ],
                    "recommended_exit_price": price,
                    "news_reason": news_reason,
                    "news_risk_score": news_risk_score,
                    "type": "NEWS_STRATEGY_ADVISORY",
                    "urgency": "CRITICAL" if severity == "critical" else "HIGH",
                }
            )
        else:
            advisories.append(
                {
                    "id": "NEWS_PARTIAL_PROFIT",
                    "strategy_id": "NEWS_EXIT",
                    "kind": "PARTIAL_PROFIT",
                    "severity": "warning",
                    "enforcement": "ADVISORY_ONLY",
                    "is_exit": True,
                    "symbol": symbol,
                    "direction": direction,
                    "price": price,
                    "entry_price": position.get("entry_price"),
                    "initial_sl": position.get("stop_loss"),
                    "rr_multiple": None,
                    "indicators": indicators,
                    "message": news_reason
                    + ". Consider partial profit booking and tightening stop.",
                    "recommended_actions": [
                        {
                            "action": "PARTIAL_BOOK",
                            "description": "Book partial profits (e.g. 25-50%) to de-risk against news.",
                        },
                        {
                            "action": "TIGHTEN_SL",
                            "description": "Tighten stop-loss to reduce downside if news impact worsens.",
                        },
                    ],
                    "recommended_exit_price": price,
                    "news_reason": news_reason,
                    "news_risk_score": news_risk_score,
                    "type": "NEWS_STRATEGY_ADVISORY",
                    "urgency": "MEDIUM",
                }
            )

        return advisories

    async def _evaluate_sr_exit_advisories_for_position(
        self,
        symbol: str,
        current_price: float,
        position: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Evaluate S/R-based SR_EXIT advisories for a position.

        Uses multi-timeframe (D/W/M/Y) S/R levels to suggest partial
        exits near strong resistance and context invalidation when key
        supports are broken.
        """

        if not position:
            return []

        try:
            price = float(current_price or 0.0)
        except Exception:
            return []

        if price <= 0.0:
            return []

        mode = str(position.get('mode') or '').title() or 'Intraday'
        # Start with Intraday/Swing; other modes can be enabled later.
        if mode not in ['Intraday', 'Swing']:
            return []

        # Mode- and timeframe-aware thresholds (percent distances).
        # Intraday: tighter thresholds, especially on Daily/Weekly.
        # Swing: slightly wider bands, giving more room for noise.
        if mode == 'Intraday':
            near_thresholds = {'D': 0.7, 'W': 0.8, 'M': 0.9, 'Y': 1.0}
            break_margins = {'D': 0.3, 'W': 0.35, 'M': 0.4, 'Y': 0.5}
        else:  # Swing
            near_thresholds = {'D': 0.8, 'W': 1.0, 'M': 1.2, 'Y': 1.5}
            break_margins = {'D': 0.5, 'W': 0.7, 'M': 1.0, 'Y': 1.2}

        direction = (position.get('direction') or 'LONG').upper()

        labels = {'D': 'Daily', 'W': 'Weekly', 'M': 'Monthly', 'Y': 'Yearly'}
        timeframes = ('D', 'W', 'M', 'Y')

        near_zones: List[str] = []
        broken_zones: List[str] = []

        for scope in timeframes:
            near_thr = float(near_thresholds.get(scope, 0.7))
            break_margin = float(break_margins.get(scope, 0.3))

            try:
                levels = await support_resistance_service.get_levels(symbol, scope)
            except Exception as e:
                logger.error(
                    "[AutoMonitoring] SR levels fetch failed for %s/%s: %s",
                    symbol,
                    scope,
                    e,
                    exc_info=True,
                )
                continue

            if levels is None:
                continue

            try:
                r1 = float(levels.r1)
                s1 = float(levels.s1)
            except Exception:
                continue

            def _pct_dist(level: float) -> float:
                return abs(price - level) / price * 100.0 if level > 0 else 999.0

            dist_r1 = _pct_dist(r1)
            dist_s1 = _pct_dist(s1)

            label = labels.get(scope, scope)

            if direction == 'LONG':
                # Near resistance (good place to take partial profits).
                if dist_r1 <= near_thr:
                    near_zones.append(f"{label} R1")

                # Break of support S1 (context invalidation).
                if s1 > 0 and price < s1 * (1 - break_margin / 100.0):
                    broken_zones.append(f"{label} S1")
            else:  # SHORT
                # Near support (good place to take partial profits on shorts).
                if dist_s1 <= near_thr:
                    near_zones.append(f"{label} S1")

                # Break of resistance R1 against the short.
                if r1 > 0 and price > r1 * (1 + break_margin / 100.0):
                    broken_zones.append(f"{label} R1")

        advisories: List[Dict[str, Any]] = []

        if near_zones:
            severity = 'info'
            if any('Weekly' in z or 'Monthly' in z for z in near_zones):
                severity = 'warning'
            if any('Yearly' in z for z in near_zones):
                severity = 'high'

            sr_reason = "Price near " + ", ".join(near_zones)

            advisories.append(
                {
                    'id': 'SR_PARTIAL_PROFIT',
                    'strategy_id': 'SR_EXIT',
                    'kind': 'PARTIAL_PROFIT',
                    'severity': severity,
                    'enforcement': 'ADVISORY_ONLY',
                    'is_exit': True,
                    'symbol': symbol,
                    'direction': direction,
                    'price': price,
                    'entry_price': position.get('entry_price'),
                    'initial_sl': position.get('stop_loss'),
                    'rr_multiple': None,
                    'indicators': {},
                    'message': f"{sr_reason}. Consider partial booking and tightening stop.",
                    'recommended_actions': [
                        {
                            'action': 'PARTIAL_BOOK',
                            'description': 'Book partial profits (e.g. 25-50%) around current price.',
                        },
                        {
                            'action': 'TIGHTEN_SL',
                            'description': 'Tighten stop-loss closer to the nearest support/resistance level.',
                        },
                    ],
                    'recommended_exit_price': price,
                    'sr_reason': sr_reason,
                    'type': 'SR_STRATEGY_ADVISORY',
                    'urgency': 'MEDIUM' if severity in ('warning', 'high') else 'LOW',
                }
            )

        if broken_zones:
            severity = 'high'
            if any('Monthly' in z or 'Yearly' in z for z in broken_zones):
                severity = 'critical'

            if direction == 'LONG':
                sr_reason = "Support broken at " + ", ".join(broken_zones)
            else:
                sr_reason = "Resistance broken at " + ", ".join(broken_zones)

            advisories.append(
                {
                    'id': 'SR_CONTEXT_INVALIDATED',
                    'strategy_id': 'SR_EXIT',
                    'kind': 'CONTEXT_INVALIDATED',
                    'severity': severity,
                    'enforcement': 'ADVISORY_ONLY',
                    'is_exit': True,
                    'symbol': symbol,
                    'direction': direction,
                    'price': price,
                    'entry_price': position.get('entry_price'),
                    'initial_sl': position.get('stop_loss'),
                    'rr_multiple': None,
                    'indicators': {},
                    'message': f"{sr_reason}. Consider exiting or tightening stop aggressively.",
                    'recommended_actions': [
                        {
                            'action': 'EXIT',
                            'description': 'Consider closing most or all of the position at current market price.',
                        },
                        {
                            'action': 'TIGHTEN_SL',
                            'description': 'If not exiting fully, tighten stop just beyond the broken level.',
                        },
                    ],
                    'recommended_exit_price': price,
                    'sr_reason': sr_reason,
                    'type': 'SR_STRATEGY_ADVISORY',
                    'urgency': 'HIGH' if severity in ('high', 'critical') else 'MEDIUM',
                }
            )

        return advisories

    async def _evaluate_s2_advisories_for_position(
        self,
        symbol: str,
        current_price: float,
        position: Dict[str, Any],
        strategy_profile: Dict[str, Any],
    ) -> List[StrategyAdvisory]:
        """Evaluate S2 (EMA trend pullback) advisory rules for a position.

        Uses intraday candles (currently 5m via timeframe='1D') as an
        approximation for the 1m/5m design, and focuses on detecting when
        the EMA 50/100/150 trend stack breaks for the position direction.
        """

        from ..services.chart_data_service import chart_data_service

        entry_price = float(position.get('entry_price') or 0.0)
        stop_loss = position.get('stop_loss')
        try:
            initial_sl = float(stop_loss) if stop_loss is not None else 0.0
        except Exception:
            initial_sl = 0.0

        if entry_price <= 0 or initial_sl <= 0:
            return []

        direction = (position.get('direction') or 'LONG').upper()

        # Use 5m intraday candles (timeframe='1D') as proxy
        try:
            chart = await chart_data_service.fetch_chart_data(symbol, '1D')
        except Exception as e:
            logger.error("[AutoMonitoring] S2 chart fetch failed for %s: %s", symbol, e, exc_info=True)
            return []

        candles = (chart or {}).get('candles') or []
        if not candles or len(candles) < 160:
            return []

        df = pd.DataFrame(candles)
        required_cols = {'open', 'high', 'low', 'close'}
        if not required_cols.issubset(df.columns):
            return []

        df = df.sort_values('time').reset_index(drop=True)
        closes = df['close']

        ema_fast = closes.ewm(span=50, adjust=False).mean()
        ema_mid = closes.ewm(span=100, adjust=False).mean()
        ema_slow = closes.ewm(span=150, adjust=False).mean()

        if len(ema_slow.dropna()) == 0:
            return []

        last_idx = len(df) - 1
        lookback_bars = int(strategy_profile.get('indicator_params', {}).get('ema', {}).get('slope_lookback_bars', 5) or 5)
        lookback_idx = max(0, last_idx - lookback_bars)

        ef_now = float(ema_fast.iloc[last_idx])
        em_now = float(ema_mid.iloc[last_idx])
        es_now = float(ema_slow.iloc[last_idx])

        ef_prev = float(ema_fast.iloc[lookback_idx])
        em_prev = float(ema_mid.iloc[lookback_idx])
        es_prev = float(ema_slow.iloc[lookback_idx])

        spread_now = ef_now - es_now
        spread_prev = ef_prev - es_prev

        # Trend / stack validation
        up_stack = ef_now > em_now > es_now and ef_now > ef_prev and em_now > em_prev and es_now > es_prev and spread_now > spread_prev
        down_stack = ef_now < em_now < es_now and ef_now < ef_prev and em_now < em_prev and es_now < es_prev and spread_now < spread_prev

        last_price = float(current_price or df['close'].iloc[-1])
        rr_multiple = self._compute_rr_multiple(direction, last_price, entry_price, initial_sl)

        advisories: List[StrategyAdvisory] = []

        # 1) Partial profit advisory at configured R-multiple (default 2.5R)
        exit_criteria = strategy_profile.get('exit_criteria', {}) or {}
        try:
            partial_rr = float(exit_criteria.get('partial_booking_at_rr', 2.5))
        except Exception:
            partial_rr = 2.5

        if rr_multiple is not None and rr_multiple >= partial_rr:
            advisories.append(
                StrategyAdvisory(
                    id='S2_PARTIAL_PROFIT',
                    strategy_id=strategy_profile.get('id', 'S2_EMA_TREND_PULLBACK'),
                    kind='PARTIAL_PROFIT',
                    severity='info',
                    enforcement='ADVISORY_ONLY',
                    is_exit=True,
                    symbol=symbol,
                    direction=direction,
                    price=last_price,
                    entry_price=entry_price,
                    initial_sl=initial_sl or None,
                    rr_multiple=rr_multiple,
                    indicators={
                        'ema_50': ef_now,
                        'ema_100': em_now,
                        'ema_150': es_now,
                        'ema_50_prev': ef_prev,
                        'ema_100_prev': em_prev,
                        'ema_150_prev': es_prev,
                    },
                    message=f"Price reached {rr_multiple:.1f}R in S2 trend; consider partial booking and tightening stop.",
                    recommended_actions=[
                        {
                            'action': 'PARTIAL_BOOK',
                            'description': 'Book partial profits (e.g. 50%) around current price.',
                        },
                        {
                            'action': 'TIGHTEN_SL',
                            'description': 'Move stop-loss closer to breakeven or a recent swing low/high.',
                        },
                    ],
                    recommended_exit_price=last_price,
                )
            )

        # 2) Context invalidation when EMA stack/slope breaks
        context_invalidated = False
        if direction == 'LONG':
            # Setup broken when bullish EMA stack no longer holds
            if not up_stack:
                context_invalidated = True
        else:
            # SHORT: setup broken when bearish EMA stack no longer holds
            if not down_stack:
                context_invalidated = True

        if context_invalidated:
            try:
                sr_reason = (
                    f"EMA stack broken: EMA50={float(ef_now):.2f} (prev {float(ef_prev):.2f}), "
                    f"EMA100={float(em_now):.2f} (prev {float(em_prev):.2f}), "
                    f"EMA150={float(es_now):.2f} (prev {float(es_prev):.2f})"
                )
            except Exception:
                sr_reason = None

            advisories.append(
                StrategyAdvisory(
                    id='S2_CONTEXT_INVALIDATED',
                    strategy_id=strategy_profile.get('id', 'S2_EMA_TREND_PULLBACK'),
                    kind='CONTEXT_INVALIDATED',
                    severity='high',
                    enforcement='ADVISORY_ONLY',
                    is_exit=True,
                    symbol=symbol,
                    direction=direction,
                    price=last_price,
                    entry_price=entry_price,
                    initial_sl=initial_sl or None,
                    rr_multiple=rr_multiple,
                    indicators={
                        'ema_50': ef_now,
                        'ema_100': em_now,
                        'ema_150': es_now,
                        'ema_50_prev': ef_prev,
                        'ema_100_prev': em_prev,
                        'ema_150_prev': es_prev,
                    },
                    message='S2 context invalidated: EMA 50/100/150 stack or slope broke. Consider exiting or tightening stop.',
                    sr_reason=sr_reason,
                    recommended_actions=[
                        {
                            'action': 'EXIT',
                            'description': 'Consider closing most or all of the position at current market price.',
                        },
                        {
                            'action': 'TIGHTEN_SL',
                            'description': 'If not exiting fully, tighten stop-loss beyond the most recent swing.',
                        },
                    ],
                    recommended_exit_price=last_price,
                )
            )

        return advisories

    async def _evaluate_s3_advisories_for_position(
        self,
        symbol: str,
        current_price: float,
        position: Dict[str, Any],
        strategy_profile: Dict[str, Any],
    ) -> List[StrategyAdvisory]:
        """Evaluate S3 (Bollinger Bands trend pullback) advisory rules.

        Approximates the 5m/15m design using:
        - timeframe='1D' (5m) for Intraday
        - timeframe='1M' (hourly) for Swing
        and flags when the mid-band trend flips against the position.
        """

        from ..services.chart_data_service import chart_data_service

        entry_price = float(position.get('entry_price') or 0.0)
        stop_loss = position.get('stop_loss')
        try:
            initial_sl = float(stop_loss) if stop_loss is not None else 0.0
        except Exception:
            initial_sl = 0.0

        if entry_price <= 0 or initial_sl <= 0:
            return []

        direction = (position.get('direction') or 'LONG').upper()
        mode = str(position.get('mode') or 'Swing')

        timeframe = '1M' if mode == 'Swing' else '1D'

        try:
            chart = await chart_data_service.fetch_chart_data(symbol, timeframe)
        except Exception as e:
            logger.error("[AutoMonitoring] S3 chart fetch failed for %s: %s", symbol, e, exc_info=True)
            return []

        candles = (chart or {}).get('candles') or []
        if not candles or len(candles) < 40:
            return []

        df = pd.DataFrame(candles)
        required_cols = {'open', 'high', 'low', 'close'}
        if not required_cols.issubset(df.columns):
            return []

        df = df.sort_values('time').reset_index(drop=True)
        closes = df['close']

        length = int(strategy_profile.get('indicator_params', {}).get('bb', {}).get('length', 20) or 20)
        mult = float(strategy_profile.get('indicator_params', {}).get('bb', {}).get('multiplier', 2.0) or 2.0)

        mid = closes.rolling(window=length, min_periods=length).mean()
        std = closes.rolling(window=length, min_periods=length).std(ddof=0)

        if mid.isna().all() or std.isna().all():
            return []

        upper = mid + mult * std
        lower = mid - mult * std

        last_idx = len(df) - 1
        lookback_bars = int(strategy_profile.get('indicator_params', {}).get('bb', {}).get('slope_lookback_bars', 5) or 5)
        lookback_idx = max(0, last_idx - lookback_bars)

        mb_now = float(mid.iloc[last_idx])
        mb_prev = float(mid.iloc[lookback_idx])

        bb_trend_up = mb_now > mb_prev
        bb_trend_down = mb_now < mb_prev

        last_price = float(current_price or df['close'].iloc[-1])
        rr_multiple = self._compute_rr_multiple(direction, last_price, entry_price, initial_sl)

        advisories: List[StrategyAdvisory] = []

        band_extended = False
        try:
            upper_now = float(upper.iloc[last_idx])
            lower_now = float(lower.iloc[last_idx])
            if direction == 'LONG' and last_price >= upper_now * 0.98:
                band_extended = True
            elif direction != 'LONG' and last_price <= lower_now * 1.02:
                band_extended = True
        except Exception:
            band_extended = False

        if band_extended:
            try:
                advisories.append(
                    StrategyAdvisory(
                        id='S3_BAND_STRETCHED',
                        strategy_id=strategy_profile.get('id', 'S3_BB_TREND_PULLBACK'),
                        kind='PRICE_STRETCHED',
                        severity='warning',
                        enforcement='ADVISORY_ONLY',
                        is_exit=False,
                        symbol=symbol,
                        direction=direction,
                        price=last_price,
                        entry_price=entry_price,
                        initial_sl=initial_sl or None,
                        rr_multiple=rr_multiple,
                        indicators={
                            'bb_mid': mb_now,
                            'bb_upper': float(upper.iloc[last_idx]),
                            'bb_lower': float(lower.iloc[last_idx]),
                        },
                        message='Price stretched near Bollinger band; trend may be extended. Monitor for mean reversion or pullback.',
                        recommended_exit_price=last_price,
                    )
                )
            except Exception:
                pass

        context_invalidated = False
        if direction == 'LONG':
            # Long setup breaks when Bollinger mid-band starts pointing down
            if bb_trend_down:
                context_invalidated = True
        else:
            # Short setup breaks when mid-band starts pointing up
            if bb_trend_up:
                context_invalidated = True

        if context_invalidated:
            try:
                if bb_trend_down:
                    bb_state = 'down'
                elif bb_trend_up:
                    bb_state = 'up'
                else:
                    bb_state = 'flat'
                sr_reason = f"Bollinger mid-band trend turned {bb_state}: mid={float(mb_now):.2f} (prev {float(mb_prev):.2f})"
            except Exception:
                sr_reason = None

            advisories.append(
                StrategyAdvisory(
                    id='S3_CONTEXT_INVALIDATED',
                    strategy_id=strategy_profile.get('id', 'S3_BB_TREND_PULLBACK'),
                    kind='CONTEXT_INVALIDATED',
                    severity='high',
                    enforcement='ADVISORY_ONLY',
                    symbol=symbol,
                    direction=direction,
                    price=last_price,
                    entry_price=entry_price,
                    initial_sl=initial_sl or None,
                    rr_multiple=rr_multiple,
                    indicators={
                        'bb_mid': mb_now,
                        'bb_mid_prev': mb_prev,
                        'bb_trend': 'up' if bb_trend_up else 'down' if bb_trend_down else 'flat',
                        'bb_upper': float(upper.iloc[last_idx]) if not np.isnan(upper.iloc[last_idx]) else None,
                        'bb_lower': float(lower.iloc[last_idx]) if not np.isnan(lower.iloc[last_idx]) else None,
                    },
                    message='S3 context invalidated: Bollinger mid-band trend flipped against the position. Consider exiting or tightening stop.',
                    sr_reason=sr_reason,
                    recommended_actions=[
                        {
                            'action': 'EXIT',
                            'description': 'Consider closing most or all of the position at current market price.',
                        },
                        {
                            'action': 'TIGHTEN_SL',
                            'description': 'If not exiting fully, trail stop just beyond the opposite band or recent swing.',
                        },
                    ],
                    recommended_exit_price=last_price,
                )
            )

        return advisories

    def _compute_heikin_ashi(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute Heikin-Ashi candles from standard OHLC data."""

        if df.empty:
            return df

        ha_df = df.copy()
        ha_close = (df['open'] + df['high'] + df['low'] + df['close']) / 4.0

        ha_open = ha_close.copy()
        ha_open.iloc[0] = (df['open'].iloc[0] + df['close'].iloc[0]) / 2.0
        for i in range(1, len(df)):
            ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2.0

        ha_high = pd.concat([df['high'], ha_open, ha_close], axis=1).max(axis=1)
        ha_low = pd.concat([df['low'], ha_open, ha_close], axis=1).min(axis=1)

        ha_df['ha_open'] = ha_open
        ha_df['ha_close'] = ha_close
        ha_df['ha_high'] = ha_high
        ha_df['ha_low'] = ha_low

        return ha_df

    def _compute_rsi(self, closes: pd.Series, length: int = 14) -> pd.Series:  # type: ignore[name-defined]
        """Compute RSI over a closing-price series."""

        if len(closes) < length + 1:
            return pd.Series(dtype=float)

        delta = closes.diff()
        gain = delta.where(delta > 0.0, 0.0)
        loss = -delta.where(delta < 0.0, 0.0)

        avg_gain = gain.rolling(window=length, min_periods=length).mean()
        avg_loss = loss.rolling(window=length, min_periods=length).mean()

        rs = avg_gain / avg_loss.replace(0.0, np.nan)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return rsi

    def _compute_psar(
        self,
        high: pd.Series,  # type: ignore[name-defined]
        low: pd.Series,  # type: ignore[name-defined]
        step: float = 0.02,
        max_step: float = 0.2,
    ) -> pd.Series:  # type: ignore[name-defined]
        """Compute Parabolic SAR (PSAR) for a series of highs and lows.

        This is a simple implementation sufficient for generating advisory
        levels; it is not intended for tick-perfect replication of broker
        studies.
        """

        if high.empty or low.empty or len(high) != len(low):
            return pd.Series(dtype=float)

        psar = high.copy()
        psar.iloc[:] = np.nan

        # Initial trend direction: assume uptrend
        bull = True
        af = step
        ep = low.iloc[0]
        psar.iloc[0] = low.iloc[0] - (high.iloc[0] - low.iloc[0])

        for i in range(1, len(high)):
            prev_psar = psar.iloc[i - 1]

            if bull:
                psar.iloc[i] = prev_psar + af * (ep - prev_psar)
                psar.iloc[i] = min(psar.iloc[i], low.iloc[i - 1], low.iloc[i])

                if high.iloc[i] > ep:
                    ep = high.iloc[i]
                    af = min(af + step, max_step)

                if low.iloc[i] < psar.iloc[i]:
                    bull = False
                    psar.iloc[i] = ep
                    ep = low.iloc[i]
                    af = step
            else:
                psar.iloc[i] = prev_psar + af * (ep - prev_psar)
                psar.iloc[i] = max(psar.iloc[i], high.iloc[i - 1], high.iloc[i])

                if low.iloc[i] < ep:
                    ep = low.iloc[i]
                    af = min(af + step, max_step)

                if high.iloc[i] > psar.iloc[i]:
                    bull = True
                    psar.iloc[i] = ep
                    ep = high.iloc[i]
                    af = step

        return psar

    def _compute_rr_multiple(
        self,
        direction: str,
        price: float,
        entry_price: float,
        initial_sl: float,
    ) -> Optional[float]:
        """Compute R-multiple (reward/risk) for the current price.

        Returns None if required inputs are missing or invalid.
        """

        try:
            entry = float(entry_price)
            sl = float(initial_sl)
            px = float(price)
        except Exception:
            return None

        if entry <= 0 or sl <= 0:
            return None

        if direction == 'LONG':
            risk = entry - sl
            if risk <= 0:
                return None
            return (px - entry) / risk
        else:
            risk = sl - entry
            if risk <= 0:
                return None
            return (entry - px) / risk
    
    def _calculate_monitoring_score(self, alerts: List[Dict], health_score: float) -> float:
        """Calculate monitoring score"""
        
        if not alerts:
            return health_score
        
        critical_count = len([a for a in alerts if a.get('urgency') == 'CRITICAL'])
        high_count = len([a for a in alerts if a.get('urgency') == 'HIGH'])
        
        score = health_score
        score -= (critical_count * 15)
        score -= (high_count * 10)
        
        return max(0, min(100, score))
    
    def _get_urgency_level(self, alerts: List[Dict]) -> str:
        """Determine overall urgency level"""
        
        if any(a.get('urgency') == 'CRITICAL' for a in alerts):
            return 'CRITICAL'
        elif any(a.get('urgency') == 'HIGH' for a in alerts):
            return 'HIGH'
        elif any(a.get('urgency') == 'MEDIUM' for a in alerts):
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def _calculate_confidence(self, alerts: List[Dict], has_position: bool) -> str:
        """Calculate confidence level"""
        
        if has_position and len(alerts) >= 2:
            return 'High'
        elif len(alerts) >= 1:
            return 'Medium'
        else:
            return 'Low'
    
    def _generate_signals(self, alerts: List[Dict]) -> List[Dict]:
        """Generate monitoring signals"""
        
        signals = []
        
        sorted_alerts = sorted(
            alerts,
            key=lambda x: {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}.get(x.get('urgency', 'LOW'), 4)
        )
        
        for alert in sorted_alerts[:3]:
            signals.append({
                'type': alert.get('type', 'ALERT'),
                'signal': alert.get('urgency', 'LOW'),
                'description': alert.get('message', '')
            })
        
        return signals
    
    def _generate_reasoning(
        self,
        alerts: List[Dict],
        health_score: float,
        has_position: bool
    ) -> str:
        """Generate reasoning for monitoring results"""
        
        if not alerts:
            return f"No alerts. All parameters within normal ranges. Health: {health_score:.0f}/100."
        
        urgency = self._get_urgency_level(alerts)
        
        if has_position:
            return f"{urgency} attention required. {len(alerts)} alert(s). Position health: {health_score:.0f}/100. {alerts[0].get('action', '')}"
        else:
            return f"{len(alerts)} opportunity alert(s). {alerts[0].get('message', '')}. {alerts[0].get('action', '')}"
    
    # ==================== SCALPING MONITORING (NEW) ====================
    
    async def monitor_scalping_positions(self, manual_trigger: bool = False) -> Dict[str, Any]:
        """
        Monitor all active scalping positions and detect exits.
        
        Called every 5 minutes by scheduler (or manually triggered).
        Checks:
        - Target hit
        - Stop loss hit
        - Time-based exit (60 min max)
        - Trailing stop activation
        - EOD auto-exit
        
        Args:
            manual_trigger: If True, user manually triggered monitoring
            
        Returns:
            Summary of monitoring results
        """
        from ..services.scalping_exit_tracker import scalping_exit_tracker
        from ..services.chart_data_service import chart_data_service
        
        logger.info(f"[ScalpingMonitor] {'Manual' if manual_trigger else 'Auto'} monitoring started")
        
        # Get active scalping positions (entries without exits in last 2 hours)
        active_positions = scalping_exit_tracker.get_active_positions(lookback_hours=2)
        
        if not active_positions:
            logger.info("[ScalpingMonitor] No active scalping positions")
            return {
                'status': 'success',
                'active_positions': 0,
                'exits_detected': 0,
                'exits': []
            }
        
        logger.info(f"[ScalpingMonitor] Monitoring {len(active_positions)} active positions")
        
        exits_detected = []
        
        # Monitor each position
        for position in active_positions:
            try:
                exit_signal = await self._check_scalping_exit_conditions(position)

                if exit_signal:
                    # Log exit
                    scalping_exit_tracker.log_exit(exit_signal)
                    exits_detected.append(exit_signal)

                    logger.info(
                        f"[EXIT] {position['symbol']}: {exit_signal['exit_reason']} @ {exit_signal['exit_price']}, return: {exit_signal['return_pct']:.2f}%"
                    )

                # S2 strategy advisories for scalping positions (advisory-only)
                try:
                    from ..services.strategy_exit_tracker import strategy_exit_tracker

                    entry_price = position.get('entry_price')
                    exit_strategy = position.get('exit_strategy') or {}
                    stop_price = exit_strategy.get('stop_loss_price')

                    if entry_price and stop_price:
                        rec_text = str(position.get('recommendation', '')).lower()
                        direction = 'LONG' if 'buy' in rec_text else 'SHORT'

                        s2_position_ctx = {
                            'entry_price': entry_price,
                            'stop_loss': stop_price,
                            'direction': direction,
                            'mode': 'Scalping',
                            'source': 'scalping',
                        }

                        s2_profile = {
                            'id': 'S2_EMA_TREND_PULLBACK',
                            'name': 'EMA Trend Pullback (Scalping)',
                            'mode': 'Scalping',
                            'timeframe': '1m',
                            'indicator_params': {
                                'ema': {
                                    'fast': 50,
                                    'mid': 100,
                                    'slow': 150,
                                    'slope_lookback_bars': 5,
                                }
                            },
                            'exit_criteria': {
                                'slope_lookback_bars': 5,
                            },
                        }

                        s2_advisories = await self._evaluate_s2_advisories_for_position(
                            symbol=position['symbol'],
                            current_price=0.0,
                            position=s2_position_ctx,
                            strategy_profile=s2_profile,
                        )

                        for adv in s2_advisories:
                            if adv.recommended_exit_price is None:
                                continue

                            strategy_exit_tracker.log_advisory(
                                adv.dict(),
                                {
                                    'symbol': position['symbol'],
                                    'universe': None,
                                    'mode': 'Scalping',
                                    'direction': direction,
                                    'entry_price': entry_price,
                                    'source': 'scalping',
                                },
                            )
                except Exception as e_adv:
                    logger.error(
                        "[ScalpingMonitor] S2 advisory evaluation failed for %s: %s",
                        position.get('symbol'),
                        e_adv,
                        exc_info=True,
                    )

            except Exception as e:
                logger.error(f"[ScalpingMonitor] Error checking {position['symbol']}: {e}", exc_info=True)
        
        logger.info(f"[ScalpingMonitor] Completed: {len(exits_detected)} exits detected")
        
        return {
            'status': 'success',
            'active_positions': len(active_positions),
            'exits_detected': len(exits_detected),
            'exits': exits_detected,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
    
    async def _check_scalping_exit_conditions(self, position: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Check if exit conditions met for a scalping position.
        
        Args:
            position: Position dict with entry details and exit strategy
            
        Returns:
            Exit signal dict if condition met, None otherwise
        """
        from ..services.chart_data_service import chart_data_service
        
        symbol = position['symbol']
        entry_price = position.get('entry_price', 0)
        entry_time = position.get('entry_time')
        recommendation = position.get('recommendation', 'Buy')
        exit_strategy = position.get('exit_strategy', {})
        
        if not entry_price or not exit_strategy:
            return None
        
        # Get current price
        try:
            chart_data = await chart_data_service.fetch_chart_data(symbol, '1M')
            if not chart_data or 'current' not in chart_data:
                return None
            
            current_price = chart_data['current'].get('price', 0)
            if current_price == 0:
                return None
            
        except Exception as e:
            logger.error(f"[ScalpingMonitor] Failed to get price for {symbol}: {e}")
            return None
        
        # Calculate return
        if recommendation == 'Buy':
            return_pct = ((current_price - entry_price) / entry_price) * 100
        else:  # Sell
            return_pct = ((entry_price - current_price) / entry_price) * 100
        
        # Calculate hold duration using timezone-aware UTC datetimes
        entry_dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
        if entry_dt.tzinfo is None:
            entry_dt = entry_dt.replace(tzinfo=timezone.utc)
        else:
            entry_dt = entry_dt.astimezone(timezone.utc)
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        hold_duration_mins = (now - entry_dt).total_seconds() / 60
        
        # Extract exit parameters
        target_pct = exit_strategy.get('target_pct', 0.5)
        stop_pct = exit_strategy.get('stop_pct', 0.5)
        max_hold_mins = exit_strategy.get('max_hold_mins', 60)
        trailing_stop = exit_strategy.get('trailing_stop', {})
        
        # Check exit conditions
        exit_reason = None

        # 1. TARGET HIT
        if return_pct >= target_pct:
            exit_reason = 'TARGET_HIT'
            exit_price = exit_strategy.get('target_price', current_price)
        
        # 2. STOP LOSS HIT
        elif return_pct <= -stop_pct:
            exit_reason = 'STOP_LOSS'
        
        # 3. TIME-BASED EXIT (60 mins max)
        elif hold_duration_mins >= max_hold_mins:
            exit_reason = 'TIME_EXIT'
        
        # 4. TRAILING STOP (if profitable)
        elif trailing_stop.get('enabled', False):
            activation_pct = trailing_stop.get('activation_pct', 0.2)
            trail_distance_pct = trailing_stop.get('trail_distance_pct', 0.3)
            
            if return_pct >= activation_pct:
                # Trailing stop activated - check if pulled back
                # (In production, track highest profit; for now use simple check)
                if return_pct < (activation_pct - trail_distance_pct):
                    exit_reason = 'TRAILING_STOP'
        
        # 5. EOD AUTO-EXIT (Market closed)
        ist_now = now_ist()
        market_open = is_cash_market_open_ist(ist_now)

        if not market_open and exit_reason is None:
            exit_reason = 'EOD_AUTO_EXIT'
        
        # If exit condition met, create exit signal
        if exit_reason:
            # Clamp exit price to configured target/stop levels where applicable
            exit_price = current_price
            try:
                if exit_reason == 'STOP_LOSS':
                    sl_price = exit_strategy.get('stop_loss_price')
                    if sl_price:
                        exit_price = float(sl_price)
                elif exit_reason == 'TARGET_HIT':
                    tgt_price = exit_strategy.get('target_price')
                    if tgt_price:
                        exit_price = float(tgt_price)
            except Exception:
                exit_price = current_price

            # Recompute return based on effective exit price so P&L reflects plan
            if recommendation == 'Buy':
                return_pct = ((exit_price - entry_price) / entry_price) * 100
            else:
                return_pct = ((entry_price - exit_price) / entry_price) * 100

            return {
                'symbol': symbol,
                'entry_time': entry_time,
                'entry_price': entry_price,
                'exit_time': now.isoformat().replace('+00:00', 'Z'),
                'exit_price': exit_price,
                'exit_reason': exit_reason,
                'return_pct': round(return_pct, 2),
                'hold_duration_mins': round(hold_duration_mins, 1),
                'mode': 'Scalping',
                'recommendation': recommendation
            }
        
        return None


# Global instance
auto_monitoring_agent = AutoMonitoringAgent()
