from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from ..services.pick_logger import create_rl_policy, set_active_rl_policy


def build_policy_config() -> Dict[str, Any]:
    """Construct baseline RL policy config for exits and bandits.

    Modes covered:
    - Scalping: baseline exit profiles plus contextual exit bandit.
    - Intraday: three exit profiles (safe/balanced/aggressive) with
      contextual exit bandit.
    - Swing, Options, Futures: exit profiles configured so offline
      evaluation can pick best profiles per mode.

    Entry bandit configuration is also provided for Scalping and
    Intraday (used today), with placeholder configs for Swing, Options,
    and Futures for future extension.
    """

    exit_priority = {"order": ["STOP", "TRAIL", "TARGET", "TIME"]}

    scalping_profiles: Dict[str, Any] = {
        "scalping_safe": {
            "name": "Scalping Safe",
            # Slightly wider stop and modest target for higher win rate.
            "stop": {"type": "percent", "value": 0.35},
            "target": {"type": "percent", "value": 0.7},
            "trailing": {
                "enabled": True,
                "activation_type": "percent",
                "activation_value": 0.5,
                "trail_type": "percent",
                "trail_value": 0.25,
            },
            # Tight time-boxing for very short-term scalps.
            "time_stop": {"enabled": True, "max_hold_minutes": 10},
            "exit_priority": exit_priority,
        },
        "scalping_balanced": {
            "name": "Scalping Balanced",
            "stop": {"type": "percent", "value": 0.3},
            # Aim for ~2R on average.
            "target": {"type": "rr_multiple", "value": 2.0},
            "trailing": {
                "enabled": True,
                "activation_type": "rr_multiple",
                "activation_value": 2.0,
                "trail_type": "percent",
                "trail_value": 0.3,
            },
            "time_stop": {"enabled": True, "max_hold_minutes": 15},
            "exit_priority": exit_priority,
        },
        "scalping_aggressive": {
            "name": "Scalping Aggressive",
            "stop": {"type": "percent", "value": 0.25},
            "target": {"type": "percent", "value": 1.0},
            "trailing": {
                "enabled": True,
                "activation_type": "percent",
                "activation_value": 0.8,
                "trail_type": "percent",
                "trail_value": 0.4,
            },
            "time_stop": {"enabled": True, "max_hold_minutes": 20},
            "exit_priority": exit_priority,
        },
    }

    intraday_profiles: Dict[str, Any] = {
        "intraday_safe": {
            "name": "Intraday Safe",
            "stop": {"type": "percent", "value": 0.7},
            "target": {"type": "percent", "value": 1.1},
            "trailing": {
                "enabled": True,
                "activation_type": "percent",
                "activation_value": 0.8,
                "trail_type": "percent",
                "trail_value": 0.4,
            },
            "time_stop": {"enabled": True, "max_hold_minutes": 60},
            "exit_priority": exit_priority,
        },
        "intraday_balanced": {
            "name": "Intraday Balanced",
            "stop": {"type": "percent", "value": 0.6},
            # Target at ~2R relative to stop distance.
            "target": {"type": "rr_multiple", "value": 2.0},
            "trailing": {
                "enabled": True,
                "activation_type": "rr_multiple",
                "activation_value": 2.0,
                "trail_type": "percent",
                "trail_value": 0.5,
            },
            "time_stop": {"enabled": True, "max_hold_minutes": 90},
            "exit_priority": exit_priority,
        },
        "intraday_aggressive": {
            "name": "Intraday Aggressive",
            "stop": {"type": "percent", "value": 0.5},
            "target": {"type": "percent", "value": 2.0},
            "trailing": {
                "enabled": True,
                "activation_type": "percent",
                "activation_value": 1.2,
                "trail_type": "percent",
                "trail_value": 0.7,
            },
            "time_stop": {"enabled": True, "max_hold_minutes": 120},
            "exit_priority": exit_priority,
        },
    }

    swing_profiles: Dict[str, Any] = {
        "swing_tight": {
            "name": "Swing Tight",
            "stop": {"type": "percent", "value": 3.0},
            "target": {"type": "percent", "value": 6.0},
            "trailing": {
                "enabled": True,
                "activation_type": "percent",
                "activation_value": 4.0,
                "trail_type": "percent",
                "trail_value": 2.0,
            },
            # 3 trading days ~ 3 * 1440 minutes.
            "time_stop": {"enabled": True, "max_hold_minutes": 3 * 1440},
            "exit_priority": exit_priority,
        },
        "swing_trend": {
            "name": "Swing Trend",
            "stop": {"type": "percent", "value": 4.0},
            "target": {"type": "percent", "value": 10.0},
            "trailing": {
                "enabled": True,
                "activation_type": "percent",
                "activation_value": 6.0,
                "trail_type": "percent",
                "trail_value": 3.0,
            },
            # 7 trading days ~ 7 * 1440 minutes.
            "time_stop": {"enabled": True, "max_hold_minutes": 7 * 1440},
            "exit_priority": exit_priority,
        },
    }

    options_profiles: Dict[str, Any] = {
        "options_intraday": {
            "name": "Options Intraday",
            "stop": {"type": "percent", "value": 12.0},
            "target": {"type": "percent", "value": 22.0},
            "trailing": {
                "enabled": True,
                "activation_type": "percent",
                "activation_value": 15.0,
                "trail_type": "percent",
                "trail_value": 8.0,
            },
            # Same-day ~ 360 minutes.
            "time_stop": {"enabled": True, "max_hold_minutes": 360},
            "exit_priority": exit_priority,
        },
        "options_swing": {
            "name": "Options Swing",
            "stop": {"type": "percent", "value": 18.0},
            "target": {"type": "percent", "value": 35.0},
            "trailing": {
                "enabled": True,
                "activation_type": "percent",
                "activation_value": 25.0,
                "trail_type": "percent",
                "trail_value": 12.0,
            },
            # 2 trading days ~ 2 * 1440 minutes.
            "time_stop": {"enabled": True, "max_hold_minutes": 2 * 1440},
            "exit_priority": exit_priority,
        },
    }

    futures_profiles: Dict[str, Any] = {
        "futures_intraday": {
            "name": "Futures Intraday",
            "stop": {"type": "percent", "value": 0.9},
            "target": {"type": "percent", "value": 1.8},
            "trailing": {
                "enabled": True,
                "activation_type": "percent",
                "activation_value": 1.2,
                "trail_type": "percent",
                "trail_value": 0.7,
            },
            # 1 session ~ 360 minutes.
            "time_stop": {"enabled": True, "max_hold_minutes": 360},
            "exit_priority": exit_priority,
        },
        "futures_swing": {
            "name": "Futures Swing",
            "stop": {"type": "percent", "value": 1.5},
            "target": {"type": "percent", "value": 3.0},
            "trailing": {
                "enabled": True,
                "activation_type": "percent",
                "activation_value": 2.0,
                "trail_type": "percent",
                "trail_value": 1.0,
            },
            # 2 sessions ~ 720 minutes.
            "time_stop": {"enabled": True, "max_hold_minutes": 720},
            "exit_priority": exit_priority,
        },
    }

    config: Dict[str, Any] = {
        "modes": {
            "Scalping": {
                "exits": {
                    "default_profile": "scalping_balanced",
                    "profiles": scalping_profiles,
                }
            },
            "Intraday": {
                "exits": {
                    "default_profile": "intraday_balanced",
                    "profiles": intraday_profiles,
                }
            },
            "Swing": {
                "exits": {
                    "default_profile": "swing_trend",
                    "profiles": swing_profiles,
                }
            },
            "Options": {
                "exits": {
                    "default_profile": "options_intraday",
                    "profiles": options_profiles,
                }
            },
            "Futures": {
                "exits": {
                    "default_profile": "futures_intraday",
                    "profiles": futures_profiles,
                }
            },
        },
        # Contextual exit bandits per mode over the configured profiles.
        "bandit": {
            "Scalping": {
                "enabled": True,
                "epsilon": 0.15,
                "min_trades_per_action": 50,
                "actions": [
                    "scalping_safe",
                    "scalping_balanced",
                    "scalping_aggressive",
                ],
            },
            "Intraday": {
                "enabled": True,
                "epsilon": 0.2,
                "min_trades_per_action": 30,
                "actions": [
                    "intraday_safe",
                    "intraday_balanced",
                    "intraday_aggressive",
                ],
            },
            "Swing": {
                "enabled": True,
                "epsilon": 0.15,
                "min_trades_per_action": 50,
                "actions": [
                    "swing_tight",
                    "swing_trend",
                ],
            },
            "Options": {
                "enabled": True,
                "epsilon": 0.15,
                "min_trades_per_action": 50,
                "actions": [
                    "options_intraday",
                    "options_swing",
                ],
            },
            "Futures": {
                "enabled": True,
                "epsilon": 0.15,
                "min_trades_per_action": 50,
                "actions": [
                    "futures_intraday",
                    "futures_swing",
                ],
            },
        },
        "evaluation": {
            "Intraday": {
                "lookback_days": 60,
                "timeframe": "15m",
                "evaluation_horizon": "EOD",
            },
            "Swing": {
                "lookback_days": 180,
                "timeframe": "1D",
                "evaluation_horizon": "EOD",
            },
            "Options": {
                "lookback_days": 60,
                "timeframe": "5m",
                "evaluation_horizon": "EOD",
            },
            "Futures": {
                "lookback_days": 60,
                "timeframe": "5m",
                "evaluation_horizon": "EOD",
            },
        },
        # Entry-bandit configuration. Only Scalping and Intraday are used
        # today; the remaining modes are provided as placeholders.
        "entry_bandit": {
            "Scalping": {
                "enabled": True,
                "epsilon": 0.15,
                "min_trades_per_action": 50,
                # Actions parameterize score/RR thresholds and caps.
                "actions": {
                    "scalp_conservative": {
                        "bull_min_score": 60,
                        "bull_min_rr": 1.3,
                        "bear_max_score": 42,
                        "bear_min_rr": 1.3,
                        "max_long_picks": 5,
                        "max_short_picks": 3,
                    },
                    "scalp_balanced": {
                        "bull_min_score": 55,
                        "bull_min_rr": 1.2,
                        "bear_max_score": 45,
                        "bear_min_rr": 1.2,
                        "max_long_picks": 6,
                        "max_short_picks": 4,
                    },
                    "scalp_aggressive": {
                        "bull_min_score": 50,
                        "bull_min_rr": 1.0,
                        "bear_max_score": 48,
                        "bear_min_rr": 1.0,
                        "max_long_picks": 8,
                        "max_short_picks": 6,
                    },
                },
                # Optional regime-aware multipliers for caps.
                "regime_bias": {
                    "Bull": {"long_mult": 1.2, "short_mult": 0.5},
                    "Bear": {"long_mult": 0.6, "short_mult": 1.2},
                    "Range": {"long_mult": 1.0, "short_mult": 1.0},
                },
                "default_action": "scalp_balanced",
            },
            "Intraday": {
                "enabled": True,
                "epsilon": 0.2,
                "min_trades_per_action": 50,
                "actions": {
                    "intraday_conservative": {
                        "bull_min_score": 65,
                        "bull_min_rr": 1.7,
                        "bear_max_score": 40,
                        "bear_min_rr": 1.7,
                    },
                    "intraday_balanced": {
                        "bull_min_score": 60,
                        "bull_min_rr": 1.5,
                        "bear_max_score": 44,
                        "bear_min_rr": 1.5,
                    },
                    "intraday_aggressive": {
                        "bull_min_score": 55,
                        "bull_min_rr": 1.2,
                        "bear_max_score": 48,
                        "bear_min_rr": 1.2,
                    },
                },
                "regime_bias": {
                    "Bull": {"long_mult": 1.1, "short_mult": 0.7},
                    "Bear": {"long_mult": 0.7, "short_mult": 1.1},
                    "Range": {"long_mult": 1.0, "short_mult": 1.0},
                },
                "default_action": "intraday_balanced",
            },
            "Swing": {
                "enabled": True,
                "epsilon": 0.1,
                "min_trades_per_action": 50,
                "actions": {
                    "swing_trend_follow": {
                        "bull_min_score": 60,
                        "bull_min_rr": 1.8,
                        "bear_max_score": 40,
                        "bear_min_rr": 1.8,
                    }
                },
                "default_action": "swing_trend_follow",
            },
            "Options": {
                "enabled": True,
                "epsilon": 0.1,
                "min_trades_per_action": 50,
                "actions": {
                    "options_intraday_entry": {
                        "bull_min_score": 65,
                        "bull_min_rr": 1.8,
                        "bear_max_score": 38,
                        "bear_min_rr": 1.8,
                    }
                },
                "default_action": "options_intraday_entry",
            },
            "Futures": {
                "enabled": True,
                "epsilon": 0.1,
                "min_trades_per_action": 50,
                "actions": {
                    "futures_intraday_entry": {
                        "bull_min_score": 60,
                        "bull_min_rr": 1.7,
                        "bear_max_score": 42,
                        "bear_min_rr": 1.7,
                    }
                },
                "default_action": "futures_intraday_entry",
            },
        },
    }

    return config


def main() -> None:
    config = build_policy_config()

    name = "RL Baseline v1"
    description = (
        "Baseline RL meta-policy for Intraday/Swing/Options/Futures exits "
        "with contextual bandit for Intraday."
    )

    policy_id = create_rl_policy(
        name=name,
        config=config,
        description=description,
        status="DRAFT",
    )

    set_active_rl_policy(policy_id)

    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    print(f"[{now_iso}] Created and activated RL policy {policy_id}")


if __name__ == "__main__":
    main()
