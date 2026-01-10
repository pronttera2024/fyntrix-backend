"""
Picks Analytics Service
=======================

Tracks and monitors actionable picks system performance:
- How often < 5 picks shown
- User interactions with picks
- Conversion rates (picks viewed → trades executed)
- Feedback collection
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import json
from collections import defaultdict


class PicksAnalytics:
    """
    Analytics service for monitoring picks system
    """
    
    def __init__(self, data_dir: Optional[Path] = None):
        """Initialize analytics with data directory"""
        if data_dir is None:
            data_dir = Path(__file__).parent.parent.parent / "data" / "analytics"
        
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Analytics files
        self.picks_log_file = self.data_dir / "picks_log.jsonl"
        self.interactions_log_file = self.data_dir / "interactions_log.jsonl"
        self.feedback_file = self.data_dir / "feedback.jsonl"
        self.daily_stats_file = self.data_dir / "daily_stats.json"
    
    def log_picks_generation(
        self,
        universe: str,
        requested: int,
        returned: int,
        total_analyzed: int,
        actionable_count: int,
        neutral_filtered: int,
        timestamp: Optional[str] = None
    ):
        """
        Log when picks are generated
        
        Args:
            universe: Universe name (e.g., NIFTY50)
            requested: Number of picks requested
            returned: Number of picks actually returned
            total_analyzed: Total stocks analyzed
            actionable_count: Count of actionable stocks
            neutral_filtered: Count of neutral stocks filtered
            timestamp: ISO timestamp (default: now)
        """
        if timestamp is None:
            timestamp = datetime.now().isoformat() + 'Z'
        
        log_entry = {
            "event": "picks_generated",
            "timestamp": timestamp,
            "universe": universe,
            "requested": requested,
            "returned": returned,
            "total_analyzed": total_analyzed,
            "actionable_count": actionable_count,
            "neutral_filtered": neutral_filtered,
            "fewer_than_requested": returned < requested
        }
        
        self._append_to_log(self.picks_log_file, log_entry)
        self._update_daily_stats(log_entry)
        
        # Log warning if fewer than requested
        if returned < requested:
            print(f"[PicksAnalytics] ⚠️  Only {returned}/{requested} picks for {universe} (filtered {neutral_filtered} neutral)")
    
    def log_pick_interaction(
        self,
        symbol: str,
        action: str,
        universe: str,
        recommendation: str,
        score: float,
        session_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ):
        """
        Log user interaction with a pick
        
        Args:
            symbol: Stock symbol
            action: Action type (view_chart, analyze, feedback, etc.)
            universe: Universe name
            recommendation: Recommendation type
            score: Blend score
            session_id: User session ID
            metadata: Additional metadata
        """
        log_entry = {
            "event": "pick_interaction",
            "timestamp": datetime.now().isoformat() + 'Z',
            "symbol": symbol,
            "action": action,
            "universe": universe,
            "recommendation": recommendation,
            "score": score,
            "session_id": session_id,
            "metadata": metadata or {}
        }
        
        self._append_to_log(self.interactions_log_file, log_entry)
    
    def log_user_feedback(
        self,
        symbol: str,
        feedback_type: str,
        rating: Optional[int] = None,
        comment: Optional[str] = None,
        recommendation: Optional[str] = None,
        session_id: Optional[str] = None
    ):
        """
        Log user feedback on a pick
        
        Args:
            symbol: Stock symbol
            feedback_type: Type of feedback (helpful, not_helpful, trade_executed, etc.)
            rating: Rating 1-5
            comment: User comment
            recommendation: Recommendation shown
            session_id: User session ID
        """
        feedback_entry = {
            "event": "user_feedback",
            "timestamp": datetime.now().isoformat() + 'Z',
            "symbol": symbol,
            "feedback_type": feedback_type,
            "rating": rating,
            "comment": comment,
            "recommendation": recommendation,
            "session_id": session_id
        }
        
        self._append_to_log(self.feedback_file, feedback_entry)
        print(f"[PicksAnalytics] Feedback received: {feedback_type} for {symbol}")
    
    def get_daily_stats(self, date: Optional[str] = None) -> Dict[str, Any]:
        """
        Get daily statistics
        
        Args:
            date: Date in YYYY-MM-DD format (default: today)
        
        Returns:
            Dictionary with daily statistics
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        try:
            if self.daily_stats_file.exists():
                with open(self.daily_stats_file, 'r') as f:
                    all_stats = json.load(f)
                    return all_stats.get(date, self._empty_daily_stats())
        except Exception as e:
            print(f"[PicksAnalytics] Error loading daily stats: {e}")
        
        return self._empty_daily_stats()
    
    def get_conversion_rate(self, days: int = 7) -> Dict[str, Any]:
        """
        Calculate conversion rate (picks viewed → user actions)
        
        Args:
            days: Number of days to analyze
        
        Returns:
            Dictionary with conversion metrics
        """
        cutoff = datetime.now() - timedelta(days=days)
        
        picks_shown = 0
        chart_views = 0
        analyze_requests = 0
        feedback_count = 0
        trade_signals = 0
        
        # Count picks shown
        try:
            if self.picks_log_file.exists():
                with open(self.picks_log_file, 'r') as f:
                    for line in f:
                        try:
                            entry = json.loads(line)
                            ts = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
                            if ts >= cutoff:
                                picks_shown += entry.get('returned', 0)
                        except:
                            continue
        except Exception as e:
            print(f"[PicksAnalytics] Error reading picks log: {e}")
        
        # Count interactions
        try:
            if self.interactions_log_file.exists():
                with open(self.interactions_log_file, 'r') as f:
                    for line in f:
                        try:
                            entry = json.loads(line)
                            ts = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
                            if ts >= cutoff:
                                action = entry.get('action', '')
                                if action == 'view_chart':
                                    chart_views += 1
                                elif action == 'analyze':
                                    analyze_requests += 1
                        except:
                            continue
        except Exception as e:
            print(f"[PicksAnalytics] Error reading interactions log: {e}")
        
        # Count feedback
        try:
            if self.feedback_file.exists():
                with open(self.feedback_file, 'r') as f:
                    for line in f:
                        try:
                            entry = json.loads(line)
                            ts = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
                            if ts >= cutoff:
                                feedback_count += 1
                                if entry.get('feedback_type') == 'trade_executed':
                                    trade_signals += 1
                        except:
                            continue
        except Exception as e:
            print(f"[PicksAnalytics] Error reading feedback log: {e}")
        
        # Calculate rates
        chart_view_rate = (chart_views / picks_shown * 100) if picks_shown > 0 else 0
        analyze_rate = (analyze_requests / picks_shown * 100) if picks_shown > 0 else 0
        feedback_rate = (feedback_count / picks_shown * 100) if picks_shown > 0 else 0
        trade_conversion = (trade_signals / picks_shown * 100) if picks_shown > 0 else 0
        
        return {
            "period_days": days,
            "picks_shown": picks_shown,
            "chart_views": chart_views,
            "analyze_requests": analyze_requests,
            "feedback_count": feedback_count,
            "trade_signals": trade_signals,
            "chart_view_rate": round(chart_view_rate, 2),
            "analyze_rate": round(analyze_rate, 2),
            "feedback_rate": round(feedback_rate, 2),
            "trade_conversion_rate": round(trade_conversion, 2)
        }
    
    def get_fewer_picks_frequency(self, days: int = 30) -> Dict[str, Any]:
        """
        Analyze how often < 5 picks are shown
        
        Args:
            days: Number of days to analyze
        
        Returns:
            Statistics about fewer-than-requested picks
        """
        cutoff = datetime.now() - timedelta(days=days)
        
        total_generations = 0
        fewer_than_5_count = 0
        pick_counts = defaultdict(int)
        by_universe = defaultdict(lambda: {"total": 0, "fewer": 0})
        
        try:
            if self.picks_log_file.exists():
                with open(self.picks_log_file, 'r') as f:
                    for line in f:
                        try:
                            entry = json.loads(line)
                            ts = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
                            if ts >= cutoff:
                                total_generations += 1
                                returned = entry.get('returned', 0)
                                requested = entry.get('requested', 5)
                                universe = entry.get('universe', 'unknown')
                                
                                pick_counts[returned] += 1
                                by_universe[universe]["total"] += 1
                                
                                if returned < requested:
                                    fewer_than_5_count += 1
                                    by_universe[universe]["fewer"] += 1
                        except:
                            continue
        except Exception as e:
            print(f"[PicksAnalytics] Error analyzing fewer picks: {e}")
        
        fewer_rate = (fewer_than_5_count / total_generations * 100) if total_generations > 0 else 0
        
        # Calculate per-universe rates
        universe_stats = {}
        for univ, data in by_universe.items():
            rate = (data["fewer"] / data["total"] * 100) if data["total"] > 0 else 0
            universe_stats[univ] = {
                "total_generations": data["total"],
                "fewer_than_requested": data["fewer"],
                "rate_percent": round(rate, 2)
            }
        
        return {
            "period_days": days,
            "total_generations": total_generations,
            "fewer_than_requested_count": fewer_than_5_count,
            "fewer_than_requested_rate": round(fewer_rate, 2),
            "pick_count_distribution": dict(pick_counts),
            "by_universe": universe_stats
        }
    
    def _append_to_log(self, file_path: Path, entry: Dict):
        """Append entry to JSONL log file"""
        try:
            with open(file_path, 'a') as f:
                f.write(json.dumps(entry) + '\n')
        except Exception as e:
            print(f"[PicksAnalytics] Error appending to log: {e}")
    
    def _update_daily_stats(self, log_entry: Dict):
        """Update daily statistics file"""
        date = log_entry['timestamp'][:10]  # Extract YYYY-MM-DD
        
        try:
            # Load existing stats
            all_stats = {}
            if self.daily_stats_file.exists():
                with open(self.daily_stats_file, 'r') as f:
                    all_stats = json.load(f)
            
            # Initialize today's stats if needed
            if date not in all_stats:
                all_stats[date] = self._empty_daily_stats()
            
            # Update stats
            stats = all_stats[date]
            stats['picks_generations'] += 1
            stats['total_picks_shown'] += log_entry.get('returned', 0)
            stats['neutral_filtered'] += log_entry.get('neutral_filtered', 0)
            
            if log_entry.get('fewer_than_requested', False):
                stats['fewer_than_requested_count'] += 1
            
            # Save updated stats
            with open(self.daily_stats_file, 'w') as f:
                json.dump(all_stats, f, indent=2)
        except Exception as e:
            print(f"[PicksAnalytics] Error updating daily stats: {e}")
    
    def _empty_daily_stats(self) -> Dict[str, Any]:
        """Return empty daily stats structure"""
        return {
            "picks_generations": 0,
            "total_picks_shown": 0,
            "neutral_filtered": 0,
            "fewer_than_requested_count": 0
        }


# Global instance
picks_analytics = PicksAnalytics()


# Export
__all__ = ['PicksAnalytics', 'picks_analytics']
