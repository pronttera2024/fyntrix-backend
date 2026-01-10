"""
WebSocket Connection Manager
Manages WebSocket connections and broadcasts real-time data to clients
"""

import logging
import asyncio
import json
from typing import Set, Dict, Any, List
from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder
from datetime import datetime

from .zerodha_websocket import get_zerodha_websocket
from .event_logger import log_event
from ..config.index_universe import ALWAYS_ON_WS_SYMBOLS

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Manages WebSocket connections and broadcasts market data to connected clients
    """
    
    def __init__(self):
        # Active connections
        self.active_connections: Set[WebSocket] = set()
        
        # Connection subscriptions (websocket -> set of symbols)
        self.connection_subscriptions: Dict[WebSocket, Set[str]] = {}
        
        # Global subscriptions (symbol -> set of websockets)
        self.symbol_subscriptions: Dict[str, Set[WebSocket]] = {}
        
        # Zerodha WebSocket service
        self.zerodha_ws = get_zerodha_websocket()
        # Always-on universe symbols (e.g., NIFTY50, BANKNIFTY)
        self.always_on_symbols: Set[str] = set(ALWAYS_ON_WS_SYMBOLS or [])
        
        # Register callback for ticks
        self.zerodha_ws.register_tick_callback(self._handle_ticks)

        self._loop = None
        
        # Statistics
        self.stats = {
            'total_connections': 0,
            'active_connections': 0,
            'messages_sent': 0,
            'errors': 0
        }
        
        # Start Zerodha WebSocket if authenticated
        if self.zerodha_ws.load_access_token():
            try:
                asyncio.get_running_loop().create_task(self._start_zerodha_ws())
            except RuntimeError:
                # No running loop (e.g., during import-time / sync smoke checks)
                # The FastAPI server lifecycle starts Zerodha WS separately.
                pass

            # Subscribe to core universe so tick cache is warm even before any
            # UI component subscribes. ZerodhaWebSocketService.subscribe will
            # queue subscriptions until the underlying KiteTicker connects.
            self._subscribe_always_on_symbols()
        
        logger.info("✓ WebSocket manager initialized")
    
    async def _start_zerodha_ws(self):
        """Start Zerodha WebSocket in background"""
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self.zerodha_ws.start
            )
        except Exception as e:
            logger.error(f"Error starting Zerodha WebSocket: {e}")
    
    def _handle_ticks(self, ticks: List[Dict[str, Any]]):
        """Handle ticks from Zerodha and broadcast to clients"""
        try:
            # Process each tick
            for tick in ticks:
                token_raw = tick.get('instrument_token')
                token_norm = token_raw
                try:
                    if token_raw is not None:
                        token_norm = int(token_raw)
                except Exception:
                    token_norm = token_raw

                symbol = None
                if token_norm is not None:
                    symbol = self.zerodha_ws.token_to_symbol.get(token_norm)
                if not symbol and token_raw is not None:
                    symbol = self.zerodha_ws.token_to_symbol.get(str(token_raw))
                
                if not symbol:
                    continue
                
                # Get connections subscribed to this symbol
                connections = self.symbol_subscriptions.get(symbol, set())
                
                if not connections:
                    continue
                
                # Prepare message
                message = {
                    'type': 'tick',
                    'symbol': symbol,
                    'data': {
                        'last_price': tick.get('last_price'),
                        'volume': tick.get('volume'),
                        'change': tick.get('change'),
                        'change_percent': round(tick.get('change', 0) / tick.get('last_price', 1) * 100, 2) if tick.get('last_price') else 0,
                        'last_trade_time': tick.get('last_trade_time'),
                        'oi': tick.get('oi'),
                        'oi_day_high': tick.get('oi_day_high'),
                        'oi_day_low': tick.get('oi_day_low'),
                        'timestamp': datetime.now().isoformat()
                    }
                }

                safe_message = jsonable_encoder(message)
                try:
                    log_event(
                        event_type="ui_tick",
                        source="websocket_manager",
                        payload=safe_message,
                    )
                except Exception:
                    pass
                
                if self._loop is not None and self._loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self._broadcast_to_connections(connections, safe_message),
                        self._loop,
                    )
                else:
                    asyncio.create_task(self._broadcast_to_connections(connections, safe_message))
                
        except Exception as e:
            logger.error(f"Error handling ticks: {e}")
            self.stats['errors'] += 1
    
    async def _broadcast_to_connections(self, connections: Set[WebSocket], message: Dict[str, Any]):
        """Broadcast message to specific connections"""
        disconnected = set()
        
        for websocket in connections:
            try:
                await websocket.send_json(message)
                self.stats['messages_sent'] += 1
            except Exception as e:
                logger.error(f"Error sending to client: {e}")
                disconnected.add(websocket)
        
        # Remove disconnected clients
        for ws in disconnected:
            await self.disconnect(ws)

    def _subscribe_always_on_symbols(self):
        """Subscribe Zerodha WS to the core index universe once at startup."""
        try:
            symbols = sorted(self.always_on_symbols)
            if not symbols:
                return
            ok = self.zerodha_ws.subscribe(symbols)
            if ok:
                logger.info(
                    "✓ Always-on WS subscriptions initialised for %d symbols", len(symbols)
                )
            else:
                logger.warning(
                    "[WebSocketManager] Zerodha subscribe() reported failure for always-on symbols"
                )
        except Exception as e:
            logger.error("Error subscribing always-on WS symbols: %s", e)
    
    async def connect(self, websocket: WebSocket):
        """
        Accept and register a new WebSocket connection
        
        Args:
            websocket: FastAPI WebSocket instance
        """
        try:
            if self._loop is None:
                try:
                    self._loop = asyncio.get_running_loop()
                except RuntimeError:
                    self._loop = None

            await websocket.accept()
            self.active_connections.add(websocket)
            self.connection_subscriptions[websocket] = set()
            
            self.stats['total_connections'] += 1
            self.stats['active_connections'] = len(self.active_connections)
            
            logger.info(f"✓ Client connected (total: {len(self.active_connections)})")
            
            # Send welcome message
            await websocket.send_json({
                'type': 'connected',
                'message': 'Connected to ARISE WebSocket',
                'timestamp': datetime.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error connecting client: {e}")
            raise
    
    async def disconnect(self, websocket: WebSocket):
        """
        Disconnect and clean up a WebSocket connection
        
        Args:
            websocket: FastAPI WebSocket instance
        """
        try:
            # Remove from active connections
            self.active_connections.discard(websocket)
            
            # Get subscribed symbols for this connection
            symbols = self.connection_subscriptions.get(websocket, set())
            
            # Remove from symbol subscriptions
            for symbol in symbols:
                if symbol in self.symbol_subscriptions:
                    self.symbol_subscriptions[symbol].discard(websocket)
                    
                    # If no more connections for this symbol, unsubscribe from Zerodha
                    if not self.symbol_subscriptions[symbol]:
                        self.zerodha_ws.unsubscribe([symbol])
                        del self.symbol_subscriptions[symbol]
            
            # Remove connection subscriptions
            if websocket in self.connection_subscriptions:
                del self.connection_subscriptions[websocket]
            
            self.stats['active_connections'] = len(self.active_connections)
            
            logger.info(f"✓ Client disconnected (remaining: {len(self.active_connections)})")
            
        except Exception as e:
            logger.error(f"Error disconnecting client: {e}")
    
    async def subscribe(self, websocket: WebSocket, symbols: List[str]):
        """
        Subscribe a connection to symbols
        
        Args:
            websocket: FastAPI WebSocket instance
            symbols: List of symbols to subscribe to
        """
        try:
            if websocket not in self.connection_subscriptions:
                logger.warning("WebSocket not registered")
                return
            
            # Add to connection subscriptions
            self.connection_subscriptions[websocket].update(symbols)
            
            # Add to symbol subscriptions
            for symbol in symbols:
                if symbol not in self.symbol_subscriptions:
                    self.symbol_subscriptions[symbol] = set()
                self.symbol_subscriptions[symbol].add(websocket)
            
            # Subscribe to Zerodha if not already subscribed
            new_symbols = [s for s in symbols if s not in self.zerodha_ws.symbol_to_token]
            if new_symbols:
                self.zerodha_ws.subscribe(new_symbols)
            
            # Send confirmation
            await websocket.send_json({
                'type': 'subscribed',
                'symbols': symbols,
                'timestamp': datetime.now().isoformat()
            })
            
            logger.info(f"✓ Client subscribed to: {symbols}")
            
        except Exception as e:
            logger.error(f"Error subscribing: {e}")
            await websocket.send_json({
                'type': 'error',
                'message': f'Subscription failed: {str(e)}',
                'timestamp': datetime.now().isoformat()
            })
    
    async def unsubscribe(self, websocket: WebSocket, symbols: List[str]):
        """
        Unsubscribe a connection from symbols
        
        Args:
            websocket: FastAPI WebSocket instance
            symbols: List of symbols to unsubscribe from
        """
        try:
            if websocket not in self.connection_subscriptions:
                return
            
            # Remove from connection subscriptions
            self.connection_subscriptions[websocket].difference_update(symbols)
            
            # Remove from symbol subscriptions
            for symbol in symbols:
                if symbol in self.symbol_subscriptions:
                    self.symbol_subscriptions[symbol].discard(websocket)
                    
                    # If no more connections for this symbol, unsubscribe from Zerodha
                    if not self.symbol_subscriptions[symbol]:
                        self.zerodha_ws.unsubscribe([symbol])
                        del self.symbol_subscriptions[symbol]
            
            # Send confirmation
            await websocket.send_json({
                'type': 'unsubscribed',
                'symbols': symbols,
                'timestamp': datetime.now().isoformat()
            })
            
            logger.info(f"✓ Client unsubscribed from: {symbols}")
            
        except Exception as e:
            logger.error(f"Error unsubscribing: {e}")
    
    async def broadcast_all(self, message: Dict[str, Any]):
        """
        Broadcast message to all connected clients
        
        Args:
            message: Message to broadcast
        """
        disconnected = set()
        
        try:
            msg_type = message.get('type')
            if msg_type == 'top_picks_update':
                log_event(
                    event_type="top_picks_ws",
                    source="websocket_manager",
                    payload=message,
                )
            elif msg_type in ('market_summary_update', 'flows_update', 'scalping_monitor_update', 'portfolio_monitor_update'):
                log_event(
                    event_type="ws_broadcast",
                    source="websocket_manager",
                    payload=message,
                )
        except Exception:
            pass

        for websocket in self.active_connections:
            try:
                await websocket.send_json(message)
                self.stats['messages_sent'] += 1
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
                disconnected.add(websocket)
        
        # Clean up disconnected clients
        for ws in disconnected:
            await self.disconnect(ws)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get WebSocket manager statistics"""
        return {
            **self.stats,
            'zerodha_stats': self.zerodha_ws.get_stats(),
            'subscribed_symbols': list(self.symbol_subscriptions.keys())
        }


# Global instance
_ws_manager = None

def get_websocket_manager() -> WebSocketManager:
    """Get or create WebSocket manager instance"""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebSocketManager()
    return _ws_manager
