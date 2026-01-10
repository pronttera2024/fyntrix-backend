"""
Policy/Macro Agent - Policy & Macroeconomic Impact Analysis
Tracks RBI, Fed, government policies, M&A, corporate actions, and macro trends
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import asyncio

from .base import BaseAgent, AgentResult
from ..services.news_aggregator import aggregate_news


class PolicyMacroAgent(BaseAgent):
    """
    Analyzes policy announcements and macroeconomic factors.
    
    Key Functions:
    1. RBI Policy Tracking (repo rate, CRR, SLR, stance)
    2. Fed Policy Tracking (interest rates, QE/QT)
    3. Government Policy (budget, subsidies, tariffs, PLI schemes)
    4. Corporate Actions (M&A, buybacks, dividends, bonus)
    5. Economic Indicators (GDP, inflation, PMI, IIP)
    6. Sector-Specific Policies
    """
    
    POLICY_KEYWORDS = {
        'rbi': ['rbi', 'repo rate', 'monetary policy', 'reserve bank'],
        'fed': ['federal reserve', 'fed', 'fomc', 'powell'],
        'fiscal': ['budget', 'subsidy', 'tariff', 'gst', 'tax'],
        'corporate': ['merger', 'acquisition', 'buyback', 'dividend', 'split'],
        'macro': ['gdp', 'inflation', 'cpi', 'pmi', 'iip', 'wpi']
    }
    
    def __init__(self, weight: float = 0.10):
        super().__init__(name="policy", weight=weight)
    
    async def analyze(
        self, 
        symbol: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """Analyze policy and macro impact on symbol"""
        
        # Fetch recent news
        news = await aggregate_news(category="general", limit=30)
        
        # Categorize news
        policy_news = self._categorize_news(news, symbol)
        
        # Analyze each category
        rbi_impact = self._analyze_rbi_policy(policy_news.get('rbi', []))
        fed_impact = self._analyze_fed_policy(policy_news.get('fed', []))
        fiscal_impact = self._analyze_fiscal_policy(policy_news.get('fiscal', []), symbol)
        corporate_impact = self._analyze_corporate_actions(policy_news.get('corporate', []), symbol)
        macro_impact = self._analyze_macro_indicators(policy_news.get('macro', []))
        
        # Aggregate signals
        signals = []
        signals.extend(rbi_impact['signals'])
        signals.extend(fed_impact['signals'])
        signals.extend(fiscal_impact['signals'])
        signals.extend(corporate_impact['signals'])
        signals.extend(macro_impact['signals'])
        
        # Calculate score
        scores = [
            rbi_impact['score'],
            fed_impact['score'],
            fiscal_impact['score'],
            corporate_impact['score'],
            macro_impact['score']
        ]
        score = sum(scores) / len(scores) if scores else 50.0
        
        # Confidence
        confidence = self.calculate_confidence(score, len(signals))
        
        # Reasoning
        reasoning = self._generate_reasoning(
            symbol, rbi_impact, fed_impact, fiscal_impact, 
            corporate_impact, macro_impact
        )
        
        # Metadata
        metadata = {
            'rbi_stance': rbi_impact.get('stance', 'Neutral'),
            'fed_stance': fed_impact.get('stance', 'Neutral'),
            'policy_tailwinds': fiscal_impact.get('tailwinds', []),
            'policy_headwinds': fiscal_impact.get('headwinds', []),
            'upcoming_events': self._get_upcoming_events(policy_news)
        }
        
        return AgentResult(
            agent_type="policy",
            symbol=symbol,
            score=round(score, 2),
            confidence=confidence,
            signals=signals,
            reasoning=reasoning,
            metadata=metadata
        )
    
    def _categorize_news(self, news: List[Dict], symbol: str) -> Dict[str, List[Dict]]:
        """Categorize news into policy types"""
        categorized = {
            'rbi': [],
            'fed': [],
            'fiscal': [],
            'corporate': [],
            'macro': []
        }
        
        for item in news:
            title = item.get('title', '').lower()
            desc = item.get('description', '').lower()
            text = f"{title} {desc}"
            
            # Check if symbol-specific
            symbol_mentioned = symbol.lower() in text
            
            for category, keywords in self.POLICY_KEYWORDS.items():
                if any(kw in text for kw in keywords):
                    item['symbol_specific'] = symbol_mentioned
                    categorized[category].append(item)
        
        return categorized
    
    def _analyze_rbi_policy(self, news: List[Dict]) -> Dict[str, Any]:
        """Analyze RBI policy impact"""
        if not news:
            return {'signals': [], 'score': 50.0, 'stance': 'Neutral'}
        
        signals = []
        
        # Check for recent policy changes
        for item in news[:5]:
            title = item.get('title', '').lower()
            
            if 'rate cut' in title or 'reduce' in title:
                signals.append({
                    'type': 'RBI_POLICY',
                    'value': 'Rate cut',
                    'signal': 'Positive (Liquidity boost)'
                })
                score = 70
                stance = 'Accommodative'
            elif 'rate hike' in title or 'increase' in title:
                signals.append({
                    'type': 'RBI_POLICY',
                    'value': 'Rate hike',
                    'signal': 'Negative (Tightening)'
                })
                score = 35
                stance = 'Hawkish'
            else:
                signals.append({
                    'type': 'RBI_POLICY',
                    'value': 'Status quo',
                    'signal': 'Neutral'
                })
                score = 50
                stance = 'Neutral'
            
            break  # Use most recent
        
        if not signals:
            score = 50
            stance = 'Neutral'
        
        return {'signals': signals, 'score': score, 'stance': stance}
    
    def _analyze_fed_policy(self, news: List[Dict]) -> Dict[str, Any]:
        """Analyze Fed policy impact"""
        if not news:
            return {'signals': [], 'score': 50.0, 'stance': 'Neutral'}
        
        signals = []
        
        for item in news[:5]:
            title = item.get('title', '').lower()
            
            if 'cut' in title or 'dovish' in title:
                signals.append({
                    'type': 'FED_POLICY',
                    'value': 'Dovish stance',
                    'signal': 'Positive for EM'
                })
                score = 65
                stance = 'Dovish'
            elif 'hike' in title or 'hawkish' in title:
                signals.append({
                    'type': 'FED_POLICY',
                    'value': 'Hawkish stance',
                    'signal': 'Negative for EM'
                })
                score = 40
                stance = 'Hawkish'
            else:
                score = 50
                stance = 'Neutral'
            
            break
        
        if not signals:
            score = 50
            stance = 'Neutral'
        
        return {'signals': signals, 'score': score, 'stance': stance}
    
    def _analyze_fiscal_policy(self, news: List[Dict], symbol: str) -> Dict[str, Any]:
        """Analyze government fiscal policy"""
        if not news:
            return {'signals': [], 'score': 50.0, 'tailwinds': [], 'headwinds': []}
        
        signals = []
        tailwinds = []
        headwinds = []
        symbol_score = 50
        
        for item in news:
            title = item.get('title', '').lower()
            symbol_specific = item.get('symbol_specific', False)
            
            if 'subsidy' in title or 'incentive' in title or 'pli' in title:
                signals.append({
                    'type': 'FISCAL_POLICY',
                    'value': 'Subsidy/Incentive announced',
                    'signal': 'Positive' if symbol_specific else 'Sector Positive'
                })
                tailwinds.append(item.get('title', ''))
                symbol_score += 10 if symbol_specific else 5
            elif 'tariff' in title or 'duty' in title and 'reduce' in title:
                signals.append({
                    'type': 'FISCAL_POLICY',
                    'value': 'Import duty reduced',
                    'signal': 'Negative for local producers'
                })
                headwinds.append(item.get('title', ''))
                symbol_score -= 5
        
        symbol_score = max(0, min(100, symbol_score))
        
        return {
            'signals': signals,
            'score': symbol_score,
            'tailwinds': tailwinds[:3],
            'headwinds': headwinds[:3]
        }
    
    def _analyze_corporate_actions(self, news: List[Dict], symbol: str) -> Dict[str, Any]:
        """Analyze corporate actions"""
        if not news:
            return {'signals': [], 'score': 50.0}
        
        signals = []
        score = 50
        
        for item in news:
            title = item.get('title', '').lower()
            symbol_specific = item.get('symbol_specific', False)
            
            if not symbol_specific:
                continue
            
            if 'buyback' in title:
                signals.append({
                    'type': 'CORPORATE_ACTION',
                    'value': 'Buyback announced',
                    'signal': 'Positive (Shareholder return)'
                })
                score = 75
            elif 'dividend' in title:
                signals.append({
                    'type': 'CORPORATE_ACTION',
                    'value': 'Dividend announced',
                    'signal': 'Positive'
                })
                score = 65
            elif 'merger' in title or 'acquisition' in title:
                signals.append({
                    'type': 'CORPORATE_ACTION',
                    'value': 'M&A activity',
                    'signal': 'Mixed (depends on terms)'
                })
                score = 55
        
        return {'signals': signals, 'score': score}
    
    def _analyze_macro_indicators(self, news: List[Dict]) -> Dict[str, Any]:
        """Analyze macroeconomic indicators"""
        if not news:
            return {'signals': [], 'score': 50.0}
        
        signals = []
        score = 50
        
        for item in news[:10]:
            title = item.get('title', '').lower()
            
            if 'gdp' in title and ('growth' in title or 'increase' in title):
                signals.append({
                    'type': 'MACRO',
                    'value': 'GDP growth positive',
                    'signal': 'Bullish'
                })
                score = 65
            elif 'inflation' in title and ('fall' in title or 'decline' in title):
                signals.append({
                    'type': 'MACRO',
                    'value': 'Inflation declining',
                    'signal': 'Positive'
                })
                score = 60
            elif 'pmi' in title and 'expansion' in title:
                signals.append({
                    'type': 'MACRO',
                    'value': 'PMI in expansion',
                    'signal': 'Positive'
                })
                score = 60
        
        return {'signals': signals, 'score': score}
    
    def _generate_reasoning(
        self, symbol, rbi, fed, fiscal, corporate, macro
    ) -> str:
        """Generate reasoning text"""
        parts = []
        
        if rbi['signals']:
            parts.append(f"RBI stance: {rbi['stance']}")
        if fiscal['tailwinds']:
            parts.append(f"Policy tailwinds: {len(fiscal['tailwinds'])} identified")
        if corporate['signals']:
            parts.append(f"Corporate actions: {len(corporate['signals'])} events")
        
        if parts:
            return f"{symbol} - " + ". ".join(parts) + "."
        else:
            return f"{symbol} - No significant policy/macro events currently impacting this stock."
    
    def _get_upcoming_events(self, policy_news: Dict) -> List[str]:
        """Get upcoming policy events"""
        events = []
        
        # Check for keywords indicating future events
        for category, items in policy_news.items():
            for item in items[:5]:
                title = item.get('title', '').lower()
                if any(word in title for word in ['upcoming', 'scheduled', 'expected', 'next']):
                    events.append(item.get('title', ''))
        
        return events[:5]
