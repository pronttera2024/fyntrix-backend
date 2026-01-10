import os
import json
import logging
from typing import Any, Optional
import uuid

logger = logging.getLogger(__name__)

_redis_client = None
LOCK_DISABLED_SENTINEL = "__redis_lock_disabled__"


def get_redis_client():
    """Lazily create and return a Redis client.

    Returns None if the redis library is not installed or connection fails.
    """
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    try:
        import redis  # type: ignore
    except ImportError:
        logger.info("Redis library not installed; Redis caching is disabled.")
        _redis_client = None
        return None

    url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    try:
        client = redis.Redis.from_url(url)
        # Lightweight health check
        client.ping()
        _redis_client = client
        logger.info("Connected to Redis at %s", url)
    except Exception as e:
        logger.warning("Could not connect to Redis at %s: %s", url, e)
        _redis_client = None

    return _redis_client


def set_json(key: str, value: Any, ex: Optional[int] = None) -> None:
    """Store a JSON-serialised value under key if Redis is available."""
    client = get_redis_client()
    if not client:
        return
    try:
        payload = json.dumps(value)
        client.set(key, payload, ex=ex)
    except Exception as e:
        logger.warning("Redis set_json failed for %s: %s", key, e)


def get_json(key: str) -> Optional[Any]:
    """Fetch and decode JSON value from Redis, or None if missing/unavailable."""
    client = get_redis_client()
    if not client:
        return None
    try:
        raw = client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning("Redis get_json failed for %s: %s", key, e)
        return None


def acquire_lock(key: str, ttl: int = 60) -> Optional[str]:
    """Attempt to acquire a simple distributed lock.

    Returns a lock token string if acquired, LOCK_DISABLED_SENTINEL if Redis
    is unavailable, or None if the lock is already held by someone else.
    """
    client = get_redis_client()
    if not client:
        return LOCK_DISABLED_SENTINEL

    token = str(uuid.uuid4())
    try:
        acquired = client.set(key, token, nx=True, ex=ttl)
        if acquired:
            return token
    except Exception as e:
        logger.warning("Redis acquire_lock failed for %s: %s", key, e)
    return None


def release_lock(key: str, token: str) -> None:
    """Release a lock if we still own it."""
    if token == LOCK_DISABLED_SENTINEL:
        return

    client = get_redis_client()
    if not client:
        return

    try:
        raw = client.get(key)
        if raw is None:
            return
        current = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
        if current == token:
            client.delete(key)
    except Exception as e:
        logger.warning("Redis release_lock failed for %s: %s", key, e)
