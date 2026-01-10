"""
Zerodha Authentication Router
Handles Zerodha Kite Connect OAuth flow
"""

from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timedelta
import os
import logging
from pathlib import Path
from ..services.zerodha_service import zerodha_service
from ..services.token_monitor import get_token_monitor

router = APIRouter()

logger = logging.getLogger(__name__)

@router.get("/zerodha/login-url")
async def get_zerodha_login_url():
    """
    Get Zerodha login URL to start authentication.
    
    Returns:
        Login URL to redirect user to
    """
    try:
        login_url = zerodha_service.get_login_url()
        return {
            "login_url": login_url,
            "instructions": [
                "1. Open the login_url in your browser",
                "2. Login with your Zerodha credentials",
                "3. After login, you'll be redirected to a URL",
                "4. Copy the 'request_token' from the redirected URL",
                "5. Call POST /v1/zerodha/session with the request_token"
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/zerodha/session")
async def create_zerodha_session(request_token: str = Query(...)):
    """
    Generate Zerodha session using request_token.
    
    Args:
        request_token: Token received after login redirect
        
    Returns:
        Session details with access_token
    """
    try:
        session = zerodha_service.generate_session(request_token)
        
        # Save access token to file so it persists across server reloads
        import os
        from pathlib import Path
        token_file = Path(__file__).parent.parent.parent / '.zerodha_token'
        with open(token_file, 'w') as f:
            f.write(session.get("access_token"))
        logger.info("Access token saved to %s", token_file)
        
        # Save token metadata for expiry tracking
        expires_at = datetime.now() + timedelta(hours=24)
        monitor = get_token_monitor()
        monitor.save_token_metadata(
            expires_at=expires_at,
            user_name=session.get("user_name")
        )
        logger.info("Token expiry tracking enabled (expires: %s)", expires_at)

        # Also set environment variable for components that read ZERODHA_ACCESS_TOKEN
        try:
            os.environ["ZERODHA_ACCESS_TOKEN"] = session.get("access_token")
        except Exception:
            pass

        # Ensure Zerodha data provider sees the new token
        try:
            from ..providers.zerodha_provider import get_zerodha_provider

            provider = get_zerodha_provider()
            provider.access_token = session.get("access_token")
            if provider.kite:
                provider.kite.set_access_token(session.get("access_token"))
                provider._load_instruments()
        except Exception as e:
            logging.getLogger(__name__).warning("Could not update Zerodha provider with new token: %s", e)

        # Attempt to start Zerodha WebSocket service with new token
        websocket_started = False
        try:
            from ..services.zerodha_websocket import get_zerodha_websocket

            zerodha_ws = get_zerodha_websocket()
            zerodha_ws.load_access_token()
            if not zerodha_ws.is_connected:
                websocket_started = bool(zerodha_ws.start())
            else:
                websocket_started = True
        except Exception as e:
            logging.getLogger(__name__).warning("Could not auto-start Zerodha WebSocket: %s", e)

        return {
            "status": "success",
            "message": "Zerodha session created successfully",
            "access_token": session.get("access_token"),
            "user_id": session.get("user_id"),
            "user_name": session.get("user_name"),
            "expires_at": expires_at.isoformat(),
            "expires": "24 hours",
            "websocket_started": websocket_started,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Session generation failed: {str(e)}")


@router.get("/zerodha/status")
async def get_zerodha_status():
    """
    Check Zerodha authentication status.
    
    Returns:
        Current authentication status
    """
    api_key_set = bool(os.getenv("ZERODHA_API_KEY"))
    api_secret_set = bool(os.getenv("ZERODHA_API_SECRET"))

    token_file = Path(__file__).parent.parent.parent / ".zerodha_token"
    token_file_present = token_file.exists()

    token_present = zerodha_service.access_token is not None
    token_valid = False
    token_error: str | None = None

    # Validate token by performing a lightweight authenticated call.
    # NOTE: Access tokens expire daily; a token may be "present" but invalid.
    if token_present and getattr(zerodha_service, "kite", None) is not None:
        try:
            # profile() is lightweight and fails fast when token is invalid.
            _ = zerodha_service.kite.profile()
            token_valid = True
        except Exception as e:
            token_valid = False
            token_error = str(e)

    authenticated = bool(api_key_set and api_secret_set and token_present and token_valid)

    message = "Authenticated and ready"
    if not api_key_set or not api_secret_set:
        message = "Zerodha API credentials not configured (check backend/.env)"
    elif not token_present:
        message = "Not authenticated - call /v1/zerodha/login-url to start"
    elif not token_valid:
        message = "Access token present but INVALID/EXPIRED - re-auth via /v1/zerodha/login-url"

    return {
        "authenticated": authenticated,
        "api_key_configured": api_key_set,
        "api_secret_configured": api_secret_set,
        "token_file_present": token_file_present,
        "access_token_present": token_present,
        "access_token_valid": token_valid,
        "access_token_error": token_error,
        "message": message,
    }


@router.post("/zerodha/set-token")
async def set_access_token(access_token: str = Query(...)):
    """
    Directly set access token (for testing or if you already have a token).
    
    Args:
        access_token: Valid Zerodha access token
        
    Returns:
        Status message
    """
    try:
        logger = logging.getLogger(__name__)

        # Update primary Zerodha service
        zerodha_service.access_token = access_token
        if zerodha_service.kite:
            zerodha_service.kite.set_access_token(access_token)

        # Persist token to file so other components (provider, WebSocket, tests) can load it
        token_file = Path(__file__).parent.parent.parent / ".zerodha_token"
        try:
            with open(token_file, "w") as f:
                f.write(access_token)
            logger.info(f"✓ Access token saved to {token_file}")
        except Exception as e:
            logger.warning(f"Could not write Zerodha token file: {e}")

        # Also set environment variable for components that read ZERODHA_ACCESS_TOKEN
        try:
            os.environ["ZERODHA_ACCESS_TOKEN"] = access_token
        except Exception as e:
            logger.warning(f"Could not set ZERODHA_ACCESS_TOKEN env var: {e}")

        # Save token metadata for expiry tracking (24 hours)
        try:
            expires_at = datetime.now() + timedelta(hours=24)
            monitor = get_token_monitor()
            monitor.save_token_metadata(expires_at=expires_at, user_name=None)
        except Exception as e:
            logger.warning(f"Could not save token metadata: {e}")

        # Ensure Zerodha data provider sees the new token
        try:
            from ..providers.zerodha_provider import get_zerodha_provider

            provider = get_zerodha_provider()
            provider.access_token = access_token
            if provider.kite:
                provider.kite.set_access_token(access_token)
                provider._load_instruments()
        except Exception as e:
            logger.warning(f"Could not update Zerodha provider with new token: {e}")

        # Attempt to start Zerodha WebSocket service with new token
        websocket_started = False
        try:
            from ..services.zerodha_websocket import get_zerodha_websocket

            zerodha_ws = get_zerodha_websocket()
            zerodha_ws.load_access_token()
            if not zerodha_ws.is_connected:
                websocket_started = zerodha_ws.start()
            else:
                websocket_started = True
        except Exception as e:
            logger.warning(f"Could not auto-start Zerodha WebSocket: {e}")

        return {
            "status": "success",
            "message": "Access token set successfully",
            "note": "Token will expire in 24 hours",
            "websocket_started": websocket_started,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
