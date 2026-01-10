"""
Context Storage
Database storage for agent analyses and context data
"""

import sqlite3
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import json
from pathlib import Path


class ContextStorage:
    """
    SQLite-based storage for agent analyses, user preferences, and context.
    """
    
    def __init__(self, db_path: str = "cache/context.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Agent analyses table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                agent_type TEXT NOT NULL,
                score REAL,
                confidence TEXT,
                signals TEXT,  -- JSON
                reasoning TEXT,
                metadata TEXT,  -- JSON
                global_context TEXT,  -- JSON
                policy_context TEXT,  -- JSON
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_symbol_date 
            ON agent_analyses(symbol, created_at DESC)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_symbol 
            ON agent_analyses(agent_type, symbol, created_at DESC)
        """)
        
        # Context memory table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS context_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                context_type TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,  -- JSON
                ttl INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_context_key 
            ON context_memory(context_type, key)
        """)
        
        # User preferences table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                pref_key TEXT NOT NULL,
                pref_value TEXT,  -- JSON
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, pref_key)
            )
        """)
        
        # Agent learning table (for future ML improvements)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_learnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_type TEXT NOT NULL,
                pattern_recognized TEXT,
                accuracy REAL,
                sample_size INTEGER,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    # ==================== Agent Analyses ====================
    
    def store_analysis(
        self,
        symbol: str,
        agent_type: str,
        score: float,
        confidence: str,
        signals: List[Dict[str, Any]],
        reasoning: str,
        metadata: Optional[Dict[str, Any]] = None,
        global_context: Optional[Dict[str, Any]] = None,
        policy_context: Optional[Dict[str, Any]] = None
    ):
        """Store agent analysis in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO agent_analyses 
            (symbol, agent_type, score, confidence, signals, reasoning, 
             metadata, global_context, policy_context)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol,
            agent_type,
            score,
            confidence,
            json.dumps(signals),
            reasoning,
            json.dumps(metadata or {}),
            json.dumps(global_context or {}),
            json.dumps(policy_context or {})
        ))
        
        conn.commit()
        conn.close()
    
    def get_latest_analysis(
        self,
        symbol: str,
        agent_type: str,
        max_age_minutes: int = 30
    ) -> Optional[Dict[str, Any]]:
        """Get latest analysis for symbol/agent if not too old"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)
        
        cursor.execute("""
            SELECT * FROM agent_analyses
            WHERE symbol = ? AND agent_type = ?
              AND created_at > ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (symbol, agent_type, cutoff))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'id': row['id'],
                'symbol': row['symbol'],
                'agent_type': row['agent_type'],
                'score': row['score'],
                'confidence': row['confidence'],
                'signals': json.loads(row['signals']),
                'reasoning': row['reasoning'],
                'metadata': json.loads(row['metadata']),
                'global_context': json.loads(row['global_context']),
                'policy_context': json.loads(row['policy_context']),
                'created_at': row['created_at']
            }
        
        return None
    
    def get_historical_analyses(
        self,
        symbol: str,
        agent_type: Optional[str] = None,
        days: int = 30,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get historical analyses for a symbol"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        if agent_type:
            cursor.execute("""
                SELECT * FROM agent_analyses
                WHERE symbol = ? AND agent_type = ?
                  AND created_at > ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (symbol, agent_type, cutoff, limit))
        else:
            cursor.execute("""
                SELECT * FROM agent_analyses
                WHERE symbol = ?
                  AND created_at > ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (symbol, cutoff, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                'id': row['id'],
                'symbol': row['symbol'],
                'agent_type': row['agent_type'],
                'score': row['score'],
                'confidence': row['confidence'],
                'signals': json.loads(row['signals']),
                'reasoning': row['reasoning'],
                'metadata': json.loads(row['metadata']),
                'created_at': row['created_at']
            }
            for row in rows
        ]
    
    # ==================== Context Memory ====================
    
    def set_context(
        self,
        context_type: str,
        key: str,
        value: Any,
        ttl: int = 3600
    ):
        """Store context data with TTL"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        
        # Delete existing
        cursor.execute("""
            DELETE FROM context_memory
            WHERE context_type = ? AND key = ?
        """, (context_type, key))
        
        # Insert new
        cursor.execute("""
            INSERT INTO context_memory 
            (context_type, key, value, ttl, expires_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            context_type,
            key,
            json.dumps(value),
            ttl,
            expires_at
        ))
        
        conn.commit()
        conn.close()
    
    def get_context(
        self,
        context_type: str,
        key: str,
        default: Any = None
    ) -> Any:
        """Get context data if not expired"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT value, expires_at FROM context_memory
            WHERE context_type = ? AND key = ?
              AND expires_at > ?
        """, (context_type, key, datetime.utcnow()))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return json.loads(row['value'])
        
        return default
    
    def cleanup_expired_context(self):
        """Remove expired context entries"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM context_memory
            WHERE expires_at < ?
        """, (datetime.utcnow(),))
        
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted
    
    # ==================== User Preferences ====================
    
    def set_user_preference(self, user_id: str, pref_key: str, pref_value: Any):
        """Store user preference"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO user_preferences
            (user_id, pref_key, pref_value, updated_at)
            VALUES (?, ?, ?, ?)
        """, (
            user_id,
            pref_key,
            json.dumps(pref_value),
            datetime.utcnow()
        ))
        
        conn.commit()
        conn.close()
    
    def get_user_preference(
        self,
        user_id: str,
        pref_key: str,
        default: Any = None
    ) -> Any:
        """Get user preference"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT pref_value FROM user_preferences
            WHERE user_id = ? AND pref_key = ?
        """, (user_id, pref_key))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return json.loads(row['pref_value'])
        
        return default
    
    def get_all_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """Get all preferences for a user"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT pref_key, pref_value FROM user_preferences
            WHERE user_id = ?
        """, (user_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return {
            row['pref_key']: json.loads(row['pref_value'])
            for row in rows
        }
    
    # ==================== Statistics ====================
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Count analyses
        cursor.execute("SELECT COUNT(*) FROM agent_analyses")
        total_analyses = cursor.fetchone()[0]
        
        # Count context entries
        cursor.execute("SELECT COUNT(*) FROM context_memory")
        total_context = cursor.fetchone()[0]
        
        # Count users
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM user_preferences")
        total_users = cursor.fetchone()[0]
        
        # Database size
        cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
        db_size = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_analyses': total_analyses,
            'total_context_entries': total_context,
            'total_users': total_users,
            'database_size_bytes': db_size,
            'database_size_mb': round(db_size / 1024 / 1024, 2)
        }


# Global storage instance
context_storage = ContextStorage()
