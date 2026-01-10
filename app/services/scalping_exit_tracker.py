"""
Scalping Exit Tracker Service

Manages storage and retrieval of scalping trade exit signals.
Provides full audit trail for regulatory compliance.

Features:
- Exit signal logging
- Position tracking
- Audit trail maintenance
- Exit data retrieval
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional

from ..core.market_hours import IST_OFFSET

from .ai_recommendation_store import get_ai_recommendation_store
from .pick_logger import log_scalping_exit_outcome

logger = logging.getLogger(__name__)


class ScalpingExitTracker:
    """Track and store scalping trade exit signals."""

    def __init__(self):
        """Initialize exit tracker with storage directory."""
        self.exits_dir = Path(__file__).parent.parent.parent / "data" / "scalping_exits"
        self.exits_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"ScalpingExitTracker initialized: storage={self.exits_dir}")

    def log_exit(self, exit_data: Dict[str, Any]) -> None:
        """
        Log a scalping exit to daily file.

        Args:
            exit_data: Dict containing exit information
                - symbol: Stock symbol
                - entry_time: Entry timestamp (ISO format)
                - entry_price: Entry price
                - exit_time: Exit timestamp (ISO format)
                - exit_price: Exit price
                - exit_reason: Reason for exit (TARGET_HIT, STOP_LOSS, TIME_EXIT, EOD_AUTO_EXIT)
                - return_pct: Return percentage
                - hold_duration_mins: Hold duration in minutes
                - mode: 'Scalping'
        """
        try:
            # Extract date from exit time
            exit_time = datetime.fromisoformat(exit_data['exit_time'].replace('Z', '+00:00'))
            date_str = exit_time.strftime('%Y%m%d')

            # File path for this date
            file_path = self.exits_dir / f"exits_{date_str}.json"

            # Load existing data or create new
            if file_path.exists():
                with open(file_path, 'r') as f:
                    data = json.load(f)
            else:
                data = {
                    'date': exit_time.strftime('%Y-%m-%d'),
                    'exits': []
                }

            # Check if exit already logged (prevent duplicates)
            existing = next(
                (e for e in data['exits'] 
                 if e['symbol'] == exit_data['symbol'] 
                 and e['entry_time'] == exit_data['entry_time']),
                None
            )

            if existing:
                logger.warning(f"Exit already logged for {exit_data['symbol']} at {exit_data['entry_time']}")
                return

            # Add new exit
            data['exits'].append(exit_data)

            # Save to file
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)

            logger.info(f"[EXIT LOGGED] {exit_data['symbol']}: {exit_data['exit_reason']} @ {exit_data['exit_price']}, return: {exit_data['return_pct']:.2f}%")

            try:
                log_scalping_exit_outcome(exit_data)
            except Exception as e:
                logger.warning(
                    f"[EXIT->PICK_DATASET] Failed to log scalping exit outcome for {exit_data.get('symbol', 'UNKNOWN')}: {e}",
                    exc_info=True,
                )

            # Best-effort: also update the ai_recommendations dataset so that
            # scalping exits are immediately reflected there. Batch evaluation
            # will skip rows that have already been marked evaluated.
            try:
                store = get_ai_recommendation_store()
                updated = store.apply_scalping_exit(exit_data)
                if updated:
                    logger.info(
                        f"[EXIT->AI_DATASET] Updated {updated} ai_recommendations row(s) for {exit_data['symbol']}"
                    )
            except Exception as e:
                logger.warning(
                    f"[EXIT->AI_DATASET] Failed to update ai_recommendations for {exit_data.get('symbol', 'UNKNOWN')}: {e}",
                    exc_info=True,
                )

        except Exception as e:
            logger.error(f"Error logging exit for {exit_data.get('symbol', 'UNKNOWN')}: {e}", exc_info=True)

    def get_exit(self, symbol: str, entry_date: str, entry_time: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieve exit for a specific symbol and entry date.

        Args:
            symbol: Stock symbol
            entry_date: Entry date (YYYY-MM-DD format)
            entry_time: Optional entry time for precise matching

        Returns:
            Exit data dict if found, None otherwise
        """
        try:
            # Convert entry_date to file date format
            entry_dt = datetime.fromisoformat(entry_date)
            date_str = entry_dt.strftime('%Y%m%d')

            # Check file for this date
            file_path = self.exits_dir / f"exits_{date_str}.json"

            if not file_path.exists():
                return None

            # Load data
            with open(file_path, 'r') as f:
                data = json.load(f)

            # Normalise the requested entry_time (if any) into a UTC datetime so
            # that we can robustly compare even if one side uses "Z" and the
            # other uses "+00:00" or has different precision.
            target_dt: Optional[datetime] = None
            if entry_time:
                try:
                    dt = datetime.fromisoformat(str(entry_time).replace('Z', '+00:00'))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    else:
                        dt = dt.astimezone(timezone.utc)
                    target_dt = dt
                except Exception:
                    target_dt = None

            best_match: Optional[Dict[str, Any]] = None
            best_delta: Optional[float] = None
            fallback_match: Optional[Dict[str, Any]] = None

            # Find matching exit
            for exit_data in data.get('exits', []):
                try:
                    if exit_data.get('symbol') != symbol:
                        continue

                    # Record the first exit for this symbol/date as a
                    # best-effort fallback when we cannot match by time.
                    if fallback_match is None:
                        fallback_match = exit_data

                    if target_dt is None:
                        # No precise entry_time provided or parsing failed -
                        # rely on the fallback behaviour.
                        continue

                    raw_et = exit_data.get('entry_time')
                    if not isinstance(raw_et, str) or not raw_et:
                        continue

                    try:
                        et_dt = datetime.fromisoformat(raw_et.replace('Z', '+00:00'))
                    except Exception:
                        continue

                    if et_dt.tzinfo is None:
                        et_dt = et_dt.replace(tzinfo=timezone.utc)
                    else:
                        et_dt = et_dt.astimezone(timezone.utc)

                    # Use a small tolerance window so that tiny formatting or
                    # rounding differences do not prevent a match. A window of
                    # 2 minutes is more than enough to disambiguate distinct
                    # scalping entries on the same symbol.
                    delta_sec = abs((et_dt - target_dt).total_seconds())
                    if delta_sec <= 120:
                        if best_delta is None or delta_sec < best_delta:
                            best_delta = delta_sec
                            best_match = exit_data
                except Exception:
                    # Per-record failures should not break the entire lookup.
                    continue

            if best_match is not None:
                return best_match

            if target_dt is None:
                # Fallback: return the first exit we saw for this symbol/date,
                # preserving prior behaviour when we cannot use entry_time.
                return fallback_match

            return None

        except Exception as e:
            logger.error(f"Error retrieving exit for {symbol} on {entry_date}: {e}", exc_info=True)
            return None

    def get_active_positions(self, lookback_hours: int = 2) -> List[Dict[str, Any]]:
        """
        Get all scalping positions that might still be active.

        Args:
            lookback_hours: How far back to look for entries

        Returns:
            List of potential active positions (entries without exits)
        """
        try:
            active_positions: List[Dict[str, Any]] = []

            # Load recent scalping pick files from the scheduler's intraday log directory
            picks_dir = Path(__file__).parent.parent.parent / "data" / "top_picks_intraday"
            # Use timezone-aware UTC datetimes to avoid naive/aware comparison issues
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

            # Filenames look like: picks_nifty50_Scalping_20251122_095130.json
            pattern = "picks_*_Scalping_*.json"
            files = sorted(
                picks_dir.glob(pattern),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            for file_path in files:
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)

                    mode = data.get('mode', '')
                    if str(mode).lower() != 'scalping':
                        continue

                    # Parse generation time from payload (fallback to file mtime).
                    # Top Picks engine stores generated_at/as_of as IST-naive
                    # timestamps. Interpret naive values as IST and convert to
                    # UTC so that all downstream comparisons use a consistent
                    # timezone.
                    as_of = data.get('as_of') or data.get('generated_at')
                    if as_of:
                        try:
                            raw_dt = datetime.fromisoformat(str(as_of).replace('Z', '+00:00'))
                            if raw_dt.tzinfo is None:
                                # Naive timestamp from Top Picks (IST). Convert
                                # to UTC by subtracting IST offset.
                                file_dt = (raw_dt - IST_OFFSET).replace(tzinfo=timezone.utc)
                            else:
                                file_dt = raw_dt.astimezone(timezone.utc)
                        except Exception:
                            file_dt = datetime.utcfromtimestamp(file_path.stat().st_mtime).replace(tzinfo=timezone.utc)
                    else:
                        file_dt = datetime.utcfromtimestamp(file_path.stat().st_mtime).replace(tzinfo=timezone.utc)

                    if file_dt < cutoff_time:
                        continue

                    entry_date = file_dt.date().isoformat()
                    entry_time = file_dt.isoformat()

                    # Check each pick (supports both 'items' and 'picks' keys)
                    picks_list = data.get('items') or data.get('picks', [])
                    for item in picks_list[:5]:
                        symbol = item.get('symbol')
                        recommendation = item.get('recommendation', 'Hold')

                        if not symbol or recommendation == 'Hold':
                            continue

                        # Check if exit already logged for this entry
                        exit_data = self.get_exit(symbol, entry_date, entry_time)
                        if exit_data:
                            continue

                        # Validate required fields before adding
                        entry_price = item.get('entry_price')
                        exit_strategy = item.get('exit_strategy')

                        # Skip positions with incomplete data (None, empty dict, or missing)
                        if not entry_price or not exit_strategy or not isinstance(exit_strategy, dict):
                            logger.warning(
                                f"Skipping {symbol}: missing entry_price={entry_price} or exit_strategy={exit_strategy}"
                            )
                            continue

                        # Validate exit_strategy has required fields
                        required_fields = ['target_price', 'stop_loss_price', 'target_pct', 'stop_pct']
                        missing_fields = [f for f in required_fields if f not in exit_strategy]
                        if missing_fields:
                            logger.warning(f"Skipping {symbol}: exit_strategy missing {missing_fields}")
                            continue

                        active_positions.append(
                            {
                                'symbol': symbol,
                                'entry_time': entry_time,
                                'entry_date': entry_date,
                                'recommendation': recommendation,
                                'entry_price': entry_price,
                                'exit_strategy': exit_strategy,
                                # Carry through the originating pick's blended score if present
                                'score_blend': item.get('score_blend'),
                                'mode': 'Scalping',
                                'file_path': str(file_path),
                            }
                        )

                except Exception as e:
                    logger.debug(f"Skipping file {file_path.name}: {e}")
                    continue

            logger.info(f"[ACTIVE POSITIONS] Found {len(active_positions)} active scalping positions")
            return active_positions

        except Exception as e:
            logger.error(f"Error getting active positions: {e}", exc_info=True)
            return []

    def get_daily_summary(self, date: Optional[str] = None) -> Dict[str, Any]:
        """
        Get summary of exits for a specific date.

        Args:
            date: Date string (YYYY-MM-DD), defaults to today

        Returns:
            Summary dict with stats
        """
        try:
            if not date:
                date = datetime.utcnow().strftime('%Y-%m-%d')

            date_str = datetime.fromisoformat(date).strftime('%Y%m%d')
            file_path = self.exits_dir / f"exits_{date_str}.json"

            if not file_path.exists():
                return {
                    'date': date,
                    'total_exits': 0,
                    'winning_exits': 0,
                    'losing_exits': 0,
                    'avg_return': 0,
                    'avg_hold_time_mins': 0,
                    'exits': []
                }

            with open(file_path, 'r') as f:
                data = json.load(f)

            exits = data.get('exits', [])
            total = len(exits)
            winning = sum(1 for e in exits if e.get('return_pct', 0) > 0)
            losing = total - winning

            avg_return = sum(e.get('return_pct', 0) for e in exits) / total if total > 0 else 0
            avg_hold = sum(e.get('hold_duration_mins', 0) for e in exits) / total if total > 0 else 0

            return {
                'date': date,
                'total_exits': total,
                'winning_exits': winning,
                'losing_exits': losing,
                'avg_return': round(avg_return, 2),
                'avg_hold_time_mins': round(avg_hold, 1),
                'exits': exits
            }

        except Exception as e:
            logger.error(f"Error getting daily summary for {date}: {e}", exc_info=True)
            return {
                'date': date,
                'total_exits': 0,
                'exits': []
            }

    def cleanup_old_exits(self, days_to_keep: int = 90):
        """
        Clean up exit logs older than specified days.

        Args:
            days_to_keep: Number of days to retain (default 90 for compliance)
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
            cutoff_str = cutoff_date.strftime('%Y%m%d')

            deleted = 0
            for file_path in self.exits_dir.glob('exits_*.json'):
                # Extract date from filename
                date_str = file_path.stem.replace('exits_', '')

                if date_str < cutoff_str:
                    file_path.unlink()
                    deleted += 1
                    logger.info(f"Deleted old exit log: {file_path.name}")

            logger.info(f"Cleanup complete: removed {deleted} old exit logs (older than {days_to_keep} days)")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)


# Singleton instance
scalping_exit_tracker = ScalpingExitTracker()
