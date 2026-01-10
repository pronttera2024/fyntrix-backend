import asyncio
from datetime import date
from typing import Optional

from ..services.pick_logger import (
    async_compute_and_log_outcomes_for_date,
    run_all_rl_trainers_for_active_policy,
)


async def main(as_of: Optional[date] = None) -> None:
    """Entry point for nightly RL training job.

    This job is intended to be run once per trading day after market close
    (e.g. 16:30 IST). It will:

    1) Compute and log EOD outcomes for today's trade_date using
       async_compute_and_log_outcomes_for_date(trade_date, "EOD").
    2) Run exit-profile and bandit trainers for the ACTIVE RL policy via
       run_all_rl_trainers_for_active_policy(as_of=as_of or today).
    """

    if as_of is None:
        as_of = date.today()

    trade_date = as_of

    processed = await async_compute_and_log_outcomes_for_date(
        trade_date=trade_date,
        evaluation_horizon="EOD",
    )
    try:
        print(f"[NightlyRL] Computed outcomes for {processed} picks on {trade_date} (EOD)")
    except Exception:
        pass

    policy_id = await run_all_rl_trainers_for_active_policy(as_of=as_of)
    try:
        print(f"[NightlyRL] Completed RL trainers for policy {policy_id} as_of={as_of}")
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
