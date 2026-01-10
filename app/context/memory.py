"""
Memory Manager
Handles short-term and long-term memory for agents
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import json
from pathlib import Path


class MemoryManager:
    """
    Manages memory for agents and user sessions.
    - Short-term: In-memory session data
    - Long-term: Persistent storage in database/files
    """
    
    def __init__(self, storage_path: str = "cache/memory"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Short-term memory (current session)
        self.session_memory: Dict[str, Any] = {}
        
        # Working memory (temporary context)
        self.working_memory: Dict[str, Any] = {}
        
        # Cache for frequently accessed data
        self.cache: Dict[str, tuple[datetime, Any]] = {}
    
    # ==================== Short-term Memory ====================
    
    def set_session_data(self, key: str, value: Any, ttl: int = 3600):
        """
        Store data in current session.
        
        Args:
            key: Memory key
            value: Data to store
            ttl: Time to live in seconds (default 1 hour)
        """
        expiry = datetime.utcnow() + timedelta(seconds=ttl)
        self.session_memory[key] = {
            'value': value,
            'expiry': expiry,
            'created_at': datetime.utcnow()
        }
    
    def get_session_data(self, key: str, default: Any = None) -> Any:
        """
        Retrieve data from current session.
        
        Args:
            key: Memory key
            default: Default value if not found or expired
            
        Returns:
            Stored value or default
        """
        if key not in self.session_memory:
            return default
        
        item = self.session_memory[key]
        
        # Check expiry
        if datetime.utcnow() > item['expiry']:
            del self.session_memory[key]
            return default
        
        return item['value']
    
    def clear_session(self):
        """Clear all session memory"""
        self.session_memory.clear()
    
    # ==================== Working Memory ====================
    
    def set_context(self, context_type: str, data: Dict[str, Any]):
        """
        Set working context for agents.
        
        Args:
            context_type: Type of context ('global', 'policy', 'user', etc.)
            data: Context data
        """
        self.working_memory[context_type] = {
            'data': data,
            'updated_at': datetime.utcnow()
        }
    
    def get_context(self, context_type: str) -> Optional[Dict[str, Any]]:
        """
        Get working context.
        
        Args:
            context_type: Type of context to retrieve
            
        Returns:
            Context data or None
        """
        if context_type in self.working_memory:
            return self.working_memory[context_type]['data']
        return None
    
    def get_all_context(self) -> Dict[str, Any]:
        """Get all working context as a single dictionary"""
        return {
            ctx_type: item['data']
            for ctx_type, item in self.working_memory.items()
        }
    
    # ==================== Long-term Memory ====================
    
    async def store_analysis(
        self, 
        symbol: str, 
        agent_type: str, 
        result: Dict[str, Any]
    ):
        """
        Store agent analysis for historical reference.
        
        Args:
            symbol: Stock symbol
            agent_type: Type of agent
            result: Analysis result
        """
        filepath = self.storage_path / f"analyses_{symbol}.jsonl"
        
        record = {
            'symbol': symbol,
            'agent_type': agent_type,
            'result': result,
            'timestamp': datetime.utcnow().isoformat() + "Z"
        }
        
        # Append to JSONL file
        with open(filepath, 'a') as f:
            f.write(json.dumps(record) + '\n')
    
    async def get_historical_analyses(
        self, 
        symbol: str, 
        agent_type: Optional[str] = None,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Retrieve historical analyses for a symbol.
        
        Args:
            symbol: Stock symbol
            agent_type: Filter by agent type (None = all agents)
            days: Number of days to look back
            
        Returns:
            List of historical analyses
        """
        filepath = self.storage_path / f"analyses_{symbol}.jsonl"
        
        if not filepath.exists():
            return []
        
        cutoff = datetime.utcnow() - timedelta(days=days)
        results = []
        
        with open(filepath, 'r') as f:
            for line in f:
                try:
                    record = json.loads(line)
                    timestamp = datetime.fromisoformat(record['timestamp'].replace('Z', ''))
                    
                    # Filter by date
                    if timestamp < cutoff:
                        continue
                    
                    # Filter by agent type if specified
                    if agent_type and record['agent_type'] != agent_type:
                        continue
                    
                    results.append(record)
                except Exception:
                    continue
        
        return results
    
    # ==================== User Preferences ====================
    
    async def store_user_preference(self, user_id: str, pref_key: str, value: Any):
        """
        Store user trading preferences.
        
        Args:
            user_id: User identifier
            pref_key: Preference key (e.g., 'risk_profile', 'preferred_sectors')
            value: Preference value
        """
        filepath = self.storage_path / f"user_{user_id}.json"
        
        # Load existing preferences
        if filepath.exists():
            with open(filepath, 'r') as f:
                prefs = json.load(f)
        else:
            prefs = {}
        
        # Update preference
        prefs[pref_key] = {
            'value': value,
            'updated_at': datetime.utcnow().isoformat() + "Z"
        }
        
        # Save
        with open(filepath, 'w') as f:
            json.dump(prefs, f, indent=2)
    
    async def get_user_preference(
        self, 
        user_id: str, 
        pref_key: str, 
        default: Any = None
    ) -> Any:
        """
        Get user preference.
        
        Args:
            user_id: User identifier
            pref_key: Preference key
            default: Default value if not found
            
        Returns:
            Preference value or default
        """
        filepath = self.storage_path / f"user_{user_id}.json"
        
        if not filepath.exists():
            return default
        
        with open(filepath, 'r') as f:
            prefs = json.load(f)
        
        if pref_key in prefs:
            return prefs[pref_key]['value']
        
        return default
    
    async def get_all_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """Get all preferences for a user"""
        filepath = self.storage_path / f"user_{user_id}.json"
        
        if not filepath.exists():
            return {}
        
        with open(filepath, 'r') as f:
            prefs = json.load(f)
        
        return {key: item['value'] for key, item in prefs.items()}
    
    # ==================== Caching ====================
    
    def cache_set(self, key: str, value: Any, ttl: int = 300):
        """
        Store value in cache with TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (default 5 min)
        """
        expiry = datetime.utcnow() + timedelta(seconds=ttl)
        self.cache[key] = (expiry, value)
    
    def cache_get(self, key: str, default: Any = None) -> Any:
        """
        Get cached value if not expired.
        
        Args:
            key: Cache key
            default: Default value if not found or expired
            
        Returns:
            Cached value or default
        """
        if key not in self.cache:
            return default
        
        expiry, value = self.cache[key]
        
        if datetime.utcnow() > expiry:
            del self.cache[key]
            return default
        
        return value
    
    def cache_clear(self):
        """Clear all cache"""
        self.cache.clear()
    
    # ==================== Utility Methods ====================
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory usage statistics"""
        return {
            'session_items': len(self.session_memory),
            'working_contexts': len(self.working_memory),
            'cached_items': len(self.cache),
            'storage_path': str(self.storage_path),
            'storage_files': len(list(self.storage_path.glob('*')))
        }
    
    def cleanup_expired(self):
        """Remove expired items from session and cache"""
        now = datetime.utcnow()
        
        # Clean session memory
        expired_keys = [
            key for key, item in self.session_memory.items()
            if now > item['expiry']
        ]
        for key in expired_keys:
            del self.session_memory[key]
        
        # Clean cache
        expired_cache = [
            key for key, (expiry, _) in self.cache.items()
            if now > expiry
        ]
        for key in expired_cache:
            del self.cache[key]
        
        return {
            'session_cleaned': len(expired_keys),
            'cache_cleaned': len(expired_cache)
        }


# Global memory manager instance
memory_manager = MemoryManager()
