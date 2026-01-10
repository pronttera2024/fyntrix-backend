from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime

# Import services for real price data
from ..services.chart_data_service import chart_data_service
from ..agents.trade_strategy_agent import TradeStrategyAgent
from ..utils.trading_modes import (
    TradingMode,
    MODE_CONFIGS,
    normalize_mode,
    get_strategy_parameters,
)

router = APIRouter(tags=["strategy"])

# Initialize Trade Strategy Agent
trade_strategy_agent = TradeStrategyAgent() 

class SimReq(BaseModel):
    strategy: str
    symbol: str
    timeframe: str = "1d"
    params: Dict[str, Any] = {}

@router.post("/strategy/simulate")
def strategy_simulate(req: SimReq):
    # mock KPIs
    return {
        "kpis": {"trades": 24, "max_dd": 0.11, "final_equity": 1.18},
        "trades": [],
    }

class SuggestReq(BaseModel):
    symbol: str
    session_id: str
    risk: str
    modes: Dict[str, bool] = {}
    context: Dict[str, Any] | None = None
    primary_mode: Optional[str] = None


@router.post("/strategy/suggest")
async def strategy_suggest(req: SuggestReq):
    """
    Generate trade strategy using TradeStrategyAgent with real prices
    """
    s = req.symbol.upper()
    scores = (req.context or {}).get("scores") or {}

    # Determine primary trading mode
    mode_name: Optional[str] = None
    if req.primary_mode:
        mode_name = normalize_mode(req.primary_mode)
    else:
        # Derive from legacy modes map for backward compatibility
        if req.modes.get("Scalping"):
            mode_name = "Scalping"
        elif req.modes.get("Intraday"):
            mode_name = "Intraday"
        elif req.modes.get("Swing") or req.modes.get("Delivery") or req.modes.get("Positional"):
            mode_name = "Swing"
        elif req.modes.get("Options"):
            mode_name = "Options"
        elif req.modes.get("Futures"):
            mode_name = "Futures"
        elif req.modes.get("Commodity") or req.modes.get("Commodities"):
            mode_name = "Commodity"

    if not mode_name:
        mode_name = "Swing"

    try:
        primary_mode_enum = TradingMode(mode_name)
    except Exception:
        primary_mode_enum = TradingMode.SWING
    
    try:
        # Fetch real chart data to get current price
        chart_data = await chart_data_service.fetch_chart_data(s, '1M')
        if not chart_data or 'current' not in chart_data:
            raise ValueError(f"Unable to fetch chart data for {s}")
        
        current_price = chart_data['current']['price']
        candles = chart_data['candles']
        
        # Run TradeStrategyAgent to get real trade plan
        import pandas as pd
        candles_df = pd.DataFrame(candles)
        
        # Build context for agent
        context = {
            'current_price': current_price,
            'candles': candles_df,
            'agent_results': {name: {'score': score} for name, score in scores.items()}
        }
        
        # Get trade plan from agent
        agent_result = await trade_strategy_agent.analyze(s, context)
        trade_plan = agent_result.metadata.get('trade_plan', {})
        
        # Mode-aware parameters and timeframe label
        mode_params = get_strategy_parameters(primary_mode_enum, score=float(agent_result.score), current_price=current_price)
        horizon = mode_params.get("hold_duration") or mode_params.get("horizon") or MODE_CONFIGS[primary_mode_enum].horizon
        timeframe = f"{primary_mode_enum.value} ({horizon})"
        
        # Adjust sizing based on risk appetite
        if req.risk == "Conservative":
            sizing = "1-2% risk per trade"
        elif req.risk == "Moderate":
            sizing = "2-3% risk per trade"
        else:  # Aggressive
            sizing = "3-5% risk per trade"
        
        # Extract target prices
        targets_list = trade_plan.get('targets', [current_price * 1.02, current_price * 1.05, current_price * 1.08])
        entry_price = trade_plan.get('entry_price', current_price)
        stop_price = trade_plan.get('stop_loss', current_price * 0.97)
        
        # Calculate gains for each target
        target_gains = []
        for t in targets_list:
            gain_pct = ((t - entry_price) / entry_price) * 100
            target_gains.append(round(gain_pct, 2))
        
        # Format plan with real values - compatible with BOTH Chart and Analyze modal
        plan = {
            # For Analyze modal (simple format)
            "setup": trade_plan.get('direction', 'LONG').lower(),
            "entry": str(entry_price),
            "stop": str(stop_price),
            "targets": [str(t) for t in targets_list],  # ARRAY for Analyze modal
            "sizing": sizing,
            "timeframe": timeframe,
            "notes": [
                f"Current Price: ₹{current_price}",
                f"Setup Quality: {trade_plan.get('setup_quality', 'MODERATE')}",
                trade_plan.get('entry_timing', 'At current levels'),
                "Respect risk management and position sizing rules"
            ],
            "confidence": agent_result.score / 100,
            
            # For Chart modal (detailed format with objects) - RENAMED to target_details
            "entry_price": entry_price,
            "entry_timing": trade_plan.get('entry_timing', 'At current levels or on pullback to support'),
            "stop_loss": {
                "initial": stop_price,
                "trailing": trade_plan.get('trailing_stop', 'Move stop loss to breakeven after T1 is achieved. Trail below recent swing lows.'),
                "final": trade_plan.get('final_stop', 'Exit position if price closes below breakeven on daily timeframe')
            },
            "target_details": {  # RENAMED from "targets" to avoid conflict
                "T1": {
                    "price": targets_list[0] if len(targets_list) > 0 else entry_price * 1.02,
                    "gain": f"{target_gains[0]}%" if len(target_gains) > 0 else "2.0%",
                    "booking": "33%",
                    "rr_ratio": "1.5"
                },
                "T2": {
                    "price": targets_list[1] if len(targets_list) > 1 else entry_price * 1.05,
                    "gain": f"{target_gains[1]}%" if len(target_gains) > 1 else "5.0%",
                    "booking": "33%",
                    "rr_ratio": "2.5"
                },
                "T3": {
                    "price": targets_list[2] if len(targets_list) > 2 else entry_price * 1.08,
                    "gain": f"{target_gains[2]}%" if len(target_gains) > 2 else "8.0%",
                    "booking": "34%",
                    "rr_ratio": "4.0"
                }
            },
            "risk_reward": trade_plan.get('risk_reward', mode_params.get('risk_reward', '2.5')),
            "direction": trade_plan.get('direction', 'LONG'),
            "invalidation": trade_plan.get('invalidation', 'Close below support on daily timeframe'),
            "trailing_stop": trade_plan.get('trailing_stop', 'Move to breakeven after T1'),
            "final_stop": trade_plan.get('final_stop', 'Exit on daily close below breakeven')
        }
        
        # Generate explanations
        tech = float(scores.get("technical", 50))
        sent = float(scores.get("sentiment", 50))
        explain = [
            f"Using REAL current price of ₹{current_price} for {s}",
            f"Technical Score: {tech}% | Sentiment: {sent}%",
            f"Trade Direction: {trade_plan.get('direction', 'LONG')}",
            f"Risk/Reward: 1:{trade_plan.get('risk_reward', '2.5')}",
            agent_result.reasoning or "Multi-agent analysis complete"
        ]
        
        return {
            "plan": plan,
            "explain": explain,
            "as_of": datetime.utcnow().isoformat()+"Z",
        }
        
    except Exception as e:
        print(f"Error generating strategy for {s}: {e}")
        import traceback
        traceback.print_exc()
        
        # Fallback to safe defaults with current price if available
        try:
            chart_data = await chart_data_service.fetch_chart_data(s, '1M')
            current_price = chart_data['current']['price'] if chart_data else 100.0
        except:
            current_price = 100.0
        
        # Derive mode for fallback timeframe
        mode_name: Optional[str] = None
        if req.primary_mode:
            mode_name = normalize_mode(req.primary_mode)
        else:
            if req.modes.get("Scalping"):
                mode_name = "Scalping"
            elif req.modes.get("Intraday"):
                mode_name = "Intraday"
            elif req.modes.get("Swing") or req.modes.get("Delivery") or req.modes.get("Positional"):
                mode_name = "Swing"
            elif req.modes.get("Options"):
                mode_name = "Options"
            elif req.modes.get("Futures"):
                mode_name = "Futures"
            elif req.modes.get("Commodity") or req.modes.get("Commodities"):
                mode_name = "Commodity"

        if not mode_name:
            mode_name = "Swing"

        try:
            fallback_mode_enum = TradingMode(mode_name)
        except Exception:
            fallback_mode_enum = TradingMode.SWING

        fallback_params = get_strategy_parameters(fallback_mode_enum, score=50.0, current_price=current_price)
        fb_horizon = fallback_params.get("hold_duration") or fallback_params.get("horizon") or MODE_CONFIGS[fallback_mode_enum].horizon
        fallback_timeframe = f"{fallback_mode_enum.value} ({fb_horizon})"

        # Use same unified format for fallback
        entry_price = current_price
        stop_price = round(current_price * 0.97, 2)
        t1 = round(current_price * 1.02, 2)
        t2 = round(current_price * 1.05, 2)
        t3 = round(current_price * 1.08, 2)
        
        return {
            "plan": {
                # Simple format
                "setup": "neutral",
                "entry": str(entry_price),
                "stop": str(stop_price),
                "targets": [str(t1), str(t2), str(t3)],  # ARRAY for Analyze modal
                "sizing": "2-3% risk per trade",
                "timeframe": fallback_timeframe,
                "notes": [f"Error generating detailed strategy: {str(e)}", "Using conservative defaults"],
                "confidence": 0.5,
                # Detailed format for Chart modal - RENAMED to target_details
                "entry_price": entry_price,
                "entry_timing": "At current market price",
                "stop_loss": {
                    "initial": stop_price,
                    "trailing": "Move to breakeven after T1",
                    "final": "Exit if closes below entry"
                },
                "target_details": {  # RENAMED from "targets" to avoid conflict
                    "T1": {"price": t1, "gain": "2.0%", "booking": "33%", "rr_ratio": "1.5"},
                    "T2": {"price": t2, "gain": "5.0%", "booking": "33%", "rr_ratio": "2.5"},
                    "T3": {"price": t3, "gain": "8.0%", "booking": "34%", "rr_ratio": "4.0"}
                },
                "risk_reward": "2.5",
                "direction": "LONG",
                "invalidation": "Close below support",
            },
            "explain": [f"Error: {str(e)}", "Showing conservative defaults with real prices"],
            "as_of": datetime.utcnow().isoformat()+"Z",
        }
