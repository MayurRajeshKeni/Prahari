import logging
from typing import Optional, Tuple, Any
import redis.asyncio as aioredis

from backend.config import settings

logger = logging.getLogger("prahari.redis")

_redis_pool: Optional[aioredis.ConnectionPool] = None
_redis_client: Optional[aioredis.Redis] = None
_rate_limit_script: Optional[Any] = None


def load_lua_script() -> str:
    """Read the Sliding Window Lua script from disk."""
    if not settings.LUA_SCRIPT_PATH.exists():
        raise FileNotFoundError(f"Lua rate limit script not found at {settings.LUA_SCRIPT_PATH}")
    return settings.LUA_SCRIPT_PATH.read_text(encoding="utf-8")


async def init_redis(client: Optional[aioredis.Redis] = None) -> aioredis.Redis:
    """
    Initialize async Redis connection pool and register the Sliding Window Lua script.
    Allows passing an existing client for testing/mocking.
    """
    global _redis_pool, _redis_client, _rate_limit_script

    if client is not None:
        _redis_client = client
    else:
        logger.info(f"Connecting to Redis at {settings.REDIS_URL}...")
        _redis_pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
            socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT,
            decode_responses=True,
        )
        _redis_client = aioredis.Redis(connection_pool=_redis_pool)

    # Register rate_limit.lua script for atomic execution via EVALSHA
    lua_code = load_lua_script()
    _rate_limit_script = _redis_client.register_script(lua_code)
    logger.info("Registered rate_limit.lua script SHA with Redis.")

    return _redis_client


async def close_redis() -> None:
    """Close active Redis client and connection pool cleanly on shutdown."""
    global _redis_pool, _redis_client, _rate_limit_script

    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None

    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None

    _rate_limit_script = None
    logger.info("Redis connection pool closed.")


def get_redis() -> aioredis.Redis:
    """Retrieve the current active Redis client instance."""
    if _redis_client is None:
        raise RuntimeError("Redis client is not initialized. Call init_redis() during application startup.")
    return _redis_client


async def check_rate_limit(
    identifier: str,
    now_ms: int,
    window_ms: int,
    limit: int,
    member_id: str,
) -> Tuple[bool, int, int]:
    """
    Execute atomic sliding window rate limit evaluation in Redis.

    Parameters:
        identifier: Unique client key identifier (e.g. IP or token).
        now_ms: Current timestamp in milliseconds.
        window_ms: Rolling window size in milliseconds.
        limit: Max requests allowed within the window.
        member_id: Unique member ID for this request entry.

    Returns:
        Tuple of (allowed: bool, remaining_quota: int, retry_after_seconds: int)
    """
    if _rate_limit_script is None or _redis_client is None:
        raise RuntimeError("Redis rate limiter script is not initialized.")

    key = f"rate_limit:{identifier}"
    result = await _rate_limit_script(
        keys=[key],
        args=[now_ms, window_ms, limit, member_id],
    )

    # Lua script returns table { allowed (1 or 0), remaining_quota, retry_after_seconds }
    allowed_int, remaining, retry_after = result[0], result[1], result[2]
    return (allowed_int == 1, int(remaining), int(retry_after))


async def get_redis_status() -> dict:
    """Check connectivity and ping latency to Redis."""
    if _redis_client is None:
        return {"connected": False, "error": "Redis client not initialized"}
    try:
        pong = await _redis_client.ping()
        return {"connected": pong is True, "status": "pong" if pong else "unknown"}
    except Exception as exc:
        logger.error(f"Redis ping failed: {exc}")
        return {"connected": False, "error": str(exc)}
