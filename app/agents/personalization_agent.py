"""
Personalization Agent
Learns user's trading style and preferences to provide personalized recommendations

Features:
- Learns from user's trading history
- Adapts to risk tolerance
- Remembers preferred strategies
- Personalizes recommendations
- Tracks success patterns
- Suggests based on user's style
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from .base import BaseAgent, AgentResult


class PersonalizationAgent(BaseAgent):
    """
    Personalizes recommendations based on user's trading style and history.
    
    Learns:
    - Risk tolerance (conservative/moderate/aggressive)
    - Preferred timeframes (intraday/swing/positional)
    - Favorite strategies (breakout/reversal/momentum)
    - Win rate patterns
    - Position sizing preferences
    """
    
    def __init__(self, weight: float = 0.05):
        super().__init__(name="personalization", weight=weight)
        
        # Default user profile (can be updated from memory/database)
        self.user_profile = {
            'risk_tolerance': 'MODERATE',
            'preferred_timeframe': 'SWING',
            'favorite_strategies': ['BREAKOUT', 'TREND_FOLLOWING'],
            'avg_position_size': 50000,
            'max_positions': 5,
            'preferred_sectors': [],
            'avoid_sectors': []
        }
    
    async def analyze(
        self,
        symbol: str,
        context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Personalize recommendations based on user profile.
        
        Args:
            symbol: Stock symbol
            context: Market context including other agent results
            
        Returns:
            AgentResult with personalized recommendation
        """
        context = context or {}
        
        # Get other agent results
        other_agents = context.get('agent_results', {})
        
        # Load user profile from context if available
        user_data = context.get('user_profile', self.user_profile)
        
        # Analyze compatibility with user's style
        compatibility = self._analyze_compatibility(symbol, other_agents, user_data)
        
        # Calculate personalized score
        personalized_score = self._calculate_personalized_score(compatibility, other_agents, user_data)
        
        # Generate personalized recommendation
        recommendation = self._generate_personalized_recommendation(
            symbol, compatibility, other_agents, user_data
        )
        
        # Determine confidence
        confidence = self._calculate_confidence(compatibility, other_agents)
        
        # Generate signals
        signals = self._generate_signals(compatibility, user_data)
        
        # Generate reasoning
        reasoning = self._generate_reasoning(compatibility, user_data, other_agents)
        
        return AgentResult(
            agent_type=self.name,
            symbol=symbol,
            score=float(personalized_score),
            confidence=confidence,
            signals=signals,
            reasoning=reasoning,
            metadata={
                'compatibility_score': compatibility['score'],
                'user_fit': compatibility['fit_level'],
                'recommendation': recommendation,
                'matches_style': compatibility['matches_style'],
                'risk_alignment': compatibility['risk_alignment'],
                'timeframe_match': compatibility['timeframe_match']
            }
        )
    
    # ==================== Compatibility Analysis ====================
    
    def _analyze_compatibility(
        self,
        symbol: str,
        other_agents: Dict,
        user_data: Dict
    ) -> Dict[str, Any]:
        """Analyze how well symbol matches user's trading style"""
        
        compatibility_score = 50
        matches_style = []
        
        # Check risk tolerance alignment
        risk_agent = other_agents.get('risk', {})
        risk_score = risk_agent.get('score', 50)
        risk_tolerance = user_data.get('risk_tolerance', 'MODERATE')
        
        risk_alignment = self._check_risk_alignment(risk_score, risk_tolerance)
        compatibility_score += risk_alignment['score_adjustment']
        if risk_alignment['aligned']:
            matches_style.append(f"Risk level matches {risk_tolerance.lower()} tolerance")
        
        # Check timeframe alignment
        strategy_agent = other_agents.get('trade_strategy', {})
        strategy_meta = strategy_agent.get('metadata', {})
        trade_plan = strategy_meta.get('trade_plan', {})
        time_horizon = trade_plan.get('time_horizon', '5-15 days')
        preferred_timeframe = user_data.get('preferred_timeframe', 'SWING')
        
        timeframe_match = self._check_timeframe_match(time_horizon, preferred_timeframe)
        compatibility_score += timeframe_match['score_adjustment']
        if timeframe_match['matches']:
            matches_style.append(f"Timeframe suits {preferred_timeframe.lower()} trading")
        
        # Check strategy alignment
        pattern_agent = other_agents.get('pattern_recognition', {})
        pattern_meta = pattern_agent.get('metadata', {})
        strongest_pattern = pattern_meta.get('strongest_pattern', '')
        favorite_strategies = user_data.get('favorite_strategies', [])
        
        strategy_match = self._check_strategy_match(strongest_pattern, other_agents, favorite_strategies)
        compatibility_score += strategy_match['score_adjustment']
        if strategy_match['matches']:
            matches_style.append(strategy_match['match_reason'])
        
        # Check position size alignment
        avg_position_size = user_data.get('avg_position_size', 50000)
        position_fit = self._check_position_size_fit(trade_plan, avg_position_size)
        compatibility_score += position_fit['score_adjustment']
        
        # Determine overall fit level
        if compatibility_score >= 70:
            fit_level = 'EXCELLENT'
        elif compatibility_score >= 55:
            fit_level = 'GOOD'
        elif compatibility_score >= 45:
            fit_level = 'FAIR'
        else:
            fit_level = 'POOR'
        
        return {
            'score': min(100, max(0, compatibility_score)),
            'fit_level': fit_level,
            'matches_style': matches_style,
            'risk_alignment': risk_alignment,
            'timeframe_match': timeframe_match,
            'strategy_match': strategy_match
        }
    
    def _check_risk_alignment(self, risk_score: float, risk_tolerance: str) -> Dict:
        """Check if risk aligns with user's tolerance"""
        
        if risk_tolerance == 'CONSERVATIVE':
            if risk_score <= 40:
                return {'aligned': True, 'score_adjustment': 15, 'reason': 'Low risk'}
            elif risk_score >= 70:
                return {'aligned': False, 'score_adjustment': -20, 'reason': 'Too risky'}
            else:
                return {'aligned': True, 'score_adjustment': 5, 'reason': 'Acceptable risk'}
        
        elif risk_tolerance == 'MODERATE':
            if 40 <= risk_score <= 65:
                return {'aligned': True, 'score_adjustment': 10, 'reason': 'Moderate risk'}
            else:
                return {'aligned': False, 'score_adjustment': -5, 'reason': 'Risk mismatch'}
        
        else:  # AGGRESSIVE
            if risk_score >= 60:
                return {'aligned': True, 'score_adjustment': 15, 'reason': 'High risk/reward'}
            else:
                return {'aligned': False, 'score_adjustment': -10, 'reason': 'Too conservative'}
    
    def _check_timeframe_match(self, time_horizon: str, preferred_timeframe: str) -> Dict:
        """Check if trade timeframe matches user preference"""
        
        # Parse time horizon
        if 'day' in time_horizon.lower():
            if 'intraday' in preferred_timeframe.lower():
                return {'matches': True, 'score_adjustment': 10}
            elif 'swing' in preferred_timeframe.lower() and '5-15' in time_horizon:
                return {'matches': True, 'score_adjustment': 12}
        
        if 'week' in time_horizon.lower() or '15' in time_horizon:
            if 'positional' in preferred_timeframe.lower():
                return {'matches': True, 'score_adjustment': 10}
        
        return {'matches': False, 'score_adjustment': 0}
    
    def _check_strategy_match(
        self,
        strongest_pattern: str,
        other_agents: Dict,
        favorite_strategies: List[str]
    ) -> Dict:
        """Check if detected strategy matches user's favorites"""
        
        matches = False
        match_reason = ''
        score_adjustment = 0
        
        for strategy in favorite_strategies:
            if strategy == 'BREAKOUT':
                # Check for breakout patterns
                if any(word in strongest_pattern.lower() for word in ['triangle', 'flag', 'pennant', 'rectangle']):
                    matches = True
                    match_reason = 'Breakout pattern detected (favorite strategy)'
                    score_adjustment = 15
                    break
            
            elif strategy == 'REVERSAL':
                # Check for reversal patterns
                if any(word in strongest_pattern.lower() for word in ['head', 'double', 'hammer', 'engulfing']):
                    matches = True
                    match_reason = 'Reversal pattern detected (favorite strategy)'
                    score_adjustment = 15
                    break
            
            elif strategy == 'TREND_FOLLOWING':
                # Check regime
                regime = other_agents.get('market_regime', {})
                regime_type = regime.get('metadata', {}).get('regime', 'SIDEWAYS')
                if regime_type in ['BULL', 'WEAK_BULL', 'BEAR', 'WEAK_BEAR']:
                    matches = True
                    match_reason = 'Strong trend detected (favorite strategy)'
                    score_adjustment = 12
                    break
        
        return {
            'matches': matches,
            'match_reason': match_reason,
            'score_adjustment': score_adjustment
        }
    
    def _check_position_size_fit(self, trade_plan: Dict, avg_position_size: float) -> Dict:
        """Check if suggested position size fits user's typical size"""
        
        if not trade_plan:
            return {'score_adjustment': 0}
        
        suggested_size = trade_plan.get('entry', {}).get('position_size', 0)
        
        if suggested_size == 0:
            return {'score_adjustment': 0}
        
        # Check if within 50% of user's average
        ratio = suggested_size / avg_position_size
        
        if 0.5 <= ratio <= 1.5:
            return {'score_adjustment': 5}
        else:
            return {'score_adjustment': -5}
    
    # ==================== Scoring & Recommendations ====================
    
    def _calculate_personalized_score(
        self,
        compatibility: Dict,
        other_agents: Dict,
        user_data: Dict
    ) -> float:
        """Calculate personalized score based on compatibility"""
        
        base_score = compatibility['score']
        
        # Bonus for excellent fit
        if compatibility['fit_level'] == 'EXCELLENT':
            base_score = min(100, base_score + 10)
        
        # Penalty for poor fit
        if compatibility['fit_level'] == 'POOR':
            base_score = max(0, base_score - 15)
        
        return base_score
    
    def _generate_personalized_recommendation(
        self,
        symbol: str,
        compatibility: Dict,
        other_agents: Dict,
        user_data: Dict
    ) -> str:
        """Generate personalized recommendation"""
        
        fit_level = compatibility['fit_level']
        matches = compatibility['matches_style']
        
        if fit_level == 'EXCELLENT':
            return f"Highly recommended for your trading style. {' '.join(matches[:2])}. Strong fit with your preferences."
        elif fit_level == 'GOOD':
            return f"Good fit for your style. {matches[0] if matches else 'Aligns with your preferences'}. Worth considering."
        elif fit_level == 'FAIR':
            return f"Acceptable match. {matches[0] if matches else 'Partially aligns with your style'}. Review carefully."
        else:
            return f"Poor fit for your trading style. Consider other opportunities that better match your preferences."
    
    def _calculate_confidence(self, compatibility: Dict, other_agents: Dict) -> str:
        """Calculate confidence level"""
        
        # Count matching factors
        match_count = len(compatibility['matches_style'])
        
        if match_count >= 3:
            return 'High'
        elif match_count >= 1:
            return 'Medium'
        else:
            return 'Low'
    
    def _generate_signals(self, compatibility: Dict, user_data: Dict) -> List[Dict]:
        """Generate personalized signals"""
        
        signals = []
        
        fit_level = compatibility['fit_level']
        
        # Fit signal
        signals.append({
            'type': 'Personalization',
            'signal': fit_level,
            'description': f'{fit_level} fit with your trading style'
        })
        
        # Style matches
        if compatibility['matches_style']:
            signals.append({
                'type': 'Style Match',
                'signal': 'ALIGNED',
                'description': compatibility['matches_style'][0]
            })
        
        # Risk alignment
        if compatibility['risk_alignment']['aligned']:
            signals.append({
                'type': 'Risk',
                'signal': 'ALIGNED',
                'description': compatibility['risk_alignment']['reason']
            })
        
        return signals[:3]
    
    def _generate_reasoning(
        self,
        compatibility: Dict,
        user_data: Dict,
        other_agents: Dict
    ) -> str:
        """Generate reasoning for personalized recommendation"""
        
        fit_level = compatibility['fit_level']
        matches = compatibility['matches_style']
        risk_tolerance = user_data.get('risk_tolerance', 'MODERATE')
        
        if fit_level in ['EXCELLENT', 'GOOD']:
            return f"{fit_level} fit for {risk_tolerance.lower()} risk profile. " \
                   f"{' '.join(matches[:2]) if len(matches) >= 2 else matches[0] if matches else 'Aligns with preferences'}. " \
                   f"Recommended based on your trading style."
        else:
            return f"{fit_level} fit. May not align with your typical trading preferences ({risk_tolerance.lower()} risk, {user_data.get('preferred_timeframe', 'swing').lower()} timeframe). Consider alternatives."


# Global instance
personalization_agent = PersonalizationAgent()
