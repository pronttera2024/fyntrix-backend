"""
Agent Coordinator
Orchestrates multiple agents and aggregates their results
"""

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
from .base import BaseAgent, AgentResult


class AgentCoordinator:
    """
    Coordinates execution of multiple agents and aggregates results.
    Implements parallel execution, error handling, and result blending.
    """
    
    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        # 10 Core Scoring Agents (weights sum to 1.00)
        # Trade Strategy, Auto-Monitoring, Personalization are utility agents (weight = 0)
        self.weights: Dict[str, float] = {
            'technical': 0.2233,         # Technical analysis (highest weight)
            'global': 0.12,              # Global market correlations
            'policy': 0.08,              # Policy/macro events
            'options': 0.12,             # Options flow analysis
            'sentiment': 0.12,           # Market sentiment
            'microstructure': 0.0893,    # Order book microstructure
            'risk': 0.08,                # Risk management
            'pattern': 0.1116,           # Pattern recognition (new)
            'regime': 0.0558,            # Market regime detection (new)
            'watchlist': 0.00,           # Watchlist intelligence (monitoring-only, not scored)
            'trade_strategy': 0.00,      # Supra agent (generates strategy, not scored)
            'auto_monitoring': 0.00,     # Utility agent (monitoring/alerts)
            'personalization': 0.00      # Utility agent (user preferences)
        }
    
    def register_agent(self, agent: BaseAgent):
        """Register an agent with the coordinator"""
        self.agents[agent.name] = agent
        # Use ASCII-only logging to avoid Windows console encoding issues
        print(f"[OK] Registered agent: {agent.name}")
    
    def set_weights(self, weights: Dict[str, float]):
        """Update agent weights for scoring"""
        # Validate weights sum to 1.0
        total = sum(weights.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {total}")
        self.weights = weights
    
    async def analyze_symbol(
        self, 
        symbol: str, 
        agent_names: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Run multiple agents in parallel and aggregate results.
        
        Args:
            symbol: Stock symbol to analyze
            agent_names: List of agent names to run (None = all agents)
            context: Additional context to pass to agents
            
        Returns:
            Aggregated analysis with blend score and agent breakdown
        """
        # Determine which agents to run
        if agent_names is None:
            agents_to_run = list(self.agents.values())
        else:
            agents_to_run = [self.agents[name] for name in agent_names if name in self.agents]
        
        if not agents_to_run:
            raise ValueError("No agents available for analysis")
        
        # Build context with global/policy data
        full_context = await self._build_context(symbol, context or {})
        
        # Run agents in parallel
        tasks = [
            self._run_agent_safely(agent, symbol, full_context)
            for agent in agents_to_run
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Filter out failed agents (None results)
        valid_results = [r for r in results if r is not None]
        
        if not valid_results:
            raise RuntimeError("All agents failed to produce results")
        
        # Aggregate results
        aggregated = self._aggregate_results(symbol, valid_results)
        
        return aggregated
    
    async def _run_agent_safely(
        self, 
        agent: BaseAgent, 
        symbol: str, 
        context: Dict[str, Any]
    ) -> Optional[AgentResult]:
        """
        Run a single agent with error handling and timeout.
        
        Args:
            agent: Agent to run
            symbol: Stock symbol
            context: Context data
            
        Returns:
            AgentResult or None if agent fails
        """
        try:
            # Check cache first
            cached = await agent.get_cached_result(symbol)
            if cached:
                print(f"  CACHE {agent.name}: Using cached result")
                return cached
            
            # Run agent with 15 second timeout (increased for data fetching)
            result = await asyncio.wait_for(
                agent.analyze(symbol, context),
                timeout=15.0
            )
            
            # Cache result
            await agent.cache_result(symbol, result)

            print(f"  OK {agent.name}: Score {result.score:.1f}, Confidence {result.confidence}")
            return result
            
        except asyncio.TimeoutError:
            print(f"  TIMEOUT {agent.name}: Timeout (>15s)")
            return None
        except Exception as e:
            print(f"  ERROR {agent.name}: Error - {str(e)[:50]}")
            return None
    
    def _aggregate_results(self, symbol: str, results: List[AgentResult]) -> Dict[str, Any]:
        """
        Aggregate agent results into a single analysis.
        
        Architecture:
        - Only agents with weight > 0 contribute to blend score
        - Zero-weight agents (Trade Strategy, Auto-Monitoring, Personalization) are utility/super agents
        
        Args:
            symbol: Stock symbol
            results: List of valid agent results
            
        Returns:
            Dictionary with blend score and breakdown
        """
        # Calculate weighted blend score (ONLY from scoring agents)
        blend_score = 0.0
        total_weight = 0.0
        
        scoring_agents = []
        utility_agents = []
        
        for result in results:
            agent_name = result.agent_type
            weight = self.weights.get(agent_name, 0.1)
            
            agent_data = {
                'agent': agent_name,
                'score': result.score,
                'confidence': result.confidence,
                'signals': result.signals,
                'reasoning': result.reasoning,
                'metadata': result.metadata,
                'weight': weight
            }
            
            # Only agents with weight > 0 contribute to blend score
            if weight > 0:
                blend_score += result.score * weight
                total_weight += weight
                scoring_agents.append(agent_data)
            else:
                # Zero-weight agents (utility/super agents)
                utility_agents.append(agent_data)
        
        # Combine all agents for breakdown (scoring first, then utility)
        agent_breakdown = scoring_agents + utility_agents
        
        # Normalize if total weight < 1.0 (some agents failed)
        # Note: total_weight should equal sum of all scoring agent weights
        # Agents return scores on 0-100 scale, we weight and normalize
        if total_weight > 0:
            scoring_weights_sum = sum(w for w in self.weights.values() if w > 0)
            # Normalize: if some agents failed, scale up proportionally
            blend_score = (blend_score / total_weight) * scoring_weights_sum
        
        # Calculate overall confidence (ONLY from scoring agents with weight > 0)
        confidence_scores = {'High': 3, 'Medium': 2, 'Low': 1}
        scoring_results = [r for r in results if self.weights.get(r.agent_type, 0) > 0]
        if scoring_results:
            avg_confidence_score = sum(
                confidence_scores.get(r.confidence, 1) for r in scoring_results
            ) / len(scoring_results)
        else:
            avg_confidence_score = 1
        
        if avg_confidence_score >= 2.5:
            overall_confidence = "High"
        elif avg_confidence_score >= 1.5:
            overall_confidence = "Medium"
        else:
            overall_confidence = "Low"
        
        # Determine recommendation
        if blend_score >= 70:
            recommendation = "Strong Buy"
        elif blend_score >= 60:
            recommendation = "Buy"
        elif blend_score >= 50:
            recommendation = "Hold"
        elif blend_score >= 40:
            recommendation = "Sell"
        else:
            recommendation = "Strong Sell"
        
        # Aggregate all signals
        all_signals = []
        for result in results:
            for signal in result.signals:
                all_signals.append({
                    **signal,
                    'agent': result.agent_type
                })
        
        return {
            'symbol': symbol,
            'blend_score': round(blend_score, 2),
            'confidence': overall_confidence,
            'recommendation': recommendation,
            'agent_count': len(results),
            'agents': agent_breakdown,
            'key_signals': all_signals[:10],  # Top 10 signals
            'timestamp': datetime.utcnow().isoformat() + "Z"
        }
    
    async def _build_context(self, symbol: str, base_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build comprehensive context for agents.
        
        Args:
            symbol: Stock symbol
            base_context: Base context provided by caller
            
        Returns:
            Enhanced context with global/policy data
        """
        # Start with base context
        context = {**base_context}
        
        # Add global market context (if Global Agent is registered)
        if 'global' in self.agents:
            try:
                # This will be implemented by Global Market Agent
                # For now, placeholder
                context['global_market'] = {
                    'sentiment': 'Neutral',
                    'us_close': {},
                    'asia_live': {}
                }
            except Exception:
                pass
        
        # Add policy context (if Policy Agent is registered)
        if 'policy' in self.agents:
            try:
                # This will be implemented by Policy/Macro Agent
                # For now, placeholder
                context['policy_events'] = {
                    'recent': [],
                    'upcoming': []
                }
            except Exception:
                pass
        
        # Add timestamp
        context['analysis_time'] = datetime.utcnow().isoformat() + "Z"
        
        return context
    
    async def batch_analyze(
        self, 
        symbols: List[str], 
        agent_names: Optional[List[str]] = None,
        max_concurrent: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Analyze multiple symbols with controlled concurrency.
        
        Args:
            symbols: List of stock symbols
            agent_names: Which agents to run
            max_concurrent: Maximum concurrent analyses
            
        Returns:
            List of aggregated results
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def analyze_with_semaphore(symbol: str):
            async with semaphore:
                try:
                    return await self.analyze_symbol(symbol, agent_names)
                except Exception as e:
                    print(f"ERROR {symbol}: Analysis failed - {e}")
                    return None
        
        tasks = [analyze_with_semaphore(symbol) for symbol in symbols]
        results = await asyncio.gather(*tasks)
        
        # Filter out None results
        return [r for r in results if r is not None]
    
    def get_agent_status(self) -> Dict[str, Any]:
        """Get status of all registered agents"""
        return {
            'total_agents': len(self.agents),
            'agents': [
                {
                    'name': agent.name,
                    'type': agent.__class__.__name__,
                    'weight': self.weights.get(agent.name, 0.0)
                }
                for agent in self.agents.values()
            ],
            'weights': self.weights
        }
