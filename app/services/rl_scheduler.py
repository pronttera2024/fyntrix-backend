import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ..jobs.nightly_rl import main as nightly_rl_main


logger = logging.getLogger(__name__)


class RLScheduler:
    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler()

    async def _run_nightly_rl(self) -> None:
        try:
            await nightly_rl_main()
        except Exception as e:
            logger.error("[RLScheduler] Nightly RL job failed: %s", e, exc_info=True)

    def start(self) -> None:
        try:
            self.scheduler.add_job(
                self._run_nightly_rl,
                CronTrigger(day_of_week="mon-fri", hour="16", minute="30"),
                id="nightly_rl_eod",
                replace_existing=True,
            )
            self.scheduler.start()
            logger.info("[RLScheduler] Started (nightly RL at 16:30, Mon-Fri)")
        except Exception as e:
            logger.error("[RLScheduler] Failed to start: %s", e, exc_info=True)

    def stop(self) -> None:
        try:
            self.scheduler.shutdown()
            logger.info("[RLScheduler] Stopped")
        except Exception as e:
            logger.error("[RLScheduler] Failed to stop: %s", e, exc_info=True)


_scheduler: RLScheduler | None = None


def get_rl_scheduler() -> RLScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = RLScheduler()
    return _scheduler


async def start_rl_scheduler() -> None:
    scheduler = get_rl_scheduler()
    scheduler.start()


def stop_rl_scheduler() -> None:
    scheduler = get_rl_scheduler()
    scheduler.stop()
