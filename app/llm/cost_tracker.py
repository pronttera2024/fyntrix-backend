"""
Cost Tracker for OpenAI API Usage
Monitors spending and prevents budget overruns
"""

import sqlite3
from typing import Dict, Any
from datetime import datetime, timedelta
from pathlib import Path


class CostTracker:
    """
    Track OpenAI API usage and costs.
    Provides budget alerts and usage statistics.
    """
    
    # Model pricing (per 1K tokens)
    PRICING = {
        'gpt-3.5-turbo': {'input': 0.0015, 'output': 0.002},
        'gpt-4-turbo': {'input': 0.01, 'output': 0.03},
        'gpt-4': {'input': 0.03, 'output': 0.06}
    }
    
    def __init__(self, db_path: str = "cache/llm_costs.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize cost tracking database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS llm_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model TEXT NOT NULL,
                tokens_input INTEGER,
                tokens_output INTEGER,
                cost_usd REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_created_at
            ON llm_requests(created_at DESC)
        """)
        
        conn.commit()
        conn.close()
    
    def calculate_cost(
        self,
        model: str,
        tokens_input: int,
        tokens_output: int
    ) -> float:
        """
        Calculate cost for a request.
        
        Args:
            model: Model name
            tokens_input: Input tokens
            tokens_output: Output tokens
            
        Returns:
            Cost in USD
        """
        if model not in self.PRICING:
            # Default to GPT-4 pricing if unknown model
            pricing = self.PRICING['gpt-4']
        else:
            pricing = self.PRICING[model]
        
        cost_input = (tokens_input / 1000) * pricing['input']
        cost_output = (tokens_output / 1000) * pricing['output']
        
        return cost_input + cost_output
    
    async def log_request(
        self,
        model: str,
        tokens_input: int,
        tokens_output: int
    ):
        """Log API request and cost (async)"""
        cost = self.calculate_cost(model, tokens_input, tokens_output)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO llm_requests (model, tokens_input, tokens_output, cost_usd)
            VALUES (?, ?, ?, ?)
        """, (model, tokens_input, tokens_output, cost))
        
        conn.commit()
        conn.close()
        
        print(f"  💵 Cost: ${cost:.4f} ({tokens_input}+{tokens_output} tokens)")
    
    def log_request_sync(
        self,
        model: str,
        tokens_input: int,
        tokens_output: int
    ):
        """Log API request and cost (sync)"""
        cost = self.calculate_cost(model, tokens_input, tokens_output)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO llm_requests (model, tokens_input, tokens_output, cost_usd)
            VALUES (?, ?, ?, ?)
        """, (model, tokens_input, tokens_output, cost))
        
        conn.commit()
        conn.close()
    
    async def get_daily_spend(self) -> float:
        """Get total spend for today"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.utcnow().date()
        
        cursor.execute("""
            SELECT COALESCE(SUM(cost_usd), 0) FROM llm_requests
            WHERE DATE(created_at) = ?
        """, (today,))
        
        total = cursor.fetchone()[0]
        conn.close()
        
        return float(total)
    
    async def get_usage_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get usage statistics for past N days"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        # Total cost
        cursor.execute("""
            SELECT 
                COUNT(*) as total_requests,
                SUM(tokens_input) as total_input_tokens,
                SUM(tokens_output) as total_output_tokens,
                SUM(cost_usd) as total_cost
            FROM llm_requests
            WHERE created_at > ?
        """, (cutoff,))
        
        totals = cursor.fetchone()
        
        # By model
        cursor.execute("""
            SELECT 
                model,
                COUNT(*) as requests,
                SUM(cost_usd) as cost
            FROM llm_requests
            WHERE created_at > ?
            GROUP BY model
            ORDER BY cost DESC
        """, (cutoff,))
        
        by_model = cursor.fetchall()
        
        # Daily breakdown
        cursor.execute("""
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as requests,
                SUM(cost_usd) as cost
            FROM llm_requests
            WHERE created_at > ?
            GROUP BY DATE(created_at)
            ORDER BY date DESC
        """, (cutoff,))
        
        daily = cursor.fetchall()
        
        conn.close()
        
        return {
            'period_days': days,
            'total_requests': totals['total_requests'],
            'total_input_tokens': totals['total_input_tokens'],
            'total_output_tokens': totals['total_output_tokens'],
            'total_cost_usd': round(totals['total_cost'] or 0, 2),
            'avg_cost_per_request': round(
                (totals['total_cost'] or 0) / max(totals['total_requests'], 1), 4
            ),
            'by_model': [
                {
                    'model': row['model'],
                    'requests': row['requests'],
                    'cost_usd': round(row['cost'], 2)
                }
                for row in by_model
            ],
            'daily_breakdown': [
                {
                    'date': row['date'],
                    'requests': row['requests'],
                    'cost_usd': round(row['cost'], 2)
                }
                for row in daily
            ]
        }
    
    async def check_budget_available(self, daily_budget: float) -> bool:
        """
        Check if daily budget has been exceeded.
        
        Args:
            daily_budget: Daily budget limit in USD
            
        Returns:
            True if budget available, False if exceeded
        """
        today_spend = await self.get_daily_spend()
        return today_spend < daily_budget
    
    async def get_budget_alert(self, daily_budget: float) -> Dict[str, Any]:
        """
        Get budget alert status.
        
        Args:
            daily_budget: Daily budget limit in USD
            
        Returns:
            Alert status and details
        """
        today_spend = await self.get_daily_spend()
        percentage = (today_spend / daily_budget) * 100 if daily_budget > 0 else 0
        
        if percentage >= 100:
            status = 'EXCEEDED'
        elif percentage >= 80:
            status = 'WARNING'
        elif percentage >= 50:
            status = 'CAUTION'
        else:
            status = 'OK'
        
        return {
            'status': status,
            'spent_usd': round(today_spend, 2),
            'budget_usd': daily_budget,
            'remaining_usd': round(max(daily_budget - today_spend, 0), 2),
            'percentage_used': round(percentage, 1)
        }
    
    def cleanup_old_records(self, days: int = 90):
        """Remove records older than N days"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        cursor.execute("""
            DELETE FROM llm_requests
            WHERE created_at < ?
        """, (cutoff,))
        
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted


# Global cost tracker instance
cost_tracker = CostTracker()
