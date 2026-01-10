"""
Zerodha WebSocket Service
Real-time streaming quotes using KiteTicker
"""

import os
import logging
import asyncio
from typing import Dict, Set, Callable, Optional, Any, List
from datetime import datetime
from kiteconnect import KiteTicker
import json
from .event_logger import log_event

logger = logging.getLogger(__name__)


class ZerodhaWebSocketService:
    """
    WebSocket service for real-time market data from Zerodha
    Uses KiteTicker for streaming quotes
    """
    
    def __init__(self):
        self.api_key = os.getenv('ZERODHA_API_KEY', '')
        self.access_token = None
        self.ticker = None
        
        # Connection state
        self.is_connected = False
        self.is_authenticated = False
        
        # Subscriptions
        self.subscribed_tokens: Set[int] = set()
        self.symbol_to_token: Dict[str, int] = {}
        self.token_to_symbol: Dict[int, str] = {}
        
        # Callbacks
        self.on_tick_callbacks: List[Callable] = []
        self.on_connect_callbacks: List[Callable] = []
        self.on_close_callbacks: List[Callable] = []
        self.on_error_callbacks: List[Callable] = []
        
        # Latest ticks cache
        self.latest_ticks: Dict[int, Dict[str, Any]] = {}
        
        # Statistics
        self.stats = {
            'ticks_received': 0,
            'reconnections': 0,
            'errors': 0,
            'last_tick_time': None,
            'last_error_code': None,
            'last_error_reason': None,
            'last_close_code': None,
            'last_close_reason': None,
        }
        
        logger.info("✓ Zerodha WebSocket service initialized")
    
    def load_access_token(self) -> bool:
        """Load access token from file"""
        try:
            from pathlib import Path
            token_file = Path(__file__).parent.parent.parent / '.zerodha_token'
            
            if token_file.exists():
                with open(token_file, 'r') as f:
                    self.access_token = f.read().strip()
                
                if self.access_token:
                    logger.info("✓ Zerodha access token loaded")
                    self.is_authenticated = True
                    return True
            
            # Fallback: try environment variable if token file is missing
            env_token = os.getenv('ZERODHA_ACCESS_TOKEN')
            if env_token:
                self.access_token = env_token.strip()
                if self.access_token:
                    logger.info("✓ Zerodha access token loaded from environment")
                    self.is_authenticated = True
                    return True
            
            logger.warning("⚠️  No Zerodha access token found")
            return False
            
        except Exception as e:
            logger.error(f"Error loading access token: {e}")
            return False
    
    def get_instrument_tokens(self, symbols: List[str]) -> Dict[str, int]:
        """
        Get instrument tokens for symbols
        Uses Zerodha provider's instrument lookup
        
        Args:
            symbols: List of trading symbols (e.g., ['RELIANCE', 'TCS'])
            
        Returns:
            Dict mapping symbol to instrument token
        """
        try:
            tokens = {}

            def _looks_like_nfo_symbol(sym: Any) -> bool:
                try:
                    s = str(sym or "").upper().strip()
                except Exception:
                    return False
                if not s:
                    return False
                if not any(c.isdigit() for c in s):
                    return False
                return s.endswith("CE") or s.endswith("PE") or s.endswith("FUT")

            try:
                from .zerodha_service import zerodha_service

                instruments_cache = getattr(zerodha_service, "instruments_cache", None) or {}
                if instruments_cache:
                    for symbol in symbols:
                        token_raw = instruments_cache.get(str(symbol).upper())
                        if token_raw:
                            try:
                                token = int(token_raw)
                            except Exception:
                                token = token_raw

                            tokens[symbol] = token
                            self.symbol_to_token[symbol] = token
                            self.token_to_symbol[token] = symbol
                            # Defensive: some tick payloads may deliver token as str
                            try:
                                self.token_to_symbol[str(token)] = symbol
                            except Exception:
                                pass
            except Exception:
                instruments_cache = {}

            # Fallback to provider (may require fetching instruments). Only do this
            # for symbols we couldn't resolve from the cached instrument map.
            missing = [s for s in symbols if s not in tokens]
            if missing:
                from ..providers.zerodha_provider import get_zerodha_provider

                zerodha = get_zerodha_provider()
                for symbol in missing:
                    exchange = "NFO" if _looks_like_nfo_symbol(symbol) else "NSE"
                    token_raw = zerodha.get_instrument_token(symbol, exchange=exchange)
                    if token_raw:
                        try:
                            token = int(token_raw)
                        except Exception:
                            token = token_raw

                        tokens[symbol] = token
                        self.symbol_to_token[symbol] = token
                        self.token_to_symbol[token] = symbol
                        try:
                            self.token_to_symbol[str(token)] = symbol
                        except Exception:
                            pass
            
            return tokens
            
        except Exception as e:
            logger.error(f"Error getting instrument tokens: {e}")
            return {}
    
    def initialize_ticker(self) -> bool:
        """Initialize KiteTicker instance"""
        try:
            if not self.is_authenticated:
                if not self.load_access_token():
                    logger.error("Cannot initialize ticker without access token")
                    return False
            
            if not self.api_key or not self.access_token:
                logger.error("API key or access token missing")
                return False
            
            # Create KiteTicker instance
            self.ticker = KiteTicker(self.api_key, self.access_token)

            # Configure reconnect behavior (KiteTicker defaults can be noisy).
            try:
                reconnect_interval = int(os.getenv("ZERODHA_WS_RECONNECT_INTERVAL_SEC", "5") or "5")
            except Exception:
                reconnect_interval = 5
            try:
                reconnect_retries = int(os.getenv("ZERODHA_WS_RECONNECT_RETRIES", "30") or "30")
            except Exception:
                reconnect_retries = 30
            reconnect_interval = max(1, min(reconnect_interval, 60))
            reconnect_retries = max(0, min(reconnect_retries, 200))
            try:
                self.ticker.enable_reconnect(True, reconnect_interval, reconnect_retries)
            except Exception:
                pass
            
            # Set up callbacks
            self.ticker.on_ticks = self._on_ticks
            self.ticker.on_connect = self._on_connect
            self.ticker.on_close = self._on_close
            self.ticker.on_error = self._on_error
            self.ticker.on_reconnect = self._on_reconnect
            self.ticker.on_noreconnect = self._on_noreconnect
            
            logger.info("✓ KiteTicker initialized")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing ticker: {e}")
            return False
    
    def _on_ticks(self, ws, ticks):
        """Callback when ticks are received"""
        try:
            self.stats['ticks_received'] += len(ticks)
            self.stats['last_tick_time'] = datetime.now().isoformat()
            try:
                for tick in ticks:
                    item: Dict[str, Any] = {}
                    for key, value in tick.items():
                        if isinstance(value, datetime):
                            item[key] = value.isoformat()
                        else:
                            item[key] = value

                    token = tick.get("instrument_token")
                    symbol = None
                    if token is not None:
                        symbol = self.token_to_symbol.get(token, str(token))

                    payload: Dict[str, Any] = {"tick": item}
                    if token is not None:
                        payload["instrument_token"] = token
                    if symbol is not None:
                        payload["symbol"] = symbol

                    log_event(
                        event_type="market_tick",
                        source="zerodha_websocket",
                        payload=payload,
                    )
            except Exception:
                pass
            
            # Cache latest ticks
            for tick in ticks:
                token_raw = tick.get('instrument_token')
                if token_raw:
                    try:
                        token = int(token_raw)
                    except Exception:
                        token = token_raw
                    self.latest_ticks[token] = tick

            # Call registered callbacks
            for callback in self.on_tick_callbacks:
                try:
                    callback(ticks)
                except Exception as e:
                    logger.error(f"Error in tick callback: {e}")
            
            # Log sample tick
            if ticks:
                sample = ticks[0]
                token = sample.get('instrument_token')
                symbol = self.token_to_symbol.get(token, token)
                logger.debug(f"Tick: {symbol} @ ₹{sample.get('last_price', 0)}")
                
        except Exception as e:
            logger.error(f"Error processing ticks: {e}")
            self.stats['errors'] += 1
    
    def _on_connect(self, ws, response):
        """Callback when connection is established"""
        try:
            self.is_connected = True
            logger.info("✓ WebSocket connected to Zerodha")
            
            # Subscribe to tokens if any
            if self.subscribed_tokens:
                self.ticker.subscribe(list(self.subscribed_tokens))
                self.ticker.set_mode(self.ticker.MODE_FULL, list(self.subscribed_tokens))
                logger.info(f"✓ Subscribed to {len(self.subscribed_tokens)} instruments")
            
            # Call registered callbacks
            for callback in self.on_connect_callbacks:
                try:
                    callback(response)
                except Exception as e:
                    logger.error(f"Error in connect callback: {e}")
                    
        except Exception as e:
            logger.error(f"Error in connect handler: {e}")
    
    def _on_close(self, ws, code, reason):
        """Callback when connection is closed"""
        self.is_connected = False
        logger.warning(f"WebSocket closed: {code} - {reason}")
        self.stats['last_close_code'] = code
        self.stats['last_close_reason'] = reason
        
        for callback in self.on_close_callbacks:
            try:
                callback(code, reason)
            except Exception as e:
                logger.error(f"Error in close callback: {e}")
    
    def _on_error(self, ws, code, reason):
        """Callback when error occurs"""
        self.stats['errors'] += 1
        self.stats['last_error_code'] = code
        self.stats['last_error_reason'] = reason

        # Some errors (notably handshake/upgrade failures) leave the connection
        # in an unusable state. Ensure status reflects that we are not connected.
        try:
            reason_s = str(reason or "")
            code_i = None
            try:
                code_i = int(code) if code is not None else None
            except Exception:
                code_i = None

            if code_i in (1006, 403) or "403" in reason_s or "upgrade failed" in reason_s.lower():
                self.is_connected = False

                # Authentication failures should stop reconnect storms and force re-auth.
                if code_i == 403 or "403" in reason_s or "forbidden" in reason_s.lower():
                    self.is_authenticated = False
                    try:
                        self.access_token = None
                    except Exception:
                        pass
                    try:
                        if self.ticker:
                            self.ticker.enable_reconnect(False)
                    except Exception:
                        pass
                    logger.warning(
                        "Zerodha WebSocket auth failed (403). Token likely expired/mismatched. Re-auth via /v1/zerodha/login-url"
                    )
        except Exception:
            self.is_connected = False

        logger.error(f"WebSocket error: {code} - {reason}")
        
        for callback in self.on_error_callbacks:
            try:
                callback(code, reason)
            except Exception as e:
                logger.error(f"Error in error callback: {e}")
    
    def _on_reconnect(self, ws, attempts_count):
        """Callback when reconnection attempt is made"""
        self.stats['reconnections'] += 1
        logger.info(f"Reconnecting... (attempt {attempts_count})")
    
    def _on_noreconnect(self, ws):
        """Callback when reconnection fails"""
        logger.error("Reconnection failed - no more attempts")
        self.is_connected = False
    
    def start(self):
        """Start WebSocket connection (blocking)"""
        try:
            # Always ensure we have the latest access token before (re)starting
            self.load_access_token()

            # Always (re)initialize KiteTicker so that token changes take effect
            self.ticker = None
            if not self.initialize_ticker():
                logger.error("Cannot start WebSocket - initialization failed")
                return False
            
            logger.info("Starting WebSocket connection...")
            self.ticker.connect(threaded=True)
            return True
            
        except Exception as e:
            logger.error(f"Error starting WebSocket: {e}")
            return False
    
    def stop(self):
        """Stop WebSocket connection"""
        try:
            if self.ticker and self.is_connected:
                self.ticker.close()
                logger.info("✓ WebSocket stopped")
            
        except Exception as e:
            logger.error(f"Error stopping WebSocket: {e}")
    
    def subscribe(self, symbols: List[str]) -> bool:
        """
        Subscribe to symbols for real-time updates
        
        Args:
            symbols: List of trading symbols
            
        Returns:
            True if subscription successful
        """
        try:
            # Get instrument tokens
            tokens_map = self.get_instrument_tokens(symbols)
            
            if not tokens_map:
                logger.warning(f"No tokens found for symbols: {symbols}")
                return False
            
            tokens = list(tokens_map.values())
            self.subscribed_tokens.update(tokens)
            
            # Subscribe if connected
            if self.is_connected and self.ticker:
                self.ticker.subscribe(tokens)
                self.ticker.set_mode(self.ticker.MODE_FULL, tokens)
                logger.info(f"✓ Subscribed to {len(tokens)} instruments: {list(tokens_map.keys())}")
            else:
                logger.info(f"✓ Queued subscription for {len(tokens)} instruments (will subscribe on connect)")
            
            return True
            
        except Exception as e:
            logger.error(f"Error subscribing to symbols: {e}")
            return False
    
    def unsubscribe(self, symbols: List[str]) -> bool:
        """
        Unsubscribe from symbols
        
        Args:
            symbols: List of trading symbols
            
        Returns:
            True if unsubscription successful
        """
        try:
            tokens = [self.symbol_to_token.get(symbol) for symbol in symbols if symbol in self.symbol_to_token]
            
            if not tokens:
                logger.warning(f"No tokens found for symbols: {symbols}")
                return False
            
            # Remove from subscribed set
            self.subscribed_tokens.difference_update(tokens)
            
            # Unsubscribe if connected
            if self.is_connected and self.ticker:
                self.ticker.unsubscribe(tokens)
                logger.info(f"✓ Unsubscribed from {len(tokens)} instruments")
            
            return True
            
        except Exception as e:
            logger.error(f"Error unsubscribing from symbols: {e}")
            return False
    
    def get_latest_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get latest tick for a symbol"""
        token = self.symbol_to_token.get(symbol)
        if token:
            return self.latest_ticks.get(token)
        return None
    
    def get_all_latest_ticks(self) -> Dict[str, Dict[str, Any]]:
        """Get all latest ticks"""
        result = {}
        for token, tick in self.latest_ticks.items():
            symbol = self.token_to_symbol.get(token, str(token))
            result[symbol] = tick
        return result
    
    def register_tick_callback(self, callback: Callable):
        """Register callback for tick events"""
        self.on_tick_callbacks.append(callback)
    
    def register_connect_callback(self, callback: Callable):
        """Register callback for connection events"""
        self.on_connect_callbacks.append(callback)
    
    def register_close_callback(self, callback: Callable):
        """Register callback for close events"""
        self.on_close_callbacks.append(callback)
    
    def register_error_callback(self, callback: Callable):
        """Register callback for error events"""
        self.on_error_callbacks.append(callback)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get WebSocket statistics"""
        return {
            **self.stats,
            'is_connected': self.is_connected,
            'is_authenticated': self.is_authenticated,
            'subscribed_count': len(self.subscribed_tokens),
            'subscribed_symbols': list(self.symbol_to_token.keys())
        }


# Global instance
_zerodha_ws = None

def get_zerodha_websocket() -> ZerodhaWebSocketService:
    """Get or create Zerodha WebSocket service instance"""
    global _zerodha_ws
    if _zerodha_ws is None:
        _zerodha_ws = ZerodhaWebSocketService()
    return _zerodha_ws
