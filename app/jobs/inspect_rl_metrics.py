from __future__ import annotations

import json
from typing import Any, Dict

from ..services.pick_logger import get_active_rl_policy


def _count_bandit_contexts(bandit_block: Dict[str, Any]) -> Dict[str, Dict[str, int]]:
    summary: Dict[str, Dict[str, int]] = {}
    for mode, mode_state in (bandit_block or {}).items():
        if not isinstance(mode_state, dict):
            continue
        contexts = mode_state.get("contexts") or {}
        if not isinstance(contexts, dict):
            continue
        ctx_count = len(contexts)
        actions_count = 0
        for ctx_state in contexts.values():
            if not isinstance(ctx_state, dict):
                continue
            actions = ctx_state.get("actions") or {}
            if isinstance(actions, dict):
                actions_count += len(actions)
        summary[mode] = {
            "contexts": ctx_count,
            "actions": actions_count,
        }
    return summary


def main() -> None:
    policy = get_active_rl_policy()
    if not policy:
        print("No ACTIVE RL policy found.")
        return

    policy_id = policy.get("policy_id")
    name = policy.get("name")
    status = policy.get("status")
    print(f"Active RL policy: {policy_id} ({name}), status={status}")

    metrics = policy.get("metrics") or {}
    if not isinstance(metrics, dict) or not metrics:
        print("metrics_json is empty or not present.")
        return

    exit_profiles = metrics.get("exit_profiles") or {}
    best_exit_profiles = metrics.get("best_exit_profiles") or {}

    if isinstance(exit_profiles, dict) and exit_profiles:
        print("\nExit profile metrics by mode:")
        for mode, profiles in exit_profiles.items():
            if not isinstance(profiles, dict):
                continue
            best = None
            best_cfg = best_exit_profiles.get(mode) if isinstance(best_exit_profiles, dict) else None
            if isinstance(best_cfg, dict):
                best = best_cfg.get("id")

            trade_counts = [int(p.get("trades") or 0) for p in profiles.values() if isinstance(p, dict)]
            total_trades = sum(trade_counts)
            print(f"  - {mode}:")
            print(f"      profiles: {len(profiles)}; total_trades: {total_trades}; best: {best}")
    else:
        print("No exit_profile metrics recorded yet.")

    # Exit bandit state
    bandit_block = metrics.get("bandit") or {}
    if isinstance(bandit_block, dict) and bandit_block:
        summary = _count_bandit_contexts(bandit_block)
        if summary:
            print("\nExit bandit context summary:")
            for mode, s in summary.items():
                print(
                    f"  - {mode}: contexts={s.get('contexts', 0)}, "
                    f"actions={s.get('actions', 0)}"
                )
        else:
            print("\nExit bandit block present but no contexts recorded.")
    else:
        print("\nNo exit bandit metrics recorded yet.")

    # Entry bandit state
    entry_block = metrics.get("entry_bandit") or {}
    if isinstance(entry_block, dict) and entry_block:
        print("\nEntry bandit context summary:")
        for mode, mode_state in entry_block.items():
            if not isinstance(mode_state, dict):
                continue
            contexts = mode_state.get("contexts") or {}
            if not isinstance(contexts, dict):
                continue
            ctx_count = len(contexts)
            actions = 0
            for ctx_state in contexts.values():
                if not isinstance(ctx_state, dict):
                    continue
                a = ctx_state.get("actions") or {}
                if isinstance(a, dict):
                    actions += len(a)
            print(f"  - {mode}: contexts={ctx_count}, actions={actions}")
    else:
        print("\nNo entry bandit metrics recorded yet.")


if __name__ == "__main__":
    main()
