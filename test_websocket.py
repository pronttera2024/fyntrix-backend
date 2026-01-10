"""
Test WebSocket Integration
"""

import asyncio
import websockets
import json
from datetime import datetime


async def test_websocket():
    """Test WebSocket connection and subscriptions"""
    
    uri = "ws://127.0.0.1:8000/v1/ws/market"
    
    print("🔌 Connecting to WebSocket...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✓ Connected!")
            
            # Wait for welcome message
            welcome = await websocket.recv()
            print(f"📩 Received: {welcome}")
            
            # Subscribe to symbols
            subscribe_message = {
                "action": "subscribe",
                "symbols": ["RELIANCE", "TCS", "INFY"]
            }
            
            print(f"\n📤 Subscribing to: {subscribe_message['symbols']}")
            await websocket.send(json.dumps(subscribe_message))
            
            # Receive confirmation
            confirmation = await websocket.recv()
            print(f"📩 Confirmation: {confirmation}")
            
            # Listen for ticks (for 30 seconds)
            print("\n📊 Listening for ticks (30 seconds)...\n")
            
            start_time = datetime.now()
            tick_count = 0
            
            while (datetime.now() - start_time).seconds < 30:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    data = json.loads(message)
                    
                    if data.get('type') == 'tick':
                        tick_count += 1
                        symbol = data.get('symbol')
                        tick_data = data.get('data', {})

                        last_price = tick_data.get('last_price')
                        change_percent = tick_data.get('change_percent')
                        volume = tick_data.get('volume', 0)

                        lp_str = f"{last_price}" if last_price is not None else "n/a"
                        cp_str = (
                            f"{float(change_percent):+.2f}%"
                            if change_percent is not None
                            else "n/a"
                        )
                        try:
                            vol_int = int(volume) if volume is not None else 0
                        except Exception:
                            vol_int = 0

                        print(
                            f"🔔 [{tick_count}] {symbol}: "
                            f"₹{lp_str} "
                            f"({cp_str}) "
                            f"Vol: {vol_int:,}"
                        )
                    
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    print(f"⚠️  Error receiving message: {e}")
            
            print(f"\n✓ Test complete! Received {tick_count} ticks")
            
            # Unsubscribe
            unsubscribe_message = {
                "action": "unsubscribe",
                "symbols": ["RELIANCE", "TCS", "INFY"]
            }
            await websocket.send(json.dumps(unsubscribe_message))
            
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    print("="*60)
    print("ARISE WebSocket Test")
    print("="*60)
    print()
    
    asyncio.run(test_websocket())
    
    print()
    print("="*60)
