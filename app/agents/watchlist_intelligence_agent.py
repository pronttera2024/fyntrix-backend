"""
Watchlist Intelligence Agent
Smart watchlist management - recommends stocks to add/remove from watchlist

Features:
- Analyzes current watchlist for opportunities
- Suggests new stocks to add based on user's trading style
- Recommends stocks to remove (low probability setups)
- Monitors watchlist for breakouts/breakdowns
- Ranks watchlist by priority
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from .base import BaseAgent, AgentResult


class WatchlistIntelligenceAgent(BaseAgent):
    """
    Intelligent watchlist management and recommendations.
    
    Capabilities:
    - Watchlist health scoring
    - Stock recommendations (add/remove)
    - Priority ranking
    - Breakout/breakdown alerts
    - Sector diversification analysis
    """
    
    def __init__(self, weight: float = 0.08):
        super().__init__(name="watchlist_intelligence", weight=weight)
        self.max_watchlist_size = 20  # Recommended max watchlist size
        self.min_score_threshold = 45  # Minimum score to keep in watchlist
    
    async def analyze(
        self,
        symbol: str,
        context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Analyze symbol for watchlist suitability.
        
        Args:
            symbol: Stock symbol
            context: Market context including other agent results
            
        Returns:
            AgentResult with watchlist recommendation
        """
        context = context or {}
        
        # Get other agent results for comprehensive analysis
        other_agents = context.get('agent_results', {})
        
        # Analyze watchlist suitability
        suitability = self._analyze_watchlist_suitability(symbol, other_agents)
        
        # Calculate priority score
        priority_score = self._calculate_priority_score(suitability, other_agents)
        
        # Determine action (ADD, KEEP, REMOVE)
        action = self._determine_action(priority_score, suitability)
        
        # Generate recommendation
        recommendation = self._generate_recommendation(symbol, action, suitability, other_agents)
        
        # Calculate confidence
        confidence = self._calculate_confidence(suitability, other_agents)
        
        # Generate signals
        signals = self._generate_signals(action, suitability)
        
        # Generate reasoning
        reasoning = self._generate_reasoning(action, suitability, other_agents)
        
        return AgentResult(
            agent_type=self.name,
            symbol=symbol,
            score=float(priority_score),
            confidence=confidence,
            signals=signals,
            reasoning=reasoning,
            metadata={
                'action': action,
                'priority': suitability.get('priority', 'MEDIUM'),
                'suitability_score': suitability.get('score', 50),
                'recommendation': recommendation,
                'setup_quality': suitability.get('setup_quality', 'MODERATE'),
                'time_sensitivity': suitability.get('time_sensitivity', 'NORMAL'),
                'reasons': suitability.get('reasons', [])
            }
        )
    
    # ==================== Analysis Methods ====================
    
    def _analyze_watchlist_suitability(
        self,
        symbol: str,
        other_agents: Dict
    ) -> Dict[str, Any]:
        """Analyze if symbol is suitable for watchlist"""
        
        suitability_score = 50
        reasons = []
        setup_quality = 'MODERATE'
        time_sensitivity = 'NORMAL'
        
        # Check technical score
        technical = other_agents.get('technical', {})
        tech_score = technical.get('score', 50)
        
        if tech_score >= 70:
            suitability_score += 15
            reasons.append('Strong technical setup')
            setup_quality = 'EXCELLENT'
        elif tech_score >= 60:
            suitability_score += 10
            reasons.append('Good technical setup')
            setup_quality = 'GOOD'
        elif tech_score <= 40:
            suitability_score -= 10
            reasons.append('Weak technical setup')
        
        # Check pattern recognition
        patterns = other_agents.get('pattern_recognition', {})
        pattern_score = patterns.get('score', 50)
        pattern_meta = patterns.get('metadata', {})
        
        if pattern_score >= 65:
            suitability_score += 12
            reasons.append(f"Strong pattern detected: {pattern_meta.get('strongest_pattern', 'N/A')}")
            time_sensitivity = 'HIGH'  # Patterns are time-sensitive
        elif pattern_score >= 55:
            suitability_score += 8
            reasons.append('Pattern forming')
        
        # Check market regime
        regime = other_agents.get('market_regime', {})
        regime_type = regime.get('metadata', {}).get('regime', 'SIDEWAYS')
        regime_score = regime.get('score', 50)
        
        if regime_type in ['BULL', 'WEAK_BULL'] and regime_score >= 60:
            suitability_score += 8
            reasons.append(f'Favorable market regime: {regime_type}')
        elif regime_type in ['BEAR', 'WEAK_BEAR'] and regime_score <= 40:
            suitability_score -= 8
            reasons.append('Unfavorable market regime')
        
        # Check trade strategy
        strategy = other_agents.get('trade_strategy', {})
        strategy_meta = strategy.get('metadata', {})
        trade_plan = strategy_meta.get('trade_plan')
        
        if trade_plan:
            rr_ratio = trade_plan.get('risk_reward', 1)
            if rr_ratio >= 2.5:
                suitability_score += 10
                reasons.append(f'Excellent R:R ratio ({rr_ratio}:1)')
                setup_quality = 'EXCELLENT'
            elif rr_ratio >= 2:
                suitability_score += 5
                reasons.append(f'Good R:R ratio ({rr_ratio}:1)')
        
        # Check sentiment
        sentiment = other_agents.get('sentiment', {})
        sent_score = sentiment.get('score', 50)
        
        if sent_score >= 65:
            suitability_score += 5
            reasons.append('Positive sentiment')
        elif sent_score <= 35:
            suitability_score -= 5
            reasons.append('Negative sentiment')
        
        # Check risk
        risk = other_agents.get('risk', {})
        risk_score = risk.get('score', 50)
        
        if risk_score >= 70:
            suitability_score -= 10
            reasons.append('High risk profile')
        elif risk_score <= 40:
            suitability_score += 5
            reasons.append('Favorable risk profile')
        
        # Determine priority
        if suitability_score >= 70:
            priority = 'HIGH'
        elif suitability_score >= 55:
            priority = 'MEDIUM'
        else:
            priority = 'LOW'
        
        return {
            'score': min(100, max(0, suitability_score)),
            'reasons': reasons,
            'priority': priority,
            'setup_quality': setup_quality,
            'time_sensitivity': time_sensitivity
        }
    
    def _calculate_priority_score(
        self,
        suitability: Dict,
        other_agents: Dict
    ) -> float:
        """Calculate overall priority score"""
        
        base_score = suitability['score']
        
        # Boost for time sensitivity
        if suitability['time_sensitivity'] == 'HIGH':
            base_score = min(100, base_score + 5)
        
        # Boost for excellent setup
        if suitability['setup_quality'] == 'EXCELLENT':
            base_score = min(100, base_score + 5)
        
        return base_score
    
    def _determine_action(
        self,
        priority_score: float,
        suitability: Dict
    ) -> str:
        """Determine watchlist action (ADD, KEEP, REMOVE)"""
        
        if priority_score >= 65:
            return 'ADD'
        elif priority_score >= 45:
            return 'KEEP'
        else:
            return 'REMOVE'
    
    def _generate_recommendation(
        self,
        symbol: str,
        action: str,
        suitability: Dict,
        other_agents: Dict
    ) -> str:
        """Generate detailed recommendation"""
        
        priority = suitability['priority']
        quality = suitability['setup_quality']
        
        if action == 'ADD':
            return f"⭐ ADD to watchlist - {quality} setup with {priority} priority. " \
                   f"Monitor for entry opportunities. {', '.join(suitability['reasons'][:2])}"
        elif action == 'KEEP':
            return f"👁️ KEEP in watchlist - {priority} priority. " \
                   f"Continue monitoring. {suitability['reasons'][0] if suitability['reasons'] else 'Stable setup'}"
        else:  # REMOVE
            return f"❌ REMOVE from watchlist - Low probability setup. " \
                   f"Better opportunities available. Consider re-evaluating later."
    
    def _calculate_confidence(
        self,
        suitability: Dict,
        other_agents: Dict
    ) -> str:
        """Calculate confidence level"""
        
        # Count available agent inputs
        available_agents = len([a for a in other_agents.values() if a.get('score') is not None])
        
        # High confidence if multiple agents agree
        if available_agents >= 5 and len(suitability['reasons']) >= 3:
            return 'High'
        elif available_agents >= 3 and len(suitability['reasons']) >= 2:
            return 'Medium'
        else:
            return 'Low'
    
    def _generate_signals(
        self,
        action: str,
        suitability: Dict
    ) -> List[Dict]:
        """Generate trading signals"""
        
        signals = []
        
        # Action signal
        if action == 'ADD':
            signals.append({
                'type': 'Watchlist',
                'signal': 'ADD',
                'description': f'{suitability["priority"]} priority - {suitability["setup_quality"]} setup'
            })
        elif action == 'KEEP':
            signals.append({
                'type': 'Watchlist',
                'signal': 'KEEP',
                'description': f'{suitability["priority"]} priority - Continue monitoring'
            })
        else:  # REMOVE
            signals.append({
                'type': 'Watchlist',
                'signal': 'REMOVE',
                'description': 'Low probability setup - Remove to declutter'
            })
        
        # Time sensitivity signal
        if suitability['time_sensitivity'] == 'HIGH':
            signals.append({
                'type': 'Alert',
                'signal': 'TIME_SENSITIVE',
                'description': 'Pattern forming - Monitor closely for entry'
            })
        
        # Setup quality signal
        if suitability['setup_quality'] == 'EXCELLENT':
            signals.append({
                'type': 'Quality',
                'signal': 'HIGH_QUALITY_SETUP',
                'description': 'Multiple factors aligned - High conviction trade'
            })
        
        return signals[:3]
    
    def _generate_reasoning(
        self,
        action: str,
        suitability: Dict,
        other_agents: Dict
    ) -> str:
        """Generate reasoning for recommendation"""
        
        priority = suitability['priority']
        quality = suitability['setup_quality']
        reasons = suitability['reasons']
        
        if action == 'ADD':
            return f"{quality} watchlist candidate with {priority} priority. " \
                   f"{' '.join(reasons[:2])}. " \
                   f"Recommended action: Add to watchlist and monitor for entry signals."
        elif action == 'KEEP':
            return f"{priority} priority watchlist item. {quality} setup. " \
                   f"{reasons[0] if reasons else 'Setup remains valid'}. " \
                   f"Continue monitoring for optimal entry."
        else:  # REMOVE
            return f"Weak setup with low probability. " \
                   f"Recommended action: Remove from watchlist to focus on better opportunities. " \
                   f"Can re-evaluate if market conditions improve."


# Global instance
watchlist_intelligence_agent = WatchlistIntelligenceAgent()
