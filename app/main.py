# Load environment variables with override to ensure .env file takes precedence over system env vars
from dotenv import load_dotenv
import os
import asyncio
import logging
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../.env'), override=True)

from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
from .routers import market, agents, strategy, memory, news, chat, chart, zerodha_auth, zerodha_data, notifications, cache, websocket, performance, analytics, scalping, watchlist, auth, redis_monitor
from .routers import trading
from .routers import support
from .routers import user_preferences, user_watchlist
from .services.cache_redis import clear_memory_cache
from .services.token_monitor import start_token_monitoring, stop_token_monitoring
from .services.index_universe_monitor import start_index_universe_monitoring, stop_index_universe_monitoring
from .services.top_picks_scheduler import start_top_picks_scheduler, stop_top_picks_scheduler, warm_top_picks
from .services.scalping_monitor_scheduler import start_scalping_monitor, stop_scalping_monitor
from .services.dashboard_scheduler import start_dashboard_scheduler, stop_dashboard_scheduler
from .services.portfolio_monitor_scheduler import start_portfolio_monitor, stop_portfolio_monitor
from .services.top_picks_positions_monitor_scheduler import (
    start_top_picks_positions_monitor,
    stop_top_picks_positions_monitor,
)
from .services.rl_scheduler import start_rl_scheduler, stop_rl_scheduler
from .core.branding import (
    APP_NAME,
    APP_OWNER,
    DEFAULT_LICENSEE,
    APP_ID,
    ENV_NAME,
    ENV_FINGERPRINT,
    short_signature,
    get_branding_meta,
)
from .security import get_token_payload

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logging.getLogger(__name__).info(
        "Starting %s (%s) • Env=%s • Licensee=%s • AppId=%s • Signature=%s • EnvFp=%s",
        APP_NAME,
        APP_OWNER,
        ENV_NAME,
        DEFAULT_LICENSEE,
        APP_ID,
        short_signature(),
        ENV_FINGERPRINT,
    )
    # TEMPORARILY DISABLED - Schedulers commented out for deployment testing
    await start_token_monitoring()
    await start_index_universe_monitoring()
    await start_top_picks_scheduler()
    try:
        asyncio.create_task(warm_top_picks())
    except Exception as e:
        logging.getLogger(__name__).warning("Failed to warm Top Picks on startup: %s", e)
    await start_scalping_monitor()  # Start scalping auto-monitor (every 5 mins)
    await start_dashboard_scheduler()  # Start dashboard/overview worker
    await start_portfolio_monitor()  # Start portfolio monitor worker
    await start_top_picks_positions_monitor()  # Start Top Picks positions monitor
    await start_rl_scheduler()  # Start nightly RL scheduler (16:30 IST, Mon-Fri)
    
    # Start WebSocket service if Zerodha is authenticated
    try:
        from .services.zerodha_websocket import get_zerodha_websocket
        zerodha_ws = get_zerodha_websocket()
        if zerodha_ws.load_access_token():
            logger = logging.getLogger(__name__)
            logger.info("Starting Zerodha WebSocket service...")
            zerodha_ws.start()
    except Exception as e:
        logging.getLogger(__name__).warning(f"Could not start WebSocket: {e}")
    
    yield
    
    # Shutdown - TEMPORARILY DISABLED (matching disabled startup)
    stop_token_monitoring()
    stop_index_universe_monitoring()
    stop_top_picks_scheduler()
    stop_scalping_monitor()  # Stop scalping monitor
    stop_dashboard_scheduler()  # Stop dashboard worker
    stop_portfolio_monitor()  # Stop portfolio monitor worker
    stop_top_picks_positions_monitor()  # Stop Top Picks positions monitor
    stop_rl_scheduler()  # Stop nightly RL scheduler
    
    # Stop WebSocket service
    try:
        from .services.zerodha_websocket import get_zerodha_websocket
        zerodha_ws = get_zerodha_websocket()
        zerodha_ws.stop()
    except:
        pass

app = FastAPI(
    title=f"{APP_NAME} API",
    version="0.1.0",
    lifespan=lifespan,
    security=[{"BearerAuth": []}],
    components={
        "securitySchemes": {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "JWT Authorization header using the Bearer scheme. Example: 'Authorization: Bearer {token}'"
            }
        }
    }
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def fyntrix_branding_headers(request: Request, call_next):
    """Inject subtle FYNTRIX branding headers into all HTTP responses.

    This acts as a watermark without changing functional behaviour.
    """
    response = await call_next(request)
    try:
        response.headers.setdefault("X-Fyntrix-App", APP_NAME)
        response.headers.setdefault("X-Fyntrix-App-Id", APP_ID)
        response.headers.setdefault("X-Fyntrix-Licensee", DEFAULT_LICENSEE)
        response.headers.setdefault("X-Fyntrix-Signature", short_signature())
        response.headers.setdefault("X-Fyntrix-Env", ENV_NAME)
        response.headers.setdefault("X-Fyntrix-Env-Fp", ENV_FINGERPRINT)
    except Exception:
        # Never break responses because of branding headers
        pass
    return response

@app.get("/health")
def health():
    return {"ok": True}


@app.get("/meta/branding")
def branding_meta():
    """Lightweight endpoint exposing non-sensitive branding metadata.

    Useful for tracing running instances back to the FYNTRIX codebase.
    """
    return get_branding_meta()

@app.post("/admin/clear-cache")
def clear_cache():
    """Clear in-memory cache for testing"""
    clear_memory_cache()
    return {"ok": True, "message": "Cache cleared"}

app.include_router(auth.router, prefix="/v1")
app.include_router(market.router, prefix="/v1")
app.include_router(agents.router, prefix="/v1")
app.include_router(strategy.router, prefix="/v1")
app.include_router(memory.router, prefix="/v1")
app.include_router(news.router, prefix="/v1")
app.include_router(chat.router, prefix="/v1")
app.include_router(chart.router, prefix="/v1")
app.include_router(support.router, prefix="/v1")
app.include_router(trading.router, prefix="/v1")
app.include_router(zerodha_auth.router, prefix="/v1")
app.include_router(zerodha_data.router, prefix="/v1")
app.include_router(notifications.router, prefix="/v1")
app.include_router(cache.router, prefix="/v1")
app.include_router(websocket.router, prefix="/v1")
app.include_router(performance.router)
app.include_router(analytics.router)
app.include_router(scalping.router)
app.include_router(watchlist.router, prefix="/v1")
app.include_router(user_preferences.router, prefix="/v1")
app.include_router(user_watchlist.router, prefix="/v1")
app.include_router(redis_monitor.router)
