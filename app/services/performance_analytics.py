"""
Performance Analytics Service
Provides winning trades analysis based on historical performance
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np
from ..services.chart_data_service import chart_data_service
from ..services.top_picks_store import get_top_picks_store
from ..services.policy_store import get_policy_store
from ..core.market_hours import is_cash_market_open_ist, IST_OFFSET

# Explicit IST timezone for naive recommendation timestamps
IST = timezone(IST_OFFSET)

# Configure structured logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
)


class PerformanceAnalytics:
    """Analyzes performance of AI recommendations over time."""

    def __init__(self):
        self.picks_dir = Path(__file__).parent.parent.parent / "data" / "top_picks_intraday"
        self.picks_dir.mkdir(parents=True, exist_ok=True)

    async def get_winning_strategies(
        self,
        lookback_days: int = 7,
        universe: str = "nifty50"
    ) -> Dict[str, Any]:
        """
        Compute performance analytics for recent recommendations.

        Args:
            lookback_days: Number of days to look back
            universe: Stock universe to analyze

        Returns:
            Dict with metrics and recommendation performance table
        """
        logger.info(f"Starting performance analysis: universe={universe}, lookback_days={lookback_days}")

        # Read historical picks from logs
        historical_picks = self._read_historical_picks(lookback_days, universe)

        if not historical_picks:
            logger.warning(f"No historical picks found for {universe} in last {lookback_days} days")
            return self._empty_response()
        
        logger.info(f"Loaded {len(historical_picks)} historical picks, computing performance...")

        # Fetch current prices and compute returns
        performance_data = await self._compute_performance(historical_picks)
        
        logger.info(f"Performance computed for {len(performance_data)} picks")

        # Deduplicate identical trades for scorecard & metrics while preserving
        # the full raw history in SQLite and the analytics endpoint.
        deduped_data = self._dedupe_performance_entries(performance_data)
        logger.info(
            f"[DEDUP] Reduced {len(performance_data)} performance entries to {len(deduped_data)} unique trades"
        )

        # Calculate aggregate metrics on unique trades, including alpha vs benchmark
        benchmark_return = await self._get_benchmark_return(
            lookback_days=lookback_days,
            universe=universe,
        )
        benchmark_timeseries = await self._get_benchmark_timeseries(
            lookback_days=lookback_days,
            universe=universe,
        )
        metrics = self._calculate_metrics(deduped_data, benchmark_return=benchmark_return)

        # Optional: offline backtest metrics using cached top_picks_backtest.db
        backtest_metrics = self._get_backtest_metrics(
            universe=universe,
            lookback_days=lookback_days,
            benchmark_return=benchmark_return,
        )

        # Strategy-level KPIs via strategy_exits logs
        s1_kpis = self.get_strategy_kpis(
            strategy_id="S1_HEIKIN_ASHI_PSAR_RSI_3M",
            mode="Intraday",
            lookback_days=lookback_days,
        )
        s2_scalping_kpis = self.get_strategy_kpis(
            strategy_id="S2_EMA_TREND_PULLBACK",
            mode="Scalping",
            lookback_days=lookback_days,
        )
        s3_swing_kpis = self.get_strategy_kpis(
            strategy_id="S3_BB_TREND_PULLBACK",
            mode="Swing",
            lookback_days=lookback_days,
        )

        # Get recent recommendations table (also based on unique trades)
        recent_recommendations = self._build_recommendations_table(deduped_data)

        return {
            "metrics": metrics,
            "backtest_metrics": backtest_metrics,
            "strategy_kpis": {
                "S1_HEIKIN_ASHI_PSAR_RSI_3M": s1_kpis,
                "S2_EMA_TREND_PULLBACK__Scalping": s2_scalping_kpis,
                "S3_BB_TREND_PULLBACK__Swing": s3_swing_kpis,
            },
            "recommendations": recent_recommendations,
            "as_of": datetime.utcnow().isoformat() + "Z",
            "lookback_days": lookback_days,
            "universe": universe,
            "benchmark_timeseries": benchmark_timeseries,
        }

    def _get_backtest_metrics(
        self,
        universe: str,
        lookback_days: int,
        benchmark_return: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Summarise offline backtest returns (TP1/MFE/Ladder) for Winning Trades.

        This reads the dedicated cache/top_picks_backtest.db created by the
        offline backtest job. It is strictly read-only and optional: if the
        DB does not exist or contains no rows for the requested universe
        / window, an empty structure is returned so that the API behaviour
        remains backward compatible.
        """

        import sqlite3

        db_path = Path("cache/top_picks_backtest.db")
        if not db_path.exists():
            return {
                "has_data": False,
                "sample_size": 0,
                "avg_return_tp1": None,
                "avg_return_mfe": None,
                "avg_return_ladder": None,
                "alpha_tp1": None,
                "alpha_mfe": None,
                "alpha_ladder": None,
                "benchmark_return": None,
            }

        cutoff = datetime.utcnow() - timedelta(days=lookback_days)

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    COUNT(*) AS n,
                    AVG(potential_return_tp1) AS avg_tp1,
                    AVG(potential_return_mfe) AS avg_mfe,
                    AVG(potential_return_ladder) AS avg_ladder
                FROM picks_backtest
                WHERE universe = ?
                  AND generated_at_utc >= ?
                """,
                (str(universe).lower(), cutoff.isoformat()),
            )

            row = cursor.fetchone()
        except Exception:
            return {
                "has_data": False,
                "sample_size": 0,
                "avg_return_tp1": None,
                "avg_return_mfe": None,
                "avg_return_ladder": None,
                "alpha_tp1": None,
                "alpha_mfe": None,
                "alpha_ladder": None,
                "benchmark_return": None,
            }
        finally:
            try:
                conn.close()  # type: ignore[name-defined]
            except Exception:
                pass

        if not row or not row[0]:
            return {
                "has_data": False,
                "sample_size": 0,
                "avg_return_tp1": None,
                "avg_return_mfe": None,
                "avg_return_ladder": None,
                "alpha_tp1": None,
                "alpha_mfe": None,
                "alpha_ladder": None,
                "benchmark_return": None,
            }

        n, avg_tp1, avg_mfe, avg_ladder = row

        def _pct(x: Optional[float]) -> Optional[float]:
            if x is None:
                return None
            try:
                return round(float(x) * 100.0, 2)
            except Exception:
                return None

        avg_tp1_pct = _pct(avg_tp1)
        avg_mfe_pct = _pct(avg_mfe)
        avg_ladder_pct = _pct(avg_ladder)

        index_ret = float(benchmark_return) if isinstance(benchmark_return, (int, float)) else 0.0

        def _alpha(val: Optional[float]) -> Optional[float]:
            if val is None:
                return None
            try:
                return round(val - index_ret, 2)
            except Exception:
                return None

        return {
            "has_data": True,
            "sample_size": int(n or 0),
            "avg_return_tp1": avg_tp1_pct,
            "avg_return_mfe": avg_mfe_pct,
            "avg_return_ladder": avg_ladder_pct,
            "alpha_tp1": _alpha(avg_tp1_pct),
            "alpha_mfe": _alpha(avg_mfe_pct),
            "alpha_ladder": _alpha(avg_ladder_pct),
            "benchmark_return": round(index_ret, 2),
        }

    def _get_backtest_lookup_for_picks(
        self,
        picks: List[Dict[str, Any]],
    ) -> Dict[Tuple[str, str], Dict[str, Any]]:
        """Build a per-pick lookup of offline TP1/MFE/Ladder returns.

        Keys are (run_id, symbol) pairs; values hold the raw potential_return_*
        values from the backtest DB. This is used to enrich individual
        recommendation rows in the Winning Trades table.
        """

        import sqlite3

        db_path = Path("cache/top_picks_backtest.db")
        if not db_path.exists():
            return {}

        # Collect unique (run_id, symbol) pairs from the incoming picks
        key_pairs = {
            (str(p.get("run_id")), str(p.get("symbol")))
            for p in picks
            if p.get("run_id") and p.get("symbol")
        }
        if not key_pairs:
            return {}

        run_ids = sorted({k[0] for k in key_pairs})

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            placeholders = ",".join("?" for _ in run_ids)
            cursor.execute(
                f"""
                SELECT
                    run_id,
                    symbol,
                    potential_return_tp1,
                    potential_return_mfe,
                    potential_return_ladder
                FROM picks_backtest
                WHERE run_id IN ({placeholders})
                """,
                tuple(run_ids),
            )

            rows = cursor.fetchall()
        except Exception:
            return {}
        finally:
            try:
                conn.close()  # type: ignore[name-defined]
            except Exception:
                pass

        lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for run_id, symbol, r_tp1, r_mfe, r_ladder in rows:
            key = (str(run_id), str(symbol))
            lookup[key] = {
                "tp1": r_tp1,
                "mfe": r_mfe,
                "ladder": r_ladder,
            }

        return lookup

    async def get_winning_trades(
        self,
        lookback_days: int = 7,
        universe: str = "nifty50",
    ) -> Dict[str, Any]:
        """Compatibility alias with clearer naming.

        New code should call this method; get_winning_strategies remains
        as a stable entrypoint for any existing imports.
        """
        return await self.get_winning_strategies(
            lookback_days=lookback_days,
            universe=universe,
        )

    def _read_historical_picks(self, lookback_days: int, universe: str) -> List[Dict[str, Any]]:
        """Read historical picks from log files with comprehensive logging.

        This function now treats each (run, symbol) pair as a separate
        recommendation instance and attaches run_id and rank_in_run so that
        downstream analytics (Winning Trades UI) can reason about repeated
        picks per symbol across modes and time.
        """
        cutoff_date = datetime.utcnow() - timedelta(days=lookback_days)
        historical_picks: List[Dict[str, Any]] = []

        # List all pick files for this universe
        pattern = f"picks_{universe}_*.json"
        files = sorted(self.picks_dir.glob(pattern), reverse=True)
        
        logger.info(f"Scanning {len(files)} files matching pattern '{pattern}' in {self.picks_dir}")

        store = get_top_picks_store()

        for file_path in files:
            try:
                # Parse timestamp from filename: picks_{universe}_MODE_YYYYMMDD_HHMMSS.json
                parts = file_path.stem.split('_')
                if len(parts) < 4:
                    continue

                timestamp_str = parts[-2] + parts[-1]
                file_date = datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")

                # Skip runs outside lookback window
                if file_date < cutoff_date:
                    continue

                # Skip weekend runs from the public scorecard (Sat=5, Sun=6)
                if file_date.weekday() >= 5:
                    logger.debug(f"Skipping weekend run from {file_path.name} (date={file_date.date()})")
                    continue

                with open(file_path, 'r') as f:
                    data = json.load(f)

                items = data.get('items') or data.get('picks') or []
                mode = data.get('mode', 'Swing')  # Get mode from file metadata

                # Enforce 15:15 IST cutoff for intraday-style modes so
                # Winning Trades ignores very-late recommendations that had
                # no realistic chance to play out intraday.
                if mode in ['Scalping', 'Intraday', 'Options', 'Futures']:
                    ist_dt = file_date + IST_OFFSET
                    minutes_ist = ist_dt.hour * 60 + ist_dt.minute
                    cutoff_minutes = 15 * 60 + 15  # 15:15 IST
                    if minutes_ist > cutoff_minutes:
                        logger.info(
                            "[CUT_OFF] Skipping %s run from %s (IST %02d:%02d > 15:15)",
                            mode,
                            file_path.name,
                            ist_dt.hour,
                            ist_dt.minute,
                        )
                        continue
                run_id = data.get('run_id')

                # Optional: engine payload for score hydration when needed
                engine_payload: Optional[Dict[str, Any]] = None

                # Derive a consistent IST-based recommendation timestamp for
                # this run. Prefer the engine's generated_at field when
                # available (which is computed via now_ist and therefore
                # represents an IST wall-clock time), and fall back to the
                # filename-derived UTC timestamp converted to IST otherwise.
                rec_dt: Optional[datetime]
                gen_at_raw = data.get('generated_at')
                if isinstance(gen_at_raw, str):
                    try:
                        rec_dt = datetime.fromisoformat(gen_at_raw)
                    except Exception:
                        rec_dt = None
                else:
                    rec_dt = None

                if not isinstance(rec_dt, datetime):
                    # Filename timestamp is in UTC; convert to IST wall clock
                    # so that downstream displays align with Indian market
                    # hours when no explicit generated_at is present.
                    rec_dt = file_date + IST_OFFSET

                # Hard filter: only keep runs whose recommendation timestamp
                # lies within regular Indian cash-market hours. We restrict
                # Winners to picks generated between 09:20 and 15:20 IST so
                # that the Recommended column never shows obviously off-session
                # times like 04:35 or 06:48.
                try:
                    minutes_ist = rec_dt.hour * 60 + rec_dt.minute
                    open_min = 9 * 60 + 20
                    close_min = 15 * 60 + 20
                    if minutes_ist < open_min or minutes_ist > close_min:
                        continue
                except Exception:
                    # If rec_dt is somehow malformed, keep the run rather than
                    # dropping it entirely.
                    pass

                # Tag each pick with recommendation date, mode, run_id, rank
                for idx, item in enumerate(items[:5]):  # Top 5 picks from each session
                    symbol = item.get('symbol')
                    if not symbol:
                        continue

                    # TRACE: Log scores presence for data flow tracking
                    scores_exist = 'scores' in item
                    scores_count = len(item.get('scores', {})) if scores_exist else 0

                    # If scores missing but we have a run_id, try to hydrate from SQLite
                    if (not scores_exist or scores_count == 0) and run_id:
                        try:
                            if engine_payload is None:
                                engine_payload = store.get_run_by_id(run_id) or {}

                            engine_picks = engine_payload.get('picks') or []
                            match = next(
                                (p for p in engine_picks if p.get('symbol') == symbol),
                                None,
                            )
                            if match and match.get('scores'):
                                item['scores'] = match['scores']
                                scores_exist = True
                                scores_count = len(item['scores'])
                                logger.info(
                                    f"[HydrateScores] Filled scores for {symbol} from run_id={run_id}"
                                )
                        except Exception as e:
                            logger.warning(
                                f"[HydrateScores] Failed to hydrate scores for {symbol} from run_id={run_id}: {e}"
                            )

                    if not scores_exist or scores_count == 0:
                        logger.warning(
                            f"[!] {symbol} from {file_path.name}: Missing or empty scores! "
                            f"scores_exist={scores_exist}, count={scores_count}"
                        )
                    else:
                        logger.debug(
                            f"[OK] {symbol} from {file_path.name}: Has {scores_count} agent scores"
                        )

                    # Preserve ALL original fields including scores. Use the
                    # IST-based generated_at timestamp so that Winners
                    # Recommended time reflects actual market-session time
                    # instead of the UTC-based filename.
                    item['recommended_date'] = rec_dt.strftime("%Y-%m-%d")  # ISO format date only
                    item['recommended_date_str'] = rec_dt.strftime("%b %d")
                    item['recommended_datetime'] = rec_dt  # Keep datetime for days_held & entry_time
                    item['mode'] = mode  # Add trading mode
                    item['run_id'] = run_id
                    item['rank_in_run'] = idx + 1

                    # Verify scores preserved
                    if item.get('scores'):
                        logger.debug(
                            f"[OK] Adding {symbol} with {len(item['scores'])} scores to historical_picks"
                        )

                    historical_picks.append(item)

            except Exception as e:
                logger.error(f"Error reading {file_path}: {e}", exc_info=True)
                continue
        
        # Summary logging
        logger.info(f"[LOADED] {len(historical_picks)} recommendation instances for universe={universe}")
        
        # Verify scores in final dataset
        picks_with_scores = sum(1 for p in historical_picks if p.get('scores'))
        picks_without_scores = len(historical_picks) - picks_with_scores
        
        if picks_without_scores > 0:
            logger.warning(f"[!] {picks_without_scores}/{len(historical_picks)} picks are missing scores!")
            # Log which symbols are missing scores
            missing_symbols = [p.get('symbol') for p in historical_picks if not p.get('scores')]
            logger.warning(f"Symbols missing scores: {missing_symbols[:10]}")
        else:
            logger.info(f"[OK] All {picks_with_scores} picks have agent scores")
        
        return historical_picks

    async def _compute_performance(self, picks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Compute performance for each pick by fetching current prices."""
        performance_data: List[Dict[str, Any]] = []

        # Optional: offline backtest lookup to enrich per-trade return profile
        try:
            backtest_lookup = self._get_backtest_lookup_for_picks(picks)
        except Exception:
            backtest_lookup = {}

        # Simple per-request cache so that we don't fetch the same chart data
        # repeatedly for multiple recommendations of the same symbol/timeframe.
        chart_cache: Dict[Tuple[str, str], Any] = {}

        for pick in picks:
            symbol = pick.get('symbol')
            recommended_date = pick.get('recommended_date')
            recommendation = pick.get('recommendation', 'Hold')

            if not symbol or recommendation == 'Hold':
                continue
            
            # TRACE: Verify scores still present before processing
            scores_present = bool(pick.get('scores'))
            if not scores_present:
                logger.warning(f"[!] {symbol}: Scores missing at compute_performance entry! This is a data flow bug.")
            else:
                logger.debug(f"[OK] {symbol}: Processing with {len(pick['scores'])} agent scores")

            try:
                # Decide chart timeframe: use high-resolution intraday data for
                # very recent recommendations so that multiple picks on the
                # same day can have distinct entry prices based on when they
                # were generated.
                rec_dt_for_entry = pick.get('recommended_datetime') or recommended_date
                timeframe = '1M'
                try:
                    if isinstance(rec_dt_for_entry, datetime):
                        age_days = (datetime.utcnow() - rec_dt_for_entry).days
                    else:
                        age_days = (datetime.utcnow() - datetime.fromisoformat(str(rec_dt_for_entry))).days
                    # For trades from today (or last 24h), switch to 1D
                    # which the chart service maps to 5-minute intraday
                    # candles for NSE stocks.
                    if age_days <= 1:
                        timeframe = '1D'
                except Exception:
                    timeframe = '1M'

                # Fetch chart data to get entry price and current price.
                # Use a small in-memory cache keyed by (symbol, timeframe)
                # to avoid redundant Zerodha/Yahoo calls for the same series.
                cache_key = (symbol, timeframe)
                chart_data = chart_cache.get(cache_key)
                if chart_data is None:
                    chart_data = await chart_data_service.fetch_chart_data(symbol, timeframe)
                    chart_cache[cache_key] = chart_data

                if not chart_data or 'candles' not in chart_data:
                    continue

                # Skip entries based on mock price data in the public scorecard
                data_source = chart_data.get('data_source')
                if data_source == 'Mock Data':
                    logger.warning(
                        f"[SkipMockData] Skipping {symbol} - chart data source is Mock Data"
                    )
                    continue

                candles = pd.DataFrame(chart_data['candles'])
                current_price = chart_data.get('current', {}).get('price', 0)

                # Find entry price using the full recommendation timestamp when available.
                # This allows multiple runs on the same day to have distinct entry prices
                # based on when the recommendation was generated.
                # Also capture the actual candle time used so the UI can show a
                # debug view of which intraday bar was selected.
                entry_price, entry_candle_ts = self._get_entry_price(candles, rec_dt_for_entry)

                if entry_price == 0 or current_price == 0:
                    continue

                # Calculate return
                return_pct = self._compute_return_pct(entry_price, current_price, recommendation)

                # Determine status based on targets, stop loss, and mode
                mode = pick.get('mode', 'Swing')

                # Initialize exit details (can be filled by scalping exits,
                # strategy exits, or EOD close)
                exit_price_actual = None
                exit_time_actual = None
                exit_reason = None
                strategy_exit: Optional[Dict[str, Any]] = None

                # Per-pick trade plan (when available) used to derive
                # target/stop thresholds instead of hard-coded 2%/4%.
                exit_strategy = pick.get('exit_strategy') or None

                if mode == 'Scalping':
                    from ..services.scalping_exit_tracker import scalping_exit_tracker

                    # Prefer an exact match on the recommendation entry time so
                    # that multiple scalping runs on the same symbol/date do
                    # not all attach to the first recorded exit.
                    entry_time_iso: Optional[str] = None
                    try:
                        rec_dt = pick.get('recommended_datetime')
                        if isinstance(rec_dt, datetime):
                            rec_dt_utc = rec_dt
                            if rec_dt_utc.tzinfo is None:
                                rec_dt_utc = rec_dt_utc.replace(tzinfo=timezone.utc)
                            else:
                                rec_dt_utc = rec_dt_utc.astimezone(timezone.utc)
                            entry_time_iso = rec_dt_utc.isoformat().replace("+00:00", "Z")
                    except Exception:
                        entry_time_iso = None

                    # Try to get exit data, using entry_time when available for
                    # precise matching, otherwise fall back to symbol/date.
                    if entry_time_iso:
                        exit_data = scalping_exit_tracker.get_exit(symbol, recommended_date, entry_time_iso)
                    else:
                        exit_data = scalping_exit_tracker.get_exit(symbol, recommended_date)

                    if exit_data:
                        # Use actual exit price and return
                        exit_price_actual = exit_data.get('exit_price')
                        exit_time_actual = exit_data.get('exit_time')
                        exit_reason = exit_data.get('exit_reason')

                        # Sanity: ignore exits that appear to occur before the
                        # recommendation timestamp (can happen if we matched
                        # the wrong run for the same symbol/date).
                        try:
                            rec_dt = pick.get('recommended_datetime')
                            if isinstance(rec_dt, datetime) and exit_time_actual:
                                if rec_dt.tzinfo is None:
                                    rec_dt = rec_dt.replace(tzinfo=IST)
                                rec_dt_utc = rec_dt.astimezone(timezone.utc)

                                exit_dt = datetime.fromisoformat(str(exit_time_actual).replace("Z", "+00:00"))
                                if exit_dt.tzinfo is None:
                                    exit_dt = exit_dt.replace(tzinfo=IST)
                                exit_dt = exit_dt.astimezone(timezone.utc)

                                if exit_dt < rec_dt_utc:
                                    logger.warning(
                                        "[Scalping Exit] Ignoring exit for %s: exit_time %s < recommendation %s",
                                        symbol,
                                        exit_dt.isoformat(),
                                        rec_dt_utc.isoformat(),
                                    )
                                    exit_price_actual = None
                                    exit_time_actual = None
                                    exit_reason = None
                        except Exception:
                            # Best-effort only; if parsing fails we keep the
                            # exit data rather than dropping the trade.
                            pass

                        if exit_price_actual is not None:
                            # Recalculate return with actual exit
                            return_pct = self._compute_return_pct(entry_price, exit_price_actual, recommendation)

                            current_price = exit_price_actual

                            # Map scalping exit_reason into canonical
                            # Winning Trades status vocabulary.
                            if exit_reason == 'TARGET_HIT':
                                try:
                                    tp1, tp2, tp3, _ = self._extract_thresholds_pct(exit_strategy)
                                    if tp3 is not None and return_pct >= float(tp3):
                                        status = 'TP3 HIT'
                                        exit_reason = 'TP3_HIT'
                                    elif return_pct >= float(tp2):
                                        status = 'TP2 HIT'
                                        exit_reason = 'TP2_HIT'
                                    elif return_pct >= float(tp1):
                                        status = 'TP1 HIT'
                                        exit_reason = 'TP1_HIT'
                                    else:
                                        status = 'CLOSED'
                                except Exception:
                                    status = 'TP1 HIT'
                            elif exit_reason == 'STOP_LOSS':
                                status = 'STOP LOSS'
                            elif exit_reason in ('TIME_EXIT', 'TRAILING_STOP', 'EOD_AUTO_EXIT'):
                                status = 'CLOSED'
                            else:
                                status = 'CLOSED'

                            logger.info(
                                f"[Scalping Exit] {symbol}: {exit_reason} @ {exit_price_actual}, return: {return_pct:.2f}%"
                            )
                        else:
                            # If the exit was rejected by sanity checks, fall
                            # back to standard status logic.
                            status = self._determine_status(
                                return_pct,
                                recommendation,
                                candles,
                                entry_price,
                                mode,
                                exit_strategy,
                            )
                    else:
                        # No exit logged yet - use standard status logic
                        status = self._determine_status(
                            return_pct,
                            recommendation,
                            candles,
                            entry_price,
                            mode,
                            exit_strategy,
                        )
                else:
                    # Non-scalping modes - use standard status logic
                    status = self._determine_status(
                        return_pct,
                        recommendation,
                        candles,
                        entry_price,
                        mode,
                        exit_strategy,
                    )

                # Strategy-based exits (e.g. S1/S2/S3) layered on top of
                # base status logic.
                if mode in ['Intraday', 'Swing', 'Scalping']:
                    try:
                        from ..services.strategy_exit_tracker import strategy_exit_tracker
                    except Exception:
                        strategy_exit_tracker = None  # type: ignore[assignment]

                    if strategy_exit_tracker is not None:
                        try:
                            if mode == 'Intraday':
                                # S1: Heikin-Ashi + PSAR + RSI virtual exits
                                se = strategy_exit_tracker.get_exit_for(
                                    symbol=symbol,
                                    date=recommended_date,
                                    strategy_id="S1_HEIKIN_ASHI_PSAR_RSI_3M",
                                    mode=mode,
                                )
                            elif mode == 'Swing':
                                # S3: Bollinger trend pullback virtual exits
                                se = strategy_exit_tracker.get_exit_for(
                                    symbol=symbol,
                                    date=recommended_date,
                                    strategy_id="S3_BB_TREND_PULLBACK",
                                    mode=mode,
                                )
                            else:  # Scalping: S2 EMA trend pullback metadata
                                se = strategy_exit_tracker.get_exit_for(
                                    symbol=symbol,
                                    date=recommended_date,
                                    strategy_id="S2_EMA_TREND_PULLBACK",
                                    mode=mode,
                                )
                        except Exception as e:
                            logger.error(
                                "[PerformanceAnalytics] Strategy exit lookup failed for %s: %s",
                                symbol,
                                e,
                                exc_info=True,
                            )
                            se = None

                        if se is not None:
                            # Always attach metadata so the UI can show
                            # hover markers even if we don't override the
                            # realized exit price. Advisory exits such as
                            # PARTIAL_PROFIT or CONTEXT_INVALIDATED are used
                            # to color the status but do not force a
                            # synthetic close in P&L.
                            try:
                                sr_reason = se.get('sr_reason')
                                news_reason = se.get('news_reason')
                                reason_text = None
                                if isinstance(sr_reason, str) and sr_reason.strip():
                                    reason_text = sr_reason.strip()
                                elif isinstance(news_reason, str) and news_reason.strip():
                                    reason_text = news_reason.strip()

                                kind = str(se.get('kind') or '').upper()
                                if kind == 'CONTEXT_INVALIDATED':
                                    se['message'] = f"Context invalidated: {reason_text}" if reason_text else 'Context invalidated'
                                elif kind == 'PARTIAL_PROFIT':
                                    se['message'] = f"Partial profit: {reason_text}" if reason_text else 'Partial profit'
                                elif reason_text:
                                    se['message'] = reason_text
                            except Exception:
                                pass

                            strategy_exit = se

                # For Intraday: treat EOD as exit at last candle close when no
                # explicit strategy-based exit was recorded. (Scalping uses
                # explicit scalping_exit_tracker exits instead.)
                if mode == 'Intraday' and status == 'CLOSED' and exit_price_actual is None:
                    rec_datetime = pick.get('recommended_datetime')
                    if rec_datetime:
                        rec_date = rec_datetime.date()
                        day_candles = candles[candles['time'].apply(
                            lambda t: datetime.fromtimestamp(t).date() == rec_date
                        )]

                        if len(day_candles) > 0:
                            last_row = day_candles.iloc[-1]
                            closing_price = float(last_row['close'])

                            # Recalculate return with closing price
                            return_pct = self._compute_return_pct(entry_price, closing_price, recommendation)

                            current_price = closing_price

                            # Also expose an explicit synthetic exit for Intraday
                            exit_price_actual = closing_price
                            try:
                                ts = int(last_row['time'])
                                exit_time_actual = self._iso_utc_from_epoch(ts)
                            except Exception:
                                exit_time_actual = None
                            exit_reason = exit_reason or 'EOD_CLOSE'

                # Map advisory strategy exits to high-level statuses when no
                # canonical realized exit has been recorded. Only advisories
                # explicitly marked as exit-driving (is_exit=True) are allowed
                # to change trade status here; informational-only advisories
                # (is_exit=False) must not flip an ACTIVE trade into a closed
                # state in Winners.
                if exit_price_actual is None and strategy_exit is not None:
                    try:
                        is_exit_advisory = bool(strategy_exit.get('is_exit', True))
                    except Exception:
                        is_exit_advisory = True

                    if is_exit_advisory:
                        try:
                            kind = str(strategy_exit.get('kind') or '').upper()
                            if kind == 'CONTEXT_INVALIDATED':
                                status = 'CONTEXT INVALIDATED'
                            elif kind == 'PARTIAL_PROFIT':
                                status = 'PARTIAL PROFIT'
                        except Exception:
                            pass

                if exit_price_actual is None and status in ('TP1 HIT', 'TP2 HIT', 'TP3 HIT', 'STOP LOSS'):
                    try:
                        tp1, tp2, tp3, stop_loss = self._extract_thresholds_pct(exit_strategy)
                        level_pct: Optional[float] = None
                        hit_kind = 'TP'

                        if status == 'TP3 HIT':
                            level_pct = tp3 if tp3 is not None else tp2
                        elif status == 'TP2 HIT':
                            level_pct = tp2
                        elif status == 'TP1 HIT':
                            level_pct = tp1
                        else:
                            hit_kind = 'SL'
                            level_pct = abs(float(stop_loss))

                        if level_pct is not None and isinstance(level_pct, (int, float)) and level_pct > 0:
                            is_long = recommendation == 'Buy'
                            if hit_kind == 'TP':
                                level_price = entry_price * (1.0 + float(level_pct) / 100.0) if is_long else entry_price * (1.0 - float(level_pct) / 100.0)
                                exit_time_actual, exit_price_actual = self._find_first_threshold_hit(
                                    candles,
                                    int(entry_candle_ts or 0),
                                    recommendation,
                                    'TP',
                                    float(level_price),
                                )
                                if exit_price_actual is not None:
                                    exit_reason = f"TP{3 if status == 'TP3 HIT' else 2 if status == 'TP2 HIT' else 1}_HIT"
                            else:
                                level_price = entry_price * (1.0 - float(level_pct) / 100.0) if is_long else entry_price * (1.0 + float(level_pct) / 100.0)
                                exit_time_actual, exit_price_actual = self._find_first_threshold_hit(
                                    candles,
                                    int(entry_candle_ts or 0),
                                    recommendation,
                                    'SL',
                                    float(level_price),
                                )
                                if exit_price_actual is not None:
                                    exit_reason = 'STOP_LOSS'

                            if exit_price_actual is not None:
                                return_pct = self._compute_return_pct(entry_price, float(exit_price_actual), recommendation)
                                current_price = float(exit_price_actual)
                    except Exception:
                        pass

                if exit_price_actual is None and strategy_exit is not None and status in ('CONTEXT INVALIDATED', 'PARTIAL PROFIT'):
                    # Only treat the advisory as an effective exit when the
                    # producer marked it as exit-driving. This prevents
                    # informational-only alerts from synthesising exits or
                    # timestamps.
                    try:
                        is_exit_advisory = bool(strategy_exit.get('is_exit', True))
                    except Exception:
                        is_exit_advisory = True

                    if not is_exit_advisory:
                        # Purely informational advisory: do not alter status,
                        # exit_price or exit_time.
                        pass
                    else:
                        px = strategy_exit.get('recommended_exit_price')
                        ts = strategy_exit.get('generated_at')

                        # When we have a numeric recommended exit price, use
                        # it as a canonical close and attach a normalised
                        # timestamp for the advisory.
                        if isinstance(px, (int, float)) and float(px) > 0:
                            exit_price_actual = float(px)

                            # Normalise advisory exit timestamp into an ISO
                            # UTC string so that it is comparable with
                            # recommendation time and consistent in the UI.
                            if ts:
                                try:
                                    if isinstance(ts, datetime):
                                        dt_ts = ts
                                    else:
                                        s_ts = str(ts)
                                        if s_ts.endswith("Z"):
                                            dt_ts = datetime.fromisoformat(s_ts.replace("Z", "+00:00"))
                                        else:
                                            dt_ts = datetime.fromisoformat(s_ts)

                                    if dt_ts.tzinfo is None:
                                        # Strategy exits store naive IST
                                        # timestamps; attach IST so that
                                        # conversion to UTC preserves the
                                        # absolute moment.
                                        dt_ts = dt_ts.replace(tzinfo=IST)

                                    exit_time_actual = self._iso_utc_from_datetime(dt_ts)
                                except Exception:
                                    # Fall back to the raw value if parsing
                                    # fails; the upstream sanity check will
                                    # decide whether to keep or drop it.
                                    exit_time_actual = str(ts)

                            kind = str(strategy_exit.get('kind') or '').upper()
                            exit_reason = kind
                            return_pct = self._compute_return_pct(entry_price, float(exit_price_actual), recommendation)
                            current_price = float(exit_price_actual)

                        else:
                            # Even when there is no explicit numeric exit
                            # price, still expose the advisory timestamp so
                            # the UI can show when the context was
                            # invalidated or partial profit was raised.
                            if ts and exit_time_actual is None:
                                try:
                                    if isinstance(ts, datetime):
                                        dt_ts = ts
                                    else:
                                        s_ts = str(ts)
                                        if s_ts.endswith("Z"):
                                            dt_ts = datetime.fromisoformat(s_ts.replace("Z", "+00:00"))
                                        else:
                                            dt_ts = datetime.fromisoformat(s_ts)

                                    if dt_ts.tzinfo is None:
                                        dt_ts = dt_ts.replace(tzinfo=IST)

                                    exit_time_actual = self._iso_utc_from_datetime(dt_ts)
                                except Exception:
                                    exit_time_actual = str(ts)

                # Sanity check: exit times should not be earlier than the
                # recommendation time. If we detect this, drop the exit and
                # treat the trade as still open for purposes of the summary.
                try:
                    rec_dt = pick.get('recommended_datetime')
                    if isinstance(rec_dt, datetime) and exit_time_actual:
                        # Naive recommendation datetimes are in IST; normalise
                        # both recommendation and exit timestamps to UTC
                        # before comparison so Winners modal ordering is
                        # consistent.
                        if rec_dt.tzinfo is None:
                            rec_dt = rec_dt.replace(tzinfo=IST)
                        rec_dt_utc = rec_dt.astimezone(timezone.utc)

                        exit_dt = datetime.fromisoformat(str(exit_time_actual).replace("Z", "+00:00"))
                        if exit_dt.tzinfo is None:
                            # Naive exit timestamps in this pipeline are
                            # produced in IST; attach IST before converting to
                            # UTC so that ordering vs recommendation time is
                            # correct.
                            exit_dt = exit_dt.replace(tzinfo=IST)
                        exit_dt = exit_dt.astimezone(timezone.utc)

                        if exit_dt < rec_dt_utc:
                            logger.warning(
                                "[PerformanceAnalytics] Dropping exit for %s (%s): exit_time %s < recommendation %s",
                                symbol,
                                mode,
                                exit_dt.isoformat(),
                                rec_dt_utc.isoformat(),
                            )
                            exit_price_actual = None
                            exit_time_actual = None
                            exit_reason = None
                except Exception:
                    # Non-fatal; if we cannot parse timestamps we keep the
                    # exit data instead of failing the trade entirely.
                    pass

                # Calculate days held using stored datetime
                rec_datetime = pick.get('recommended_datetime')
                if rec_datetime:
                    days_held = (datetime.utcnow() - rec_datetime).days
                else:
                    # Fallback: parse from date string
                    try:
                        rec_date = datetime.strptime(recommended_date, "%Y-%m-%d")
                        days_held = (datetime.utcnow() - rec_date).days
                    except:
                        days_held = 0

                # For intraday-style modes (Scalping, Intraday), enforce that
                # trades are always treated as same-day exits in Winners:
                #
                #   1) If a realised exit timestamp spills into the next
                #      IST calendar day (e.g. an EOD_AUTO_EXIT logged on the
                #      following morning), clamp it back to a canonical
                #      end-of-day time on the original trade date so the UI
                #      never shows next-day exits for these modes.
                #   2) If the trade's session is already in the past and we
                #      still have no realised exit, synthesise an end-of-day
                #      close using the last available candle for that
                #      trading date so that trades are not shown as ACTIVE
                #      across multiple sessions.
                try:
                    if mode in ['Intraday', 'Scalping']:
                        rec_dt = pick.get('recommended_datetime')
                        if isinstance(rec_dt, datetime):
                            # Recommendation timestamps in this pipeline are
                            # IST wall-clock times stored as naive datetimes.
                            if rec_dt.tzinfo is None:
                                rec_ist = rec_dt.replace(tzinfo=IST)
                            else:
                                rec_ist = rec_dt.astimezone(IST)

                            trade_date = rec_ist.date()

                            # 1) Clamp any realised exits that appear on the
                            #    next IST day back to an EOD timestamp on the
                            #    trade date.
                            if exit_time_actual:
                                try:
                                    exit_dt = datetime.fromisoformat(
                                        str(exit_time_actual).replace("Z", "+00:00")
                                    )
                                    if exit_dt.tzinfo is None:
                                        # Exit timestamps are serialised as
                                        # UTC Z strings; attach UTC when
                                        # missing before converting to IST.
                                        exit_dt = exit_dt.replace(tzinfo=timezone.utc)
                                    exit_ist = exit_dt.astimezone(IST)

                                    if exit_ist.date() > trade_date:
                                        # Use a canonical close time per
                                        # mode so that Winners presents a
                                        # reasonable intraday/same-day exit.
                                        if mode == 'Scalping':
                                            close_h, close_m = 15, 20
                                        else:  # Intraday
                                            close_h, close_m = 15, 29

                                        clamped_ist = datetime(
                                            trade_date.year,
                                            trade_date.month,
                                            trade_date.day,
                                            close_h,
                                            close_m,
                                            0,
                                            tzinfo=IST,
                                        )

                                        # Ensure we never move the exit
                                        # before the recommendation time.
                                        if clamped_ist <= rec_ist:
                                            clamped_ist = rec_ist + timedelta(minutes=1)

                                        exit_time_actual = self._iso_utc_from_datetime(clamped_ist)
                                except Exception:
                                    # If clamping fails for any reason, keep
                                    # the original exit timestamp rather than
                                    # dropping the trade.
                                    pass

                            # 2) If the trade day is in the past and we
                            #    still have no realised exit, synthesise an
                            #    end-of-day close so that the trade no longer
                            #    appears ACTIVE across days.
                            if exit_price_actual is None:
                                try:
                                    today_ist = datetime.utcnow().replace(
                                        tzinfo=timezone.utc
                                    ).astimezone(IST).date()

                                    if today_ist > trade_date and status == 'ACTIVE':
                                        # Filter candles to those on the
                                        # recommendation date using the same
                                        # naive-date comparison as other
                                        # parts of this service.
                                        day_candles = candles[candles['time'].apply(
                                            lambda t: datetime.fromtimestamp(t).date() == trade_date
                                        )]

                                        if len(day_candles) > 0:
                                            last_row = day_candles.iloc[-1]
                                            closing_price = float(last_row['close'])

                                            # Recalculate return with the
                                            # effective end-of-day close.
                                            return_pct = self._compute_return_pct(
                                                entry_price,
                                                closing_price,
                                                recommendation,
                                            )

                                            current_price = closing_price
                                            exit_price_actual = closing_price

                                            try:
                                                ts = int(last_row['time'])
                                                exit_time_actual = self._iso_utc_from_epoch(ts)
                                            except Exception:
                                                # Fallback: synthetic close
                                                # timestamp based on trade
                                                # date and canonical close
                                                # time.
                                                if mode == 'Scalping':
                                                    close_h, close_m = 15, 20
                                                else:
                                                    close_h, close_m = 15, 29

                                                pseudo_close = datetime(
                                                    trade_date.year,
                                                    trade_date.month,
                                                    trade_date.day,
                                                    close_h,
                                                    close_m,
                                                    0,
                                                    tzinfo=IST,
                                                )
                                                exit_time_actual = self._iso_utc_from_datetime(pseudo_close)

                                            exit_reason = exit_reason or 'EOD_CLOSE'
                                            status = 'CLOSED'
                                        else:
                                            # No candle data for that day;
                                            # mark the position closed so it
                                            # does not remain ACTIVE across
                                            # multiple sessions.
                                            status = 'CLOSED'
                                except Exception:
                                    # Best-effort only; if normalisation or
                                    # synthetic close fails, keep the trade
                                    # as-is rather than breaking analytics.
                                    pass
                except Exception:
                    # Guard-rail: never allow intraday/scalping-specific
                    # normalisation errors to bubble up.
                    pass

                # Additional safeguard for Scalping: enforce a hard
                # max-hold horizon based on the trade plan (default 60
                # minutes). If a scalping trade is still marked ACTIVE
                # after this horizon and no explicit exit has been
                # recorded, synthesise a time-based exit using the last
                # available candle up to that horizon so that Winners
                # never shows scalps as ACTIVE for hours.
                if mode == 'Scalping' and exit_price_actual is None and status == 'ACTIVE':
                    try:
                        rec_dt = pick.get('recommended_datetime')
                        if isinstance(rec_dt, datetime):
                            # Determine configured max hold from exit_strategy
                            max_hold_conf: Optional[float] = None
                            if isinstance(exit_strategy, dict):
                                mh = exit_strategy.get('max_hold_mins')
                                if isinstance(mh, (int, float)) and mh > 0:
                                    max_hold_conf = float(mh)

                            max_hold_minutes = max_hold_conf or 60.0

                            # Age of the trade in minutes using IST wall-clock
                            if rec_dt.tzinfo is None:
                                rec_ist = rec_dt.replace(tzinfo=IST)
                            else:
                                rec_ist = rec_dt.astimezone(IST)

                            now_ist = datetime.utcnow().replace(tzinfo=timezone.utc).astimezone(IST)
                            age_minutes = (now_ist - rec_ist).total_seconds() / 60.0

                            if age_minutes >= max_hold_minutes:
                                # Determine a horizon timestamp in epoch
                                # seconds based on the entry candle plus the
                                # configured max-hold window.
                                if isinstance(entry_candle_ts, (int, float)) and entry_candle_ts > 0:
                                    horizon_ts = int(entry_candle_ts + max_hold_minutes * 60.0)
                                    try:
                                        horizon_candles = candles[candles['time'].apply(
                                            lambda t: int(t) <= horizon_ts
                                        )]
                                    except Exception:
                                        horizon_candles = candles
                                else:
                                    horizon_candles = candles

                                if len(horizon_candles) > 0:
                                    last_row = horizon_candles.iloc[-1]
                                    closing_price = float(last_row['close'])

                                    # Recalculate return with the synthetic
                                    # time-based close.
                                    return_pct = self._compute_return_pct(
                                        entry_price,
                                        closing_price,
                                        recommendation,
                                    )

                                    current_price = closing_price
                                    exit_price_actual = closing_price

                                    try:
                                        ts = int(last_row['time'])
                                        exit_time_actual = self._iso_utc_from_epoch(ts)
                                    except Exception:
                                        exit_time_actual = None

                                    exit_reason = exit_reason or 'TIME_EXIT'
                                    status = 'CLOSED'
                    except Exception:
                        # Best-effort only; if the synthetic time-exit
                        # computation fails, leave the trade unchanged.
                        pass

                # Simple sanity filter for intraday/scalping extreme returns
                if mode in ['Intraday', 'Scalping'] and days_held <= 1:
                    if abs(return_pct) > 30:
                        logger.warning(
                            f"[SkipOutlier] Skipping {symbol} ({mode}) with return {return_pct:.2f}% "
                            f"for days_held={days_held} as unrealistic for intraday/scalping"
                        )
                        continue

                # Construct performance data with explicit scores preservation
                perf_entry: Dict[str, Any] = {
                    'symbol': symbol,
                    'recommended_date': pick.get('recommended_date', ''),
                    'entry_price': round(entry_price, 2),
                    'current_price': round(current_price, 2),
                    'return_pct': round(return_pct, 2),
                    'status': status,
                    'days_held': days_held,
                    'recommendation': recommendation,
                    'mode': pick.get('mode', 'Swing'),
                    'confidence': pick.get('confidence', 'Medium'),
                    'score_blend': pick.get('score_blend', 0),
                    'scores': pick.get('scores', {}),  # Preserve agent scores
                    'run_id': pick.get('run_id'),
                    'rank_in_run': pick.get('rank_in_run'),
                    # Explicit entry timestamp for UI/analytics (ISO8601 if available)
                    'entry_time': (
                        self._iso_utc_from_datetime(pick['recommended_datetime'])
                        if isinstance(pick.get('recommended_datetime'), datetime)
                        else None
                    ),
                    # Debug: actual candle time used for entry price mapping
                    'entry_candle_time': (
                        datetime.fromtimestamp(entry_candle_ts, tz=timezone.utc).isoformat() + 'Z'
                        if isinstance(entry_candle_ts, (int, float)) and entry_candle_ts > 0
                        else None
                    ),
                }

                # Attach offline backtest potential returns (TP1 / MFE / Ladder) when available
                try:
                    run_id_val = pick.get('run_id')
                    if run_id_val:
                        bt_key = (str(run_id_val), symbol)
                        bt = backtest_lookup.get(bt_key, None)
                    else:
                        bt = None
                except Exception:
                    bt = None

                if bt is not None:
                    def _bt_pct(x: Any):
                        try:
                            if x is None:
                                return None
                            return round(float(x) * 100.0, 2)
                        except Exception:
                            return None

                    r_tp1 = _bt_pct(bt.get('tp1'))
                    r_mfe = _bt_pct(bt.get('mfe'))
                    r_ladder = _bt_pct(bt.get('ladder'))

                    if r_tp1 is not None:
                        perf_entry['return_tp1'] = r_tp1
                    if r_mfe is not None:
                        perf_entry['return_mfe'] = r_mfe
                    if r_ladder is not None:
                        perf_entry['return_ladder'] = r_ladder

                # Add scalping/strategy exit details if available. Attach
                # exit_time / exit_reason whenever present so that advisory
                # exits such as CONTEXT_INVALIDATED can still display a
                # timestamp even when no explicit exit_price was recorded.
                if exit_price_actual is not None:
                    perf_entry['exit_price'] = round(exit_price_actual, 2)
                if exit_time_actual is not None:
                    perf_entry['exit_time'] = exit_time_actual
                if exit_reason is not None:
                    perf_entry['exit_reason'] = exit_reason

                # Attach raw strategy exit metadata (for UI hover markers, etc.)
                if strategy_exit is not None:
                    perf_entry['strategy_exit'] = strategy_exit
                
                # TRACE: Verify scores made it to performance entry
                if not perf_entry['scores']:
                    logger.error(f"[ERROR] {symbol}: Scores LOST during performance_data construction! pick had scores: {bool(pick.get('scores'))}")
                else:
                    logger.debug(f"[OK] {symbol}: Performance entry created with {len(perf_entry['scores'])} scores")
                
                performance_data.append(perf_entry)

            except Exception as e:
                logger.error(f"Error computing performance for {symbol}: {e}", exc_info=True)
                continue
        
        # Final validation
        logger.info(f"[OK] Returning {len(performance_data)} performance entries")
        
        # Verify scores in final output
        entries_with_scores = sum(1 for p in performance_data if p.get('scores'))
        if entries_with_scores < len(performance_data):
            missing = len(performance_data) - entries_with_scores
            logger.error(f"[ERROR] {missing}/{len(performance_data)} performance entries are missing scores!")
            # Log specific symbols
            missing_symbols = [p['symbol'] for p in performance_data if not p.get('scores')]
            logger.error(f"Symbols missing scores in output: {missing_symbols}")
        else:
            logger.info(f"[OK] All {entries_with_scores} performance entries have agent scores")
        
        return performance_data

    def _get_entry_price(self, candles: pd.DataFrame, recommended_at: Any) -> Tuple[float, int]:
        """Get entry price from candles based on recommendation timestamp.

        recommended_at may be a datetime or an ISO8601 string. Using the
        full timestamp (when available) ensures different runs on the same
        day can map to different entry candles.
        """
        try:
            # Normalize recommendation time to an epoch-second timestamp in UTC
            if isinstance(recommended_at, (int, float)):
                # Already an epoch timestamp
                rec_timestamp = int(recommended_at)
            else:
                if isinstance(recommended_at, datetime):
                    rec_dt = recommended_at
                else:
                    s = str(recommended_at)
                    # Handle trailing 'Z' (UTC designator) if present
                    if s.endswith("Z"):
                        rec_dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                    else:
                        rec_dt = datetime.fromisoformat(s)

                # Naive datetimes in this pipeline are in IST; attach IST and
                # convert to UTC before computing the epoch timestamp.
                if rec_dt.tzinfo is None:
                    rec_dt = rec_dt.replace(tzinfo=IST)
                rec_dt_utc = rec_dt.astimezone(timezone.utc)

                rec_timestamp = int(rec_dt_utc.timestamp())

            # Find the candle closest to recommendation timestamp
            candles = candles.copy()
            candles['time_diff'] = (candles['time'] - rec_timestamp).abs()
            closest_idx = candles['time_diff'].idxmin()
            entry_row = candles.loc[closest_idx]
            entry_price = entry_row['close']

            # Extract candle timestamp (epoch seconds) for debug/analytics
            try:
                candle_ts_raw = entry_row['time']
                entry_candle_ts = int(candle_ts_raw)
            except Exception:
                try:
                    entry_candle_ts = int(float(candle_ts_raw))  # type: ignore[name-defined]
                except Exception:
                    entry_candle_ts = 0

            return float(entry_price), entry_candle_ts
        except Exception as e:
            print(f"[PerformanceAnalytics] Error getting entry price: {e}")
            # Use first available candle as fallback
            if len(candles) > 0:
                fallback_price = float(candles.iloc[0]['close'])
                try:
                    fallback_ts = int(candles.iloc[0]['time'])
                except Exception:
                    fallback_ts = 0
            else:
                fallback_price = 0.0
                fallback_ts = 0

            return fallback_price, fallback_ts

    def _compute_return_pct(
        self,
        entry_price: float,
        price: float,
        recommendation: str,
    ) -> float:
        if recommendation == 'Buy':
            return ((price - entry_price) / entry_price) * 100
        else:
            return ((entry_price - price) / entry_price) * 100

    def _extract_thresholds_pct(
        self,
        exit_strategy: Optional[Dict[str, Any]],
    ) -> Tuple[float, float, Optional[float], float]:
        tp1 = 2.0
        tp2 = 4.0
        tp3: Optional[float] = None
        stop_loss = -2.0

        try:
            if exit_strategy and isinstance(exit_strategy, dict):
                ladder = exit_strategy.get('targets_ladder') or {}

                def _val(k: str) -> Optional[float]:
                    v = ladder.get(k)
                    try:
                        return float(v)
                    except Exception:
                        return None

                tp1_pct = _val('tp1_pct')
                tp2_pct = _val('tp2_pct')
                tp3_pct = _val('tp3_pct')

                s_pct = exit_strategy.get('stop_pct')
                if isinstance(s_pct, (int, float)) and s_pct > 0:
                    stop_loss = -float(s_pct)

                if isinstance(tp1_pct, (int, float)) and tp1_pct > 0:
                    tp1 = float(tp1_pct)
                if isinstance(tp2_pct, (int, float)) and tp2_pct > 0:
                    tp2 = float(tp2_pct)
                if isinstance(tp3_pct, (int, float)) and tp3_pct > 0:
                    tp3 = float(tp3_pct)

                if (not ladder) or (not isinstance(tp1_pct, (int, float)) or tp1_pct <= 0):
                    t_pct = exit_strategy.get('target_pct')
                    if isinstance(t_pct, (int, float)) and t_pct > 0:
                        tp1 = float(t_pct)
                        tp2 = tp1 * 2.0
        except Exception:
            pass

        return tp1, tp2, tp3, stop_loss

    def _iso_utc_from_epoch(self, ts: Any) -> Optional[str]:
        try:
            ts_int = int(ts)
            if ts_int <= 0:
                return None
            return datetime.fromtimestamp(ts_int, tz=timezone.utc).isoformat().replace('+00:00', 'Z')
        except Exception:
            return None

    def _iso_utc_from_datetime(self, dt: datetime) -> str:
        try:
            # Naive datetimes in this service are in IST; attach IST first so
            # that the conversion to UTC produces the correct absolute
            # timestamp for serialization.
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST)
            dt = dt.astimezone(timezone.utc)
            return dt.isoformat().replace('+00:00', 'Z')
        except Exception:
            return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')

    def _find_first_threshold_hit(
        self,
        candles: pd.DataFrame,
        start_ts: int,
        direction: str,
        kind: str,
        level_price: float,
    ) -> Tuple[Optional[str], Optional[float]]:
        try:
            if candles is None or len(candles) == 0:
                return None, None

            df = candles
            if 'time' not in df.columns:
                return None, None

            try:
                df = df[df['time'].apply(lambda t: int(t) >= int(start_ts))]
            except Exception:
                df = df

            if len(df) == 0:
                return None, None

            d = (direction or '').lower()
            is_long = d == 'buy'
            k = (kind or '').upper()

            for _, row in df.iterrows():
                try:
                    hi = float(row.get('high'))
                    lo = float(row.get('low'))
                    ts = row.get('time')
                except Exception:
                    continue

                if k == 'TP':
                    hit = (hi >= level_price) if is_long else (lo <= level_price)
                else:
                    hit = (lo <= level_price) if is_long else (hi >= level_price)

                if hit:
                    return self._iso_utc_from_epoch(ts), float(level_price)

            return None, None
        except Exception:
            return None, None

    def _determine_status(
        self,
        return_pct: float,
        recommendation: str,
        candles: pd.DataFrame,
        entry_price: float,
        mode: str = 'Swing',
        exit_strategy: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Determine trade status based on price action and mode."""

        # Define target thresholds (conservative defaults used when no
        # trade-plan ladder is available).
        tp1 = 2.0   # 2% gain
        tp2 = 4.0   # 4% gain
        tp3 = None  # Optional third target when available
        stop_loss = -2.0  # 2% loss

        # When a per-pick trade plan is available, prefer the explicit
        # TP1/TP2/TP3 ladder from exit_strategy.targets_ladder. This allows
        # us to distinguish TP1/TP2/TP3 HIT in Winning Trades.
        try:
            if exit_strategy and isinstance(exit_strategy, dict):
                ladder = exit_strategy.get('targets_ladder') or {}

                def _val(k: str) -> Optional[float]:
                    v = ladder.get(k)
                    try:
                        return float(v)
                    except Exception:
                        return None

                tp1_pct = _val('tp1_pct')
                tp2_pct = _val('tp2_pct')
                tp3_pct = _val('tp3_pct')

                # Stop-loss still derived from stop_pct when provided.
                s_pct = exit_strategy.get('stop_pct')
                if isinstance(s_pct, (int, float)) and s_pct > 0:
                    stop_loss = -float(s_pct)

                # Use ladder percentages when present; otherwise fall back to
                # single target_pct with 2R-style TP2 as before.
                if isinstance(tp1_pct, (int, float)) and tp1_pct > 0:
                    tp1 = float(tp1_pct)
                if isinstance(tp2_pct, (int, float)) and tp2_pct > 0:
                    tp2 = float(tp2_pct)
                if isinstance(tp3_pct, (int, float)) and tp3_pct > 0:
                    tp3 = float(tp3_pct)

                if (not ladder) or (not isinstance(tp1_pct, (int, float)) or tp1_pct <= 0):
                    # Backward-compatible single-target behaviour
                    t_pct = exit_strategy.get('target_pct')
                    if isinstance(t_pct, (int, float)) and t_pct > 0:
                        tp1 = float(t_pct)
                        tp2 = tp1 * 2.0
        except Exception:
            pass

        # Map realised return to TP1/TP2/TP3 semantics. We treat the
        # highest target exceeded as the status.
        if tp3 is not None and return_pct >= tp3:
            return 'TP3 HIT'
        elif return_pct >= tp2:
            return 'TP2 HIT'
        elif return_pct >= tp1:
            return 'TP1 HIT'
        elif return_pct <= stop_loss:
            return 'STOP LOSS'
        else:
            # For Intraday/Scalping: Check if market closed
            if mode in ['Intraday', 'Scalping']:
                # Market hours: 9:15 AM to 3:30 PM IST (closed outside this window)
                market_closed = not is_cash_market_open_ist()
                if market_closed:
                    return 'CLOSED'  # Market closed for intraday
            
            return 'ACTIVE'

    async def _get_benchmark_return(
        self,
        lookback_days: int,
        universe: str,
    ) -> Optional[float]:
        """Fetch benchmark index return (%) for the lookback window.

        Uses NIFTY50 as the default benchmark for most universes and BANKNIFTY
        when the universe appears to be bank-index focused. Falls back to 0.0
        when data is unavailable or only mock data is present.
        """

        try:
            universe_lower = (universe or "").lower()
            if "bank" in universe_lower:
                benchmark_symbol = "BANKNIFTY"
            else:
                benchmark_symbol = "NIFTY50"

            # Map lookback window to a coarse chart timeframe for index data.
            if lookback_days <= 7:
                timeframe = "1W"
            elif lookback_days <= 30:
                timeframe = "1M"
            else:
                timeframe = "1Y"

            chart = await chart_data_service.fetch_chart_data(benchmark_symbol, timeframe)
            if not chart:
                logger.warning(
                    "[Benchmark] No chart data returned for %s / %s (lookback_days=%s)",
                    benchmark_symbol,
                    timeframe,
                    lookback_days,
                )
                return None

            if chart.get("data_source") == "Mock Data":
                logger.warning(
                    "[Benchmark] Chart data for %s / %s is Mock Data; skipping benchmark for alpha",
                    benchmark_symbol,
                    timeframe,
                )
                return None

            current = chart.get("current") or {}
            change = current.get("change")
            if isinstance(change, (int, float)):
                return float(change)

            logger.warning(
                "[Benchmark] Missing or invalid 'change' field in chart response for %s / %s",
                benchmark_symbol,
                timeframe,
            )
            return None
        except Exception as e:
            logger.error("[Benchmark] Failed to compute benchmark return: %s", e, exc_info=True)
            return None

    async def _get_benchmark_timeseries(
        self,
        lookback_days: int,
        universe: str,
    ) -> Dict[str, float]:
        """Fetch per-day benchmark index returns (%) keyed by ISO date.

        This is used by the Winning Trades UI to align date-filtered trade
        performance with the same-day NIFTY50 / BANKNIFTY move instead of
        only a window-level benchmark.
        """

        try:
            universe_lower = (universe or "").lower()
            if "bank" in universe_lower:
                benchmark_symbol = "BANKNIFTY"
            else:
                benchmark_symbol = "NIFTY50"

            # Map lookback window to a coarse chart timeframe for index data.
            if lookback_days <= 7:
                timeframe = "1W"
            elif lookback_days <= 30:
                timeframe = "1M"
            else:
                timeframe = "1Y"

            chart = await chart_data_service.fetch_chart_data(benchmark_symbol, timeframe)
            if not chart:
                logger.warning(
                    "[BenchmarkTS] No chart data returned for %s / %s (lookback_days=%s)",
                    benchmark_symbol,
                    timeframe,
                    lookback_days,
                )
                return {}

            if chart.get("data_source") == "Mock Data":
                logger.warning(
                    "[BenchmarkTS] Chart data for %s / %s is Mock Data; skipping benchmark timeseries",
                    benchmark_symbol,
                    timeframe,
                )
                return {}

            candles = chart.get("candles") or []
            if not candles:
                return {}

            df = pd.DataFrame(candles)
            if df.empty or "time" not in df or "open" not in df or "close" not in df:
                return {}

            df["time"] = pd.to_numeric(df["time"], errors="coerce")
            df["open"] = pd.to_numeric(df["open"], errors="coerce")
            df["close"] = pd.to_numeric(df["close"], errors="coerce")
            df = df.dropna(subset=["time", "open", "close"])

            if df.empty:
                return {}

            # Derive trading date in IST to match recommended_date semantics.
            df["dt_utc"] = pd.to_datetime(df["time"], unit="s", utc=True)
            df["date"] = df["dt_utc"].dt.tz_convert("Asia/Kolkata").dt.date

            daily_returns: Dict[str, float] = {}
            for date_value, grp in df.groupby("date", sort=True):
                if grp.empty:
                    continue

                try:
                    first_open = float(grp.iloc[0]["open"])
                    last_close = float(grp.iloc[-1]["close"])
                except Exception:
                    continue

                if first_open <= 0 or last_close <= 0:
                    continue

                ret = ((last_close - first_open) / first_open) * 100.0
                daily_returns[date_value.isoformat()] = round(float(ret), 2)

            return daily_returns
        except Exception as e:
            logger.error("[BenchmarkTS] Failed to compute benchmark timeseries: %s", e, exc_info=True)
            return {}

    def _calculate_metrics(
        self,
        performance_data: List[Dict[str, Any]],
        benchmark_return: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Calculate aggregate performance metrics, including alpha vs benchmark."""

        if not performance_data:
            return {
                'win_rate': 0,
                'avg_return': 0.0,
                'alpha_generated': 0.0,
                'total_picks': 0
            }

        # Win rate: % of picks that hit target (not stop loss or negative)
        wins = [p for p in performance_data if p['return_pct'] > 0]
        losses = [p for p in performance_data if p['return_pct'] <= 0]

        win_rate = (len(wins) / len(performance_data)) * 100 if performance_data else 0

        # Average return per recommendation
        avg_return = np.mean([p['return_pct'] for p in performance_data])

        # Alpha generated vs benchmark index (e.g. NIFTY50 / BANKNIFTY).
        # When benchmark_return is unavailable, fall back to 0.0 so that
        # alpha reduces to the raw average return instead of using a stub.
        index_return = float(benchmark_return) if isinstance(benchmark_return, (int, float)) else 0.0
        alpha_generated = avg_return - index_return

        return {
            'win_rate': round(win_rate, 1),
            'avg_return': round(avg_return, 2),
            'alpha_generated': round(alpha_generated, 2),
            'total_picks': len(performance_data),
            'winning_picks': len(wins),
            'losing_picks': len(losses),
            'benchmark_return': round(index_return, 2),
        }

    def get_strategy_kpis(
        self,
        strategy_id: str,
        mode: Optional[str] = None,
        lookback_days: int = 30,
    ) -> Dict[str, Any]:
        """Compute strategy-level KPIs from strategy_exits logs.

        This reads advisory-only strategy_exit_tracker data and derives
        win-rate and return/R-multiple metrics for the given strategy.
        """

        from ..services.strategy_exit_tracker import strategy_exit_tracker

        base_dir = strategy_exit_tracker.exits_dir

        try:
            if not base_dir.exists():
                return {
                    "strategy_id": strategy_id,
                    "mode": mode,
                    "lookback_days": lookback_days,
                    "trades": 0,
                    "win_rate": 0.0,
                    "avg_return": 0.0,
                    "avg_rr_multiple": None,
                }
        except Exception:
            return {
                "strategy_id": strategy_id,
                "mode": mode,
                "lookback_days": lookback_days,
                "trades": 0,
                "win_rate": 0.0,
                "avg_return": 0.0,
                "avg_rr_multiple": None,
            }

        now = datetime.utcnow()
        cutoff = now - timedelta(days=lookback_days)

        # Collect best-per-day exits using the same ranking logic as
        # StrategyExitTracker.get_exit_for (per symbol/mode/date).
        per_key: Dict[tuple, Dict[str, Any]] = {}

        for file_path in sorted(base_dir.glob("strategy_exits_*.json")):
            stem = file_path.stem.replace("strategy_exits_", "")
            try:
                file_dt = datetime.strptime(stem, "%Y%m%d")
            except Exception:
                continue

            if file_dt < cutoff:
                continue

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.error("[StrategyKPIs] Failed to read %s: %s", file_path.name, e, exc_info=True)
                continue

            for rec in data.get("exits", []):
                if rec.get("strategy_id") != strategy_id:
                    continue
                if mode is not None and rec.get("mode") != mode:
                    continue

                sym = rec.get("symbol")
                if not sym:
                    continue

                key = (sym, rec.get("mode"), file_dt.date().isoformat())

                def sort_key(r: Dict[str, Any]) -> tuple:
                    kind = str(r.get("kind") or "")
                    if kind == "CONTEXT_INVALIDATED":
                        kind_rank = 0
                    elif kind == "PARTIAL_PROFIT":
                        kind_rank = 1
                    else:
                        kind_rank = 2

                    ts = r.get("generated_at")
                    try:
                        if isinstance(ts, str):
                            ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        else:
                            ts_dt = datetime.min
                    except Exception:
                        ts_dt = datetime.min

                    return (kind_rank, ts_dt)

                existing = per_key.get(key)
                if existing is None or sort_key(rec) < sort_key(existing):
                    per_key[key] = rec

        if not per_key:
            return {
                "strategy_id": strategy_id,
                "mode": mode,
                "lookback_days": lookback_days,
                "trades": 0,
                "win_rate": 0.0,
                "avg_return": 0.0,
                "avg_rr_multiple": None,
            }

        returns: List[float] = []
        rr_vals: List[float] = []

        for rec in per_key.values():
            try:
                entry = float(rec.get("entry_price") or 0.0)
                exit_px = float(rec.get("recommended_exit_price") or 0.0)
            except Exception:
                continue

            if entry <= 0 or exit_px <= 0:
                continue

            direction = str(rec.get("direction") or "LONG").upper()
            if direction == "SHORT":
                ret = ((entry - exit_px) / entry) * 100.0
            else:
                ret = ((exit_px - entry) / entry) * 100.0

            returns.append(ret)

            rr = rec.get("rr_multiple")
            try:
                rr_f = float(rr) if rr is not None else None
            except Exception:
                rr_f = None

            if rr_f is not None:
                rr_vals.append(rr_f)

        if not returns:
            return {
                "strategy_id": strategy_id,
                "mode": mode,
                "lookback_days": lookback_days,
                "trades": 0,
                "win_rate": 0.0,
                "avg_return": 0.0,
                "avg_rr_multiple": None,
            }

        wins = [r for r in returns if r > 0]
        win_rate = (len(wins) / len(returns)) * 100.0 if returns else 0.0
        avg_return = float(np.mean(returns)) if returns else 0.0
        avg_rr = float(np.mean(rr_vals)) if rr_vals else None

        return {
            "strategy_id": strategy_id,
            "mode": mode,
            "lookback_days": lookback_days,
            "trades": len(returns),
            "win_rate": round(win_rate, 1),
            "avg_return": round(avg_return, 2),
            "avg_rr_multiple": round(avg_rr, 2) if avg_rr is not None else None,
        }

    def _dedupe_performance_entries(
        self, performance_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Collapse obviously identical trades while preserving distinct ones.

        Deduplication is based on trade outcome characteristics so that multiple
        identical entries (same symbol/mode/date/prices/status) from repeated
        runs do not inflate the scorecard, while still retaining all unique
        trades for analytics.
        """

        unique_entries: List[Dict[str, Any]] = []
        seen_keys = set()

        for p in performance_data:
            key = (
                p.get('symbol'),
                p.get('mode'),
                p.get('recommended_date'),
                round(p.get('entry_price', 0.0), 4),
                round(p.get('current_price', 0.0), 4),
                p.get('status'),
                # For scalping / closed trades, include exit_price when present
                round(p.get('exit_price', p.get('current_price', 0.0)), 4),
            )

            if key in seen_keys:
                continue

            seen_keys.add(key)
            unique_entries.append(p)

        return unique_entries

    def _build_recommendations_table(
        self,
        performance_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Build the recommendations table for UI display."""

        # Sort by return_pct (highest first) for better UX. The incoming
        # performance_data is already deduplicated by _dedupe_performance_entries.
        return sorted(
            performance_data,
            key=lambda x: x.get('return_pct', 0),
            reverse=True,
        )

    async def evaluate_ai_recommendations(self, max_rows: int = 500) -> Dict[str, Any]:
        import sqlite3
        from ..services.ai_recommendation_store import get_ai_recommendation_store
        from ..services.scalping_exit_tracker import scalping_exit_tracker

        policy_store = get_policy_store()

        now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)

        store = get_ai_recommendation_store()
        conn = sqlite3.connect(store.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, symbol, mode, recommendation, generated_at_utc, entry_price
            FROM ai_recommendations
            WHERE evaluated = 0
            ORDER BY generated_at_utc ASC
            LIMIT ?
            """,
            (max_rows,),
        )
        rows = cursor.fetchall()

        evaluated = 0
        for rec_id, symbol, mode, recommendation, generated_at_utc, entry_price in rows:
            mode_policy = policy_store.get_mode_policy(mode)
            mode_type = str(mode_policy.horizon_type or "").lower()

            if not entry_price:
                continue

            # Parse recommendation time (stored as UTC ISO string) into aware UTC
            try:
                s = str(generated_at_utc)
                if s.endswith("Z"):
                    rec_dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                else:
                    rec_dt = datetime.fromisoformat(s)
            except Exception:
                rec_dt = now_utc

            if rec_dt.tzinfo is None:
                rec_dt = rec_dt.replace(tzinfo=timezone.utc)
            else:
                rec_dt = rec_dt.astimezone(timezone.utc)

            rec_lower = str(recommendation or "").lower()

            # 1) Scalping / exit-only: rely on explicit scalping exits
            if mode_type == "exit_only":
                entry_date = rec_dt.date().isoformat()

                exit_data = scalping_exit_tracker.get_exit(symbol, entry_date)
                if not exit_data:
                    continue

                try:
                    exit_price = float(exit_data.get("exit_price") or 0.0)
                except Exception:
                    exit_price = 0.0

                if exit_price <= 0.0:
                    continue

                if "sell" in rec_lower:
                    pnl_pct = ((entry_price - exit_price) / entry_price) * 100.0
                else:
                    pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0

                exit_time_utc = exit_data.get("exit_time")
                exit_reason = exit_data.get("exit_reason") or "SCALPING_EXIT"

            # 2) Intraday / eod_close: evaluate at end-of-day close
            elif mode_type == "eod_close":
                # Only evaluate once the trading day has fully completed
                rec_date = rec_dt.date()
                if now_utc.date() <= rec_date:
                    continue

                # Use near-term intraday data when recent, else daily
                age_days = (now_utc.date() - rec_date).days
                timeframe = "1D" if age_days <= 1 else "1M"

                try:
                    chart_data = await chart_data_service.fetch_chart_data(symbol, timeframe)
                except Exception:
                    continue

                if not chart_data or "candles" not in chart_data:
                    continue

                candles = pd.DataFrame(chart_data["candles"])
                if candles.empty or "time" not in candles or "close" not in candles:
                    continue

                day_candles = candles[candles["time"].apply(
                    lambda t: datetime.fromtimestamp(t, tz=timezone.utc).date() == rec_date
                )]

                if len(day_candles) == 0:
                    continue

                last_row = day_candles.iloc[-1]
                try:
                    closing_price = float(last_row["close"])
                except Exception:
                    continue

                if closing_price <= 0.0:
                    continue

                if "sell" in rec_lower:
                    pnl_pct = ((entry_price - closing_price) / entry_price) * 100.0
                else:
                    pnl_pct = ((closing_price - entry_price) / entry_price) * 100.0

                try:
                    ts = int(last_row["time"])
                    exit_time_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    exit_time_utc = exit_time_dt.isoformat().replace("+00:00", "Z")
                except Exception:
                    exit_time_utc = None

                exit_price = closing_price
                exit_reason = "EOD_CLOSE"

            # 3) Swing / Options / Futures: evaluate at fixed-days horizon
            elif mode_type == "fixed_days":
                days = int(mode_policy.horizon_days or 0)
                if days <= 0:
                    continue

                horizon_dt = rec_dt + timedelta(days=days)
                if now_utc < horizon_dt:
                    continue

                target_ts = int(horizon_dt.timestamp())

                try:
                    chart_data = await chart_data_service.fetch_chart_data(symbol, "1M")
                except Exception:
                    continue

                if not chart_data or "candles" not in chart_data:
                    continue

                candles = pd.DataFrame(chart_data["candles"])
                if candles.empty or "time" not in candles or "close" not in candles:
                    continue

                candles = candles.copy()
                candles["time_diff_eval"] = (candles["time"] - target_ts).abs()
                try:
                    closest_idx = candles["time_diff_eval"].idxmin()
                except Exception:
                    continue

                row = candles.loc[closest_idx]
                try:
                    eval_price = float(row["close"])
                except Exception:
                    continue

                if eval_price <= 0.0:
                    continue

                if "sell" in rec_lower:
                    pnl_pct = ((entry_price - eval_price) / entry_price) * 100.0
                else:
                    pnl_pct = ((eval_price - entry_price) / entry_price) * 100.0

                try:
                    ts = int(row["time"])
                    exit_time_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    exit_time_utc = exit_time_dt.isoformat().replace("+00:00", "Z")
                except Exception:
                    exit_time_utc = None

                exit_price = eval_price
                exit_reason = f"FIXED_DAYS_{days}"

            else:
                # Unknown or unsupported mode type
                continue

            evaluated_at_utc = now_utc.isoformat().replace("+00:00", "Z")

            cursor.execute(
                """
                UPDATE ai_recommendations
                SET evaluated = 1,
                    evaluated_at_utc = ?,
                    exit_price = ?,
                    exit_time_utc = ?,
                    exit_reason = ?,
                    pnl_pct = ?
                WHERE id = ?
                """,
                (
                    evaluated_at_utc,
                    exit_price,
                    exit_time_utc,
                    exit_reason,
                    pnl_pct,
                    rec_id,
                ),
            )
            evaluated += 1

        if evaluated:
            conn.commit()
        conn.close()

        return {
            "evaluated": evaluated,
            "total_candidates": len(rows),
        }

    async def get_alpha_by_mode(self, lookback_days: int = 30) -> Dict[str, Any]:
        """Aggregate realized P&L metrics by trading mode over a lookback window.

        This reads evaluated rows from ai_recommendations and groups by mode to
        compute basic statistics like win rate and average pnl_pct. For now,
        alpha is measured as excess return vs 0 (no-trade baseline); benchmark
        adjustments can be layered on later.
        """

        import sqlite3
        from ..services.ai_recommendation_store import get_ai_recommendation_store

        now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
        cutoff_dt = now_utc - timedelta(days=lookback_days)
        cutoff_iso = cutoff_dt.isoformat().replace("+00:00", "Z")

        store = get_ai_recommendation_store()
        conn = sqlite3.connect(store.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT mode, pnl_pct
            FROM ai_recommendations
            WHERE evaluated = 1
              AND generated_at_utc >= ?
            """,
            (cutoff_iso,),
        )
        rows = cursor.fetchall()
        conn.close()

        by_mode: Dict[str, Dict[str, Any]] = {}

        for mode, pnl in rows:
            if pnl is None:
                continue
            try:
                pnl_f = float(pnl)
            except Exception:
                continue

            mode_key = str(mode or "Unknown")
            bucket = by_mode.setdefault(
                mode_key,
                {
                    "mode": mode_key,
                    "trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "sum_pnl": 0.0,
                    "pnl_values": [],
                },
            )

            bucket["trades"] += 1
            bucket["sum_pnl"] += pnl_f
            bucket["pnl_values"].append(pnl_f)
            if pnl_f > 0:
                bucket["wins"] += 1
            else:
                bucket["losses"] += 1

        summary: Dict[str, Any] = {
            "modes": [],
            "total_trades": 0,
            "overall_avg_pnl_pct": 0.0,
        }

        all_pnls: list[float] = []

        for mode_key, bucket in by_mode.items():
            trades = bucket["trades"]
            wins = bucket["wins"]
            losses = bucket["losses"]
            pnl_values = bucket["pnl_values"]

            if trades == 0 or not pnl_values:
                avg_pnl = 0.0
                median_pnl = 0.0
                win_rate = 0.0
            else:
                avg_pnl = float(np.mean(pnl_values))
                median_pnl = float(np.median(pnl_values))
                win_rate = (wins / trades) * 100.0

            all_pnls.extend(pnl_values)

            summary["modes"].append(
                {
                    "mode": mode_key,
                    "trades": trades,
                    "wins": wins,
                    "losses": losses,
                    "win_rate": round(win_rate, 1),
                    "avg_pnl_pct": round(avg_pnl, 2),
                    "median_pnl_pct": round(median_pnl, 2),
                }
            )

        summary["total_trades"] = sum(m["trades"] for m in summary["modes"])
        if all_pnls:
            summary["overall_avg_pnl_pct"] = round(float(np.mean(all_pnls)), 2)

        return summary

    def _empty_response(self) -> Dict[str, Any]:
        """Return empty response when no data available."""
        return {
            "metrics": {
                "win_rate": 0,
                "avg_return": 0.0,
                "alpha_generated": 0.0,
                "total_picks": 0
            },
            "recommendations": [],
            "as_of": datetime.utcnow().isoformat() + "Z",
            "message": "No historical picks found for the specified period"
        }


# Global instance
performance_analytics = PerformanceAnalytics()
