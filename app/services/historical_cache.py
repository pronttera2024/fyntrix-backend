"""
Historical Data Cache Service
Intelligent caching for historical market data to improve performance
"""

import os
import json
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import pandas as pd

logger = logging.getLogger(__name__)


class HistoricalDataCache:
    """
    Intelligent cache for historical OHLC data
    
    Features:
    - File-based persistent caching
    - Smart TTL based on data timeframe
    - Automatic cache invalidation
    - Compression support
    - Memory-efficient storage
    """
    
    def __init__(self, cache_dir: Optional[Path] = None):
        # Cache directory
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent.parent / '.cache' / 'historical'
        
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache metadata file
        self.metadata_file = self.cache_dir / 'metadata.json'
        self.metadata: Dict[str, Any] = {}
        self._load_metadata()
        
        # Cache TTL configuration (in seconds)
        self.ttl_config = {
            '1m': 3600,          # 1 minute data: 1 hour TTL
            '3m': 3600,          # 3 minute data: 1 hour TTL
            '5m': 3600,          # 5 minute data: 1 hour TTL
            '15m': 7200,         # 15 minute data: 2 hours TTL
            '30m': 14400,        # 30 minute data: 4 hours TTL
            '1h': 28800,         # 1 hour data: 8 hours TTL
            '1d': 86400,         # 1 day data: 24 hours TTL (refresh daily)
            'day': 86400,        # day data: 24 hours TTL
            'minute': 3600,      # minute data: 1 hour TTL
            '60minute': 28800,   # 60 minute data: 8 hours TTL
        }
        
        # Statistics
        self.stats = {
            'hits': 0,
            'misses': 0,
            'writes': 0,
            'invalidations': 0
        }
        
        logger.info(f"✓ Historical data cache initialized: {self.cache_dir}")
    
    def _load_metadata(self):
        """Load cache metadata from file"""
        try:
            if self.metadata_file.exists():
                with open(self.metadata_file, 'r') as f:
                    self.metadata = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load cache metadata: {e}")
            self.metadata = {}
    
    def _save_metadata(self):
        """Save cache metadata to file"""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self.metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save cache metadata: {e}")
    
    def _generate_cache_key(
        self,
        symbol: str,
        from_date: datetime,
        to_date: datetime,
        interval: str,
        source: str = "auto"
    ) -> str:
        """
        Generate unique cache key for the data request
        
        Args:
            symbol: Stock symbol
            from_date: Start date
            to_date: End date
            interval: Data interval
            source: Data source (zerodha, yahoo, auto)
            
        Returns:
            Unique cache key
        """
        # Normalize dates to day boundary for daily data
        if interval in ['1d', 'day']:
            from_str = from_date.strftime('%Y-%m-%d')
            to_str = to_date.strftime('%Y-%m-%d')
        else:
            from_str = from_date.strftime('%Y-%m-%d_%H:%M')
            to_str = to_date.strftime('%Y-%m-%d_%H:%M')
        
        # Create key components
        key_string = f"{symbol}_{from_str}_{to_str}_{interval}_{source}"
        
        # Hash for shorter filenames
        key_hash = hashlib.md5(key_string.encode()).hexdigest()[:12]
        
        return f"{symbol}_{interval}_{key_hash}"
    
    def _get_cache_file(self, cache_key: str) -> Path:
        """Get cache file path for a cache key"""
        return self.cache_dir / f"{cache_key}.json"
    
    def _is_cache_valid(self, cache_key: str, interval: str) -> bool:
        """
        Check if cached data is still valid
        
        Args:
            cache_key: Cache key
            interval: Data interval
            
        Returns:
            True if cache is valid
        """
        if cache_key not in self.metadata:
            return False
        
        meta = self.metadata[cache_key]
        cached_at = datetime.fromisoformat(meta.get('cached_at', '2000-01-01'))
        
        # Get TTL for this interval
        ttl = self.ttl_config.get(interval, 3600)  # Default 1 hour
        
        # Check if cache has expired
        age = (datetime.now() - cached_at).total_seconds()
        
        return age < ttl
    
    def get(
        self,
        symbol: str,
        from_date: datetime,
        to_date: datetime,
        interval: str,
        source: str = "auto"
    ) -> Optional[pd.DataFrame]:
        """
        Get historical data from cache
        
        Args:
            symbol: Stock symbol
            from_date: Start date
            to_date: End date
            interval: Data interval
            source: Data source
            
        Returns:
            DataFrame with historical data or None if not cached/expired
        """
        cache_key = self._generate_cache_key(symbol, from_date, to_date, interval, source)
        
        # Check if cache is valid
        if not self._is_cache_valid(cache_key, interval):
            self.stats['misses'] += 1
            logger.debug(f"Cache MISS: {cache_key}")
            return None
        
        # Load from cache file
        try:
            cache_file = self._get_cache_file(cache_key)
            
            if not cache_file.exists():
                self.stats['misses'] += 1
                return None
            
            with open(cache_file, 'r') as f:
                data = json.load(f)
            
            # Convert back to DataFrame
            df = pd.DataFrame(data['data'])
            
            # Convert timestamp back to datetime if needed
            if 'time' in df.columns:
                df['time'] = pd.to_datetime(df['time'])
            
            self.stats['hits'] += 1
            logger.debug(f"Cache HIT: {cache_key} ({len(df)} rows)")
            
            return df
            
        except Exception as e:
            logger.error(f"Error loading from cache: {e}")
            self.stats['misses'] += 1
            return None
    
    def set(
        self,
        symbol: str,
        from_date: datetime,
        to_date: datetime,
        interval: str,
        data: pd.DataFrame,
        source: str = "auto"
    ):
        """
        Store historical data in cache
        
        Args:
            symbol: Stock symbol
            from_date: Start date
            to_date: End date
            interval: Data interval
            data: DataFrame with historical data
            source: Data source
        """
        if data is None or data.empty:
            logger.debug("Not caching empty data")
            return
        
        cache_key = self._generate_cache_key(symbol, from_date, to_date, interval, source)
        
        try:
            # Convert DataFrame to dict for JSON storage
            data_dict = data.to_dict(orient='records')
            
            # Convert datetime objects to strings
            for record in data_dict:
                for key, value in record.items():
                    if isinstance(value, (pd.Timestamp, datetime)):
                        record[key] = value.isoformat()
            
            cache_data = {
                'data': data_dict,
                'row_count': len(data),
                'columns': list(data.columns)
            }
            
            # Save to cache file
            cache_file = self._get_cache_file(cache_key)
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f)
            
            # Update metadata
            self.metadata[cache_key] = {
                'symbol': symbol,
                'from_date': from_date.isoformat(),
                'to_date': to_date.isoformat(),
                'interval': interval,
                'source': source,
                'cached_at': datetime.now().isoformat(),
                'row_count': len(data),
                'file_size': cache_file.stat().st_size
            }
            self._save_metadata()
            
            self.stats['writes'] += 1
            logger.debug(f"Cache WRITE: {cache_key} ({len(data)} rows)")
            
        except Exception as e:
            logger.error(f"Error writing to cache: {e}")
    
    def invalidate(
        self,
        symbol: Optional[str] = None,
        interval: Optional[str] = None,
        older_than_hours: Optional[int] = None
    ) -> int:
        """
        Invalidate cache entries
        
        Args:
            symbol: Specific symbol to invalidate (None = all)
            interval: Specific interval to invalidate (None = all)
            older_than_hours: Invalidate entries older than X hours
            
        Returns:
            Number of entries invalidated
        """
        invalidated = 0
        keys_to_remove = []
        
        for cache_key, meta in self.metadata.items():
            should_invalidate = True
            
            # Filter by symbol
            if symbol and meta.get('symbol') != symbol:
                should_invalidate = False
            
            # Filter by interval
            if interval and meta.get('interval') != interval:
                should_invalidate = False
            
            # Filter by age
            if older_than_hours:
                cached_at = datetime.fromisoformat(meta.get('cached_at', '2000-01-01'))
                age_hours = (datetime.now() - cached_at).total_seconds() / 3600
                if age_hours < older_than_hours:
                    should_invalidate = False
            
            if should_invalidate:
                # Delete cache file
                cache_file = self._get_cache_file(cache_key)
                try:
                    if cache_file.exists():
                        cache_file.unlink()
                    keys_to_remove.append(cache_key)
                    invalidated += 1
                except Exception as e:
                    logger.error(f"Error deleting cache file {cache_file}: {e}")
        
        # Remove from metadata
        for key in keys_to_remove:
            del self.metadata[key]
        
        if invalidated > 0:
            self._save_metadata()
            self.stats['invalidations'] += invalidated
            logger.info(f"✓ Invalidated {invalidated} cache entries")
        
        return invalidated
    
    def clear_all(self) -> int:
        """
        Clear all cache entries
        
        Returns:
            Number of entries cleared
        """
        count = len(self.metadata)
        
        # Delete all cache files
        for cache_file in self.cache_dir.glob('*.json'):
            if cache_file.name != 'metadata.json':
                try:
                    cache_file.unlink()
                except Exception as e:
                    logger.error(f"Error deleting {cache_file}: {e}")
        
        # Clear metadata
        self.metadata = {}
        self._save_metadata()
        
        # Reset stats
        self.stats['invalidations'] += count
        
        logger.info(f"✓ Cleared all cache ({count} entries)")
        return count
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self.stats['hits'] + self.stats['misses']
        hit_rate = (self.stats['hits'] / total_requests * 100) if total_requests > 0 else 0
        
        # Calculate total cache size
        total_size = 0
        for meta in self.metadata.values():
            total_size += meta.get('file_size', 0)
        
        return {
            'hits': self.stats['hits'],
            'misses': self.stats['misses'],
            'writes': self.stats['writes'],
            'invalidations': self.stats['invalidations'],
            'hit_rate': round(hit_rate, 2),
            'total_entries': len(self.metadata),
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2)
        }
    
    def get_cache_info(self) -> List[Dict[str, Any]]:
        """Get information about all cached entries"""
        info = []
        
        for cache_key, meta in self.metadata.items():
            cached_at = datetime.fromisoformat(meta.get('cached_at', '2000-01-01'))
            age_hours = (datetime.now() - cached_at).total_seconds() / 3600
            
            info.append({
                'cache_key': cache_key,
                'symbol': meta.get('symbol'),
                'interval': meta.get('interval'),
                'from_date': meta.get('from_date'),
                'to_date': meta.get('to_date'),
                'source': meta.get('source'),
                'cached_at': meta.get('cached_at'),
                'age_hours': round(age_hours, 2),
                'row_count': meta.get('row_count'),
                'size_kb': round(meta.get('file_size', 0) / 1024, 2)
            })
        
        # Sort by cached_at (newest first)
        info.sort(key=lambda x: x['cached_at'], reverse=True)
        
        return info


# Global instance
_historical_cache = None

def get_historical_cache() -> HistoricalDataCache:
    """Get or create historical data cache instance"""
    global _historical_cache
    if _historical_cache is None:
        _historical_cache = HistoricalDataCache()
    return _historical_cache
