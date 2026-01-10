"""
WebSocket API Router
Real-time market data streaming endpoints
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from typing import Dict, Any
import json
import logging
from datetime import datetime

from ..services.websocket_manager import get_websocket_manager
from ..services.zerodha_websocket import get_zerodha_websocket

router = APIRouter(tags=["websocket"])
logger = logging.getLogger(__name__)


@router.websocket("/ws/market")
async def websocket_market_data(websocket: WebSocket):
    """
    WebSocket endpoint for real-time market data
    
    Connection flow:
    1. Client connects to /v1/ws/market
    2. Server sends connection confirmation
    3. Client sends subscription requests
    4. Server streams real-time ticks
    
    Message format (Client → Server):
    {
        "action": "subscribe" | "unsubscribe",
        "symbols": ["RELIANCE", "TCS", "INFY"]
    }
    
    Message format (Server → Client):
    {
        "type": "tick",
        "symbol": "RELIANCE",
        "data": {
            "last_price": 2850.50,
            "volume": 1234567,
            "change_percent": 1.25,
            "timestamp": "2024-11-13T21:30:00"
        }
    }
    """
    manager = get_websocket_manager()
    
    try:
        # Accept connection
        await manager.connect(websocket)
        
        # Main message loop
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_text()
                message = json.loads(data)
                
                action = message.get('action')
                symbols = message.get('symbols', [])
                
                if action == 'subscribe':
                    await manager.subscribe(websocket, symbols)
                    
                elif action == 'unsubscribe':
                    await manager.unsubscribe(websocket, symbols)
                    
                elif action == 'ping':
                    await websocket.send_json({
                        'type': 'pong',
                        'timestamp': message.get('timestamp')
                    })
                    
                else:
                    await websocket.send_json({
                        'type': 'error',
                        'message': f'Unknown action: {action}'
                    })
                    
            except json.JSONDecodeError:
                await websocket.send_json({
                    'type': 'error',
                    'message': 'Invalid JSON format'
                })
                
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
        
    except Exception as e:
        logger.exception("WebSocket error")
        try:
            await manager.disconnect(websocket)
        except Exception:
            logger.exception("WebSocket disconnect failed")


@router.get("/ws/status")
async def get_websocket_status() -> Dict[str, Any]:
    """
    Get WebSocket service status
    
    Returns:
        Status information about WebSocket connections and subscriptions
    """
    try:
        manager = get_websocket_manager()
        zerodha_ws = get_zerodha_websocket()
        
        stats = manager.get_stats()
        
        return {
            "status": "operational" if zerodha_ws.is_connected else "disconnected",
            "zerodha_connected": zerodha_ws.is_connected,
            "zerodha_authenticated": zerodha_ws.is_authenticated,
            "active_connections": stats.get('active_connections', 0),
            "total_connections": stats.get('total_connections', 0),
            "messages_sent": stats.get('messages_sent', 0),
            "subscribed_symbols": stats.get('subscribed_symbols', []),
            "zerodha_stats": stats.get('zerodha_stats', {})
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting WebSocket status: {str(e)}"
        )


@router.post("/ws/start")
async def start_websocket_service() -> Dict[str, Any]:
    """
    Manually start Zerodha WebSocket service
    
    Returns:
        Start status
    """
    try:
        zerodha_ws = get_zerodha_websocket()
        
        if zerodha_ws.is_connected:
            return {
                "status": "already_running",
                "message": "WebSocket service is already running"
            }
        
        # Start WebSocket
        success = zerodha_ws.start()
        
        if success:
            return {
                "status": "success",
                "message": "WebSocket service started"
            }
        else:
            return {
                "status": "failed",
                "message": "Failed to start WebSocket service"
            }
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error starting WebSocket: {str(e)}"
        )


@router.post("/ws/stop")
async def stop_websocket_service() -> Dict[str, Any]:
    """
    Stop Zerodha WebSocket service
    
    Returns:
        Stop status
    """
    try:
        zerodha_ws = get_zerodha_websocket()
        
        if not zerodha_ws.is_connected:
            return {
                "status": "not_running",
                "message": "WebSocket service is not running"
            }
        
        # Stop WebSocket
        zerodha_ws.stop()
        
        return {
            "status": "success",
            "message": "WebSocket service stopped"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error stopping WebSocket: {str(e)}"
        )


@router.get("/ws/subscriptions")
async def get_subscriptions() -> Dict[str, Any]:
    """
    Get current WebSocket subscriptions
    
    Returns:
        List of subscribed symbols and connection counts
    """
    try:
        manager = get_websocket_manager()
        zerodha_ws = get_zerodha_websocket()
        
        # Get subscription info
        subscriptions = {}
        for symbol, connections in manager.symbol_subscriptions.items():
            subscriptions[symbol] = {
                'connection_count': len(connections),
                'token': zerodha_ws.symbol_to_token.get(symbol)
            }
        
        return {
            "status": "success",
            "total_symbols": len(subscriptions),
            "subscriptions": subscriptions
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting subscriptions: {str(e)}"
        )


@router.get("/ws/latest-ticks")
async def get_latest_ticks(symbols: str = None) -> Dict[str, Any]:
    """
    Get latest ticks from cache
    
    Args:
        symbols: Comma-separated list of symbols (optional)
        
    Returns:
        Latest tick data for requested symbols
    """
    try:
        zerodha_ws = get_zerodha_websocket()

        zerodha_stats = {}
        try:
            zerodha_stats = zerodha_ws.get_stats() or {}
        except Exception:
            zerodha_stats = {}
        
        if symbols:
            symbol_list = [s.strip() for s in symbols.split(',')]
            ticks = {}
            for symbol in symbol_list:
                tick = zerodha_ws.get_latest_tick(symbol)
                if tick:
                    ticks[symbol] = tick
        else:
            ticks = zerodha_ws.get_all_latest_ticks()
        
        return {
            "status": "success",
            "count": len(ticks),
            "ticks": ticks,
            "zerodha_connected": zerodha_ws.is_connected,
            "zerodha_authenticated": zerodha_ws.is_authenticated,
            "last_tick_time": zerodha_stats.get("last_tick_time"),
            "ticks_received": zerodha_stats.get("ticks_received"),
            "server_time": datetime.now().isoformat(),
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting latest ticks: {str(e)}"
        )
