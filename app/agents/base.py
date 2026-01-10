"""
Base Agent Class
All agents inherit from this base class
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class AgentResult(BaseModel):
    """Standard result format for all agents"""
    agent_type: str
    symbol: str
    score: float = Field(ge=0, le=100, description="Score from 0-100")
    confidence: str = Field(description="High, Medium, or Low")
    signals: List[Dict[str, Any]] = Field(default_factory=list)
    reasoning: str = Field(description="Plain English explanation")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    
    class Config:
        json_schema_extra = {
            "example": {
                "agent_type": "technical",
                "symbol": "RELIANCE",
                "score": 78.5,
                "confidence": "High",
                "signals": [
                    {"type": "RSI", "value": 55, "signal": "Neutral"},
                    {"type": "MACD", "value": "Bullish Crossover", "signal": "Buy"}
                ],
                "reasoning": "Stock shows bullish MACD crossover with RSI in neutral zone",
                "metadata": {"timeframe": "1D"},
                "timestamp": "2024-11-10T10:30:00Z"
            }
        }


class BaseAgent(ABC):
    """
    Base class for all agents.
    Each agent must implement the analyze() method.
    """
    
    def __init__(self, name: str, weight: float = 1.0):
        self.name = name
        self.weight = weight  # Weight in blend score calculation
        self.cache = {}  # Simple in-memory cache
    
    @abstractmethod
    async def analyze(
        self, 
        symbol: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Analyze a symbol and return structured result.
        
        Args:
            symbol: Stock symbol (e.g., 'RELIANCE', 'NIFTY')
            context: Additional context (global market, user prefs, etc.)
            
        Returns:
            AgentResult with score, signals, reasoning
        """
        pass
    
    def normalize_score(self, raw_score: float, min_val: float, max_val: float) -> float:
        """
        Normalize a raw score to 0-100 range.
        
        Args:
            raw_score: Original score
            min_val: Minimum possible value
            max_val: Maximum possible value
            
        Returns:
            Normalized score between 0 and 100
        """
        if max_val == min_val:
            return 50.0
        
        normalized = ((raw_score - min_val) / (max_val - min_val)) * 100
        return max(0.0, min(100.0, normalized))
    
    def calculate_confidence(self, score: float, signal_count: int) -> str:
        """
        Calculate confidence level based on score and signal agreement.
        
        Args:
            score: Agent score (0-100)
            signal_count: Number of confirming signals
            
        Returns:
            "High", "Medium", or "Low"
        """
        if score >= 75 and signal_count >= 3:
            return "High"
        elif score >= 50 and signal_count >= 2:
            return "Medium"
        else:
            return "Low"
    
    async def get_cached_result(self, symbol: str, ttl: int = 300) -> Optional[AgentResult]:
        """
        Get cached result if available and not expired.
        
        Args:
            symbol: Stock symbol
            ttl: Time to live in seconds (default 5 min)
            
        Returns:
            Cached AgentResult or None
        """
        cache_key = f"{self.name}:{symbol}"
        if cache_key in self.cache:
            cached_time, result = self.cache[cache_key]
            age = (datetime.utcnow() - cached_time).total_seconds()
            if age < ttl:
                return result
        return None
    
    async def cache_result(self, symbol: str, result: AgentResult):
        """Store result in cache with timestamp"""
        cache_key = f"{self.name}:{symbol}"
        self.cache[cache_key] = (datetime.utcnow(), result)
    
    def __repr__(self):
        return f"<{self.__class__.__name__}(name={self.name}, weight={self.weight})>"
