import time
from typing import Dict, Any
from fastapi import APIRouter, Request, status
from backend.config import settings
from backend.redis_client.client import get_redis_status, get_redis
from backend.middleware.rate_limiter import get_client_identifier

router = APIRouter()


@router.get("/health", tags=["Monitoring"])
async def health_check() -> Dict[str, Any]:
    """Gateway health check and datastore status."""
    redis_info = await get_redis_status()
    is_healthy = redis_info.get("connected", False)

    return {
        "status": "healthy" if is_healthy else "degraded",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "timestamp": int(time.time()),
        "redis": redis_info,
    }


@router.get("/api/v1/ping", tags=["Gateway"])
async def ping() -> Dict[str, str]:
    """Lightweight test endpoint."""
    return {"message": "pong"}


@router.get("/api/v1/data", tags=["Gateway"])
async def get_mock_data(request: Request) -> Dict[str, Any]:
    """
    Simulated protected API endpoint serving mock business payload.
    Rate limited by the gateway middleware.
    """
    client_id = get_client_identifier(request)
    return {
        "message": "Access granted to protected upstream payload.",
        "client": client_id,
        "timestamp": time.time(),
        "items": [
            {"id": 1, "name": "Secure Resource Alpha", "status": "active"},
            {"id": 2, "name": "Secure Resource Beta", "status": "active"},
        ],
    }


@router.get("/api/v1/quota", tags=["Gateway"])
async def get_quota_status(request: Request) -> Dict[str, Any]:
    """
    Inspect the calling client's current rate limit usage without consuming quota.
    """
    client_id = get_client_identifier(request)
    now_ms = int(time.time() * 1000)
    window_ms = settings.RATE_LIMIT_WINDOW_SECONDS * 1000
    clear_before = now_ms - window_ms
    key = f"rate_limit:{client_id}"

    try:
        redis_conn = get_redis()
        # Count items with score between clear_before and inf
        active_count = await redis_conn.zcount(key, clear_before, "+inf")
        remaining = max(0, settings.RATE_LIMIT_MAX_REQUESTS - active_count)
        ttl = await redis_conn.ttl(key)
    except Exception:
        active_count = 0
        remaining = settings.RATE_LIMIT_MAX_REQUESTS
        ttl = -1

    return {
        "client": client_id,
        "limit": settings.RATE_LIMIT_MAX_REQUESTS,
        "window_seconds": settings.RATE_LIMIT_WINDOW_SECONDS,
        "current_requests": active_count,
        "remaining_quota": remaining,
        "ttl_seconds": max(0, ttl),
    }


@router.api_route("/api/v1/echo/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], tags=["Gateway"])
async def echo_proxy(request: Request, path: str) -> Dict[str, Any]:
    """
    Generic echo endpoint simulating upstream microservice proxying.
    """
    client_id = get_client_identifier(request)
    return {
        "proxy_path": path,
        "method": request.method,
        "client": client_id,
        "headers": {k: v for k, v in request.headers.items() if not k.lower().startswith("sec-")},
        "query_params": dict(request.query_params),
    }
