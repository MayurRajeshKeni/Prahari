import time
import uuid
import logging
from typing import Callable, Optional, Set
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config import settings
from backend.redis_client.client import check_rate_limit

logger = logging.getLogger("prahari.ratelimit")

# Paths that bypass rate limiting (health checks, schema, docs)
EXEMPT_PATHS: Set[str] = {
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
}


def get_client_identifier(request: Request) -> str:
    """
    Extract a unique client identifier from the request.
    Prioritizes API Key header, followed by X-Forwarded-For, then direct client IP.
    """
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"key:{api_key.strip()}"

    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP if multiple are chained in X-Forwarded-For
        client_ip = forwarded_for.split(",")[0].strip()
        if client_ip:
            return f"ip:{client_ip}"

    if request.client and request.client.host:
        return f"ip:{request.client.host}"

    return "ip:127.0.0.1"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI Middleware to enforce atomic distributed rate limiting on incoming traffic.
    Uses sliding window algorithm via Redis Lua script.
    """

    def __init__(
        self,
        app,
        max_requests: Optional[int] = None,
        window_seconds: Optional[int] = None,
        exempt_paths: Optional[Set[str]] = None,
    ):
        super().__init__(app)
        self.max_requests = max_requests or settings.RATE_LIMIT_MAX_REQUESTS
        self.window_seconds = window_seconds or settings.RATE_LIMIT_WINDOW_SECONDS
        self.window_ms = self.window_seconds * 1000
        self.exempt_paths = exempt_paths if exempt_paths is not None else EXEMPT_PATHS

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for exempt system endpoints
        if request.url.path in self.exempt_paths:
            return await call_next(request)

        identifier = get_client_identifier(request)
        now_ms = int(time.time() * 1000)
        member_id = f"{now_ms}:{uuid.uuid4().hex[:8]}"

        try:
            allowed, remaining, retry_after = await check_rate_limit(
                identifier=identifier,
                now_ms=now_ms,
                window_ms=self.window_ms,
                limit=self.max_requests,
                member_id=member_id,
            )
        except Exception as exc:
            logger.error(f"Rate limiting evaluation failed: {exc}", exc_info=True)
            # Fail-open with warning if Redis is temporarily unreachable
            response = await call_next(request)
            response.headers["X-RateLimit-Error"] = "Service Degraded"
            return response

        if not allowed:
            logger.warning(
                f"Rate limit exceeded for {identifier} on {request.method} {request.url.path}. "
                f"Retry after: {retry_after}s"
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(retry_after),
                },
            )

        # Quota available: continue pipeline
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


async def rate_limit_dependency(
    request: Request,
    max_requests: Optional[int] = None,
    window_seconds: Optional[int] = None,
) -> dict:
    """
    FastAPI dependency version for granular per-route rate limiting.
    """
    limit = max_requests or settings.RATE_LIMIT_MAX_REQUESTS
    window_sec = window_seconds or settings.RATE_LIMIT_WINDOW_SECONDS
    window_ms = window_sec * 1000

    identifier = get_client_identifier(request)
    now_ms = int(time.time() * 1000)
    member_id = f"{now_ms}:{uuid.uuid4().hex[:8]}"

    allowed, remaining, retry_after = await check_rate_limit(
        identifier=identifier,
        now_ms=now_ms,
        window_ms=window_ms,
        limit=limit,
        member_id=member_id,
    )

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Rate limit exceeded",
                "retry_after": retry_after,
            },
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
            },
        )

    return {
        "identifier": identifier,
        "limit": limit,
        "remaining": remaining,
    }
