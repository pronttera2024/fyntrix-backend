"""
Test Scalping System End-to-End

This script tests the complete scalping architecture:
1. Generates test scalping picks with exit strategies
2. Triggers monitoring
3. Verifies exits are detected
4. Checks audit trail

Run: python test_scalping_system.py
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


async def main():
    print("=" * 60)
    print("SCALPING SYSTEM END-TO-END TEST")
    print("=" * 60)
    print()
    
    # Step 1: Generate test scalping picks
    print("STEP 1: Generating Test Scalping Picks")
    print("-" * 60)
    
    picks_dir = Path(__file__).parent / "data" / "top_picks_intraday"
    picks_dir.mkdir(parents=True, exist_ok=True)
    
    # Create test picks with different scenarios
    test_picks = [
        {
            "symbol": "SBIN",
            "entry_price": 625.50,
            "recommendation": "Buy",
            "mode": "Scalping",
            "entry_time": (datetime.now(timezone.utc) - timedelta(minutes=25)).isoformat().replace('+00:00', 'Z'),
            "exit_strategy": {
                "target_price": 628.63,
                "target_pct": 0.5,
                "stop_loss_price": 623.00,
                "stop_pct": 0.4,
                "max_hold_mins": 60,
                "trailing_stop": {
                    "enabled": True,
                    "activation_pct": 0.2,
                    "trail_distance_pct": 0.3
                },
                "atr": 0.42,
                "atr_pct": 0.067,
                "scalp_type": "standard",
                "description": "Standard scalp: ATR=0.07%, Target=0.5%, Stop=0.4%"
            },
            "scores": {
                "scalping": 78.5,
                "technical": 72.0,
                "microstructure": 81.0,
                "pattern_recognition": 68.0
            },
            "confidence": "High",
            "score_blend": 75.0
        },
        {
            "symbol": "RELIANCE",
            "entry_price": 2458.20,
            "recommendation": "Buy",
            "mode": "Scalping",
            "entry_time": (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat().replace('+00:00', 'Z'),
            "exit_strategy": {
                "target_price": 2470.50,
                "target_pct": 0.5,
                "stop_loss_price": 2448.40,
                "stop_pct": 0.4,
                "max_hold_mins": 60,
                "trailing_stop": {
                    "enabled": True,
                    "activation_pct": 0.2,
                    "trail_distance_pct": 0.3
                },
                "atr": 1.23,
                "atr_pct": 0.05,
                "scalp_type": "standard",
                "description": "Standard scalp: ATR=0.05%, Target=0.5%, Stop=0.4%"
            },
            "scores": {
                "scalping": 82.0,
                "technical": 76.0,
                "microstructure": 85.0,
                "pattern_recognition": 71.0
            },
            "confidence": "High",
            "score_blend": 78.5
        },
        {
            "symbol": "HDFCBANK",
            "entry_price": 1642.30,
            "recommendation": "Buy",
            "mode": "Scalping",
            "entry_time": (datetime.now(timezone.utc) - timedelta(minutes=70)).isoformat().replace('+00:00', 'Z'),  # Will trigger time exit
            "exit_strategy": {
                "target_price": 1650.52,
                "target_pct": 0.5,
                "stop_loss_price": 1635.73,
                "stop_pct": 0.4,
                "max_hold_mins": 60,
                "trailing_stop": {
                    "enabled": True,
                    "activation_pct": 0.2,
                    "trail_distance_pct": 0.3
                },
                "atr": 0.82,
                "atr_pct": 0.05,
                "scalp_type": "standard",
                "description": "Standard scalp: ATR=0.05%, Target=0.5%, Stop=0.4%"
            },
            "scores": {
                "scalping": 74.0,
                "technical": 68.0,
                "microstructure": 79.0,
                "pattern_recognition": 65.0
            },
            "confidence": "Medium",
            "score_blend": 71.5
        }
    ]
    
    # Save test picks
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    file_path = picks_dir / f"picks_test_scalping_{timestamp}.json"
    
    payload = {
        "items": test_picks,
        "as_of": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        "universe": "test",
        "mode": "Scalping",
        "test": True
    }
    
    with open(file_path, 'w') as f:
        json.dump(payload, f, indent=2)
    
    print(f"✅ Generated {len(test_picks)} test scalping picks")
    print(f"   Saved to: {file_path.name}")
    print()
    
    for pick in test_picks:
        entry_time = datetime.fromisoformat(pick['entry_time'].replace('Z', '+00:00'))
        elapsed_mins = (datetime.now(timezone.utc) - entry_time).total_seconds() / 60
        print(f"   - {pick['symbol']}: Entry @ ₹{pick['entry_price']}, "
              f"Elapsed: {elapsed_mins:.1f} mins, "
              f"Target: ₹{pick['exit_strategy']['target_price']}")
    print()
    
    # Step 2: Test Exit Tracker
    print("STEP 2: Testing Exit Tracker")
    print("-" * 60)
    
    from app.services.scalping_exit_tracker import scalping_exit_tracker
    
    # Get active positions
    active_positions = scalping_exit_tracker.get_active_positions(lookback_hours=2)
    print(f"✅ Active positions found: {len(active_positions)}")
    
    if active_positions:
        print("   Active positions:")
        for pos in active_positions[:5]:
            print(f"   - {pos['symbol']}: Entry @ ₹{pos.get('entry_price', 0)}")
    print()
    
    # Step 3: Trigger Auto-Monitoring
    print("STEP 3: Triggering Auto-Monitoring")
    print("-" * 60)
    
    from app.agents.auto_monitoring_agent import auto_monitoring_agent
    
    result = await auto_monitoring_agent.monitor_scalping_positions(manual_trigger=True)
    
    print(f"✅ Monitoring complete")
    print(f"   Active positions: {result['active_positions']}")
    print(f"   Exits detected: {result['exits_detected']}")
    print()
    
    if result['exits_detected'] > 0:
        print("   Detected exits:")
        for exit in result['exits']:
            print(f"   - {exit['symbol']}: {exit['exit_reason']} @ ₹{exit['exit_price']}, "
                  f"return: {exit['return_pct']:.2f}%")
    print()
    
    # Step 4: Check Audit Trail
    print("STEP 4: Checking Audit Trail")
    print("-" * 60)
    
    # Get daily summary
    summary = scalping_exit_tracker.get_daily_summary()
    
    print(f"✅ Daily Summary")
    print(f"   Total exits: {summary['total_exits']}")
    print(f"   Winning exits: {summary['winning_exits']}")
    print(f"   Losing exits: {summary['losing_exits']}")
    if summary['total_exits'] > 0:
        print(f"   Win rate: {(summary['winning_exits'] / summary['total_exits'] * 100):.1f}%")
        print(f"   Avg return: {summary['avg_return']:.2f}%")
        print(f"   Avg hold time: {summary['avg_hold_time_mins']:.1f} mins")
    print()
    
    # Step 5: Test API Endpoints
    print("STEP 5: Testing API Endpoints")
    print("-" * 60)
    print("   To test API endpoints, run:")
    print()
    print("   # Get active positions")
    print("   curl http://localhost:8000/api/v1/scalping/active-positions")
    print()
    print("   # Trigger manual monitoring")
    print("   curl -X POST http://localhost:8000/api/v1/scalping/monitor?manual=true")
    print()
    print("   # Get daily summary")
    print("   curl http://localhost:8000/api/v1/scalping/daily-summary")
    print()
    print("   # Get 7-day stats")
    print("   curl http://localhost:8000/api/v1/scalping/stats?days=7")
    print()
    
    print("=" * 60)
    print("✅ TEST COMPLETE!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Start the backend: cd backend && python -m uvicorn app.main:app --reload")
    print("2. Start the frontend: cd frontend && npm start")
    print("3. Click '⚡ Scalping' button in the sidebar")
    print("4. Click 'Check Now' to trigger monitoring")
    print("5. Watch for exit notifications!")
    print()
    print(f"Test picks saved to: {file_path}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
