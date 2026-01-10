import json
from pathlib import Path
from typing import Dict, List

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .top_picks_engine import NIFTY_50_SYMBOLS, BANKNIFTY_SYMBOLS, NIFTY_100_SYMBOLS, NIFTY_500_SYMBOLS, INDEX_UNIVERSE_CACHE_FILE


class IndexUniverseMonitor:
    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler()
        self.cache_file: Path = INDEX_UNIVERSE_CACHE_FILE
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

    async def refresh_universes(self) -> None:
        try:
            data: Dict[str, List[str]] = {
                "nifty50": NIFTY_50_SYMBOLS,
                "banknifty": BANKNIFTY_SYMBOLS,
                "nifty100": NIFTY_100_SYMBOLS,
                "nifty500": NIFTY_500_SYMBOLS,
            }
            with open(self.cache_file, "w") as f:
                json.dump(data, f)
            print(f"[IndexUniverseMonitor] Index universes cache written to {self.cache_file}")
        except Exception as e:
            print(f"[IndexUniverseMonitor] Failed to refresh index universes: {e}")

    def start(self) -> None:
        try:
            self.scheduler.add_job(
                self.refresh_universes,
                CronTrigger(hour="6", minute="10"),
                id="index_universe_refresh",
                replace_existing=True,
            )
            self.scheduler.start()
            # Prime cache once at startup (fire-and-forget)
            import asyncio
            asyncio.create_task(self.refresh_universes())
            print("[IndexUniverseMonitor] Started index universe scheduler")
        except Exception as e:
            print(f"[IndexUniverseMonitor] Failed to start scheduler: {e}")

    def stop(self) -> None:
        try:
            self.scheduler.shutdown()
            print("[IndexUniverseMonitor] Stopped index universe scheduler")
        except Exception as e:
            print(f"[IndexUniverseMonitor] Failed to stop scheduler: {e}")


_monitor: IndexUniverseMonitor | None = None


def get_index_universe_monitor() -> IndexUniverseMonitor:
    global _monitor
    if _monitor is None:
        _monitor = IndexUniverseMonitor()
    return _monitor


async def start_index_universe_monitoring() -> None:
    monitor = get_index_universe_monitor()
    monitor.start()


def stop_index_universe_monitoring() -> None:
    monitor = get_index_universe_monitor()
    monitor.stop()
