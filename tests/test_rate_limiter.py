import time
from typing import Dict, List, Tuple
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.config import settings
from backend.middleware.rate_limiter import (
    RateLimitMiddleware,
    get_client_identifier,
    EXEMPT_PATHS,
)
from backend.routes.api import router as api_router
from backend.redis_client.client import load_lua_script


class MockRedisRateLimiter:
    """
    In-memory mock replicating the exact Redis ZSET Sliding Window logic
    from scripts/rate_limit.lua for isolated unit & CI testing.
    """

    def __init__(self):
        # Store as dict: key -> list of (timestamp_ms, member_id)
        self.store: Dict[str, List[Tuple[int, str]]] = {}

    async def execute_lua(
        self,
        identifier: str,
        now_ms: int,
        window_ms: int,
        limit: int,
        member_id: str,
    ) -> Tuple[bool, int, int]:
        key = f"rate_limit:{identifier}"
        entries = self.store.get(key, [])
        clear_before = now_ms - window_ms

        # 1. Prune expired timestamps
        active = [item for item in entries if item[0] > clear_before]

        # 2. Check quota
        if len(active) < limit:
            active.append((now_ms, member_id))
            self.store[key] = active
            remaining = limit - len(active)
            return (True, remaining, 0)
        else:
            self.store[key] = active
            oldest_ts = active[0][0]
            reset_time = oldest_ts + window_ms
            retry_after = max(1, int((reset_time - now_ms + 999) // 1000))
            return (False, 0, retry_after)


@pytest.fixture
def mock_limiter(monkeypatch):
    limiter = MockRedisRateLimiter()

    async def mock_check(identifier, now_ms, window_ms, limit, member_id):
        return await limiter.execute_lua(identifier, now_ms, window_ms, limit, member_id)

    monkeypatch.setattr("backend.middleware.rate_limiter.check_rate_limit", mock_check)
    return limiter


@pytest.fixture
def test_app():
    app = FastAPI()
    # Configure tight limit for fast testing: 3 requests per 10 seconds
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=3,
        window_seconds=10,
    )
    app.include_router(api_router)
    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


# -------------------------------------------------------------------------
# Test Cases
# -------------------------------------------------------------------------


def test_lua_script_syntax_and_primitives():
    """Verify scripts/rate_limit.lua exists and contains required Redis ZSET calls."""
    content = load_lua_script()
    assert content, "Lua script should not be empty"
    assert "ZREMRANGEBYSCORE" in content
    assert "ZCARD" in content
    assert "ZADD" in content
    assert "PEXPIRE" in content
    assert "ZRANGE" in content


def test_client_identifier_resolution():
    """Verify IP and API Key extraction precedence."""
    # 1. Direct host
    req1 = Request({"type": "http", "client": ("192.168.1.100", 12345), "headers": []})
    assert get_client_identifier(req1) == "ip:192.168.1.100"

    # 2. X-Forwarded-For header takes precedence over client.host
    req2 = Request({
        "type": "http",
        "client": ("127.0.0.1", 12345),
        "headers": [(b"x-forwarded-for", b"203.0.113.195, 70.41.3.18")],
    })
    assert get_client_identifier(req2) == "ip:203.0.113.195"

    # 3. X-API-Key takes highest precedence
    req3 = Request({
        "type": "http",
        "client": ("127.0.0.1", 12345),
        "headers": [
            (b"x-forwarded-for", b"203.0.113.195"),
            (b"x-api-key", b"secret-prahari-token-xyz"),
        ],
    })
    assert get_client_identifier(req3) == "key:secret-prahari-token-xyz"


def test_exempt_endpoints_bypass_rate_limiting(client, mock_limiter):
    """Exempt endpoints like /health must not be blocked even with zero quota."""
    # Health check is exempt
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert data["service"] == settings.PROJECT_NAME


def test_sliding_window_allows_requests_within_quota(client, mock_limiter):
    """Requests within max_requests (3) should succeed with status 200 and headers."""
    headers = {"X-Forwarded-For": "10.0.0.1"}

    # Request 1
    resp1 = client.get("/api/v1/ping", headers=headers)
    assert resp1.status_code == 200
    assert resp1.headers["X-RateLimit-Limit"] == "3"
    assert resp1.headers["X-RateLimit-Remaining"] == "2"

    # Request 2
    resp2 = client.get("/api/v1/ping", headers=headers)
    assert resp2.status_code == 200
    assert resp2.headers["X-RateLimit-Remaining"] == "1"

    # Request 3 (Final allowed request in window)
    resp3 = client.get("/api/v1/ping", headers=headers)
    assert resp3.status_code == 200
    assert resp3.headers["X-RateLimit-Remaining"] == "0"


def test_sliding_window_rejects_exceeded_quota_with_429(client, mock_limiter):
    """Fourth request from same client must return 429 and structured JSON error."""
    headers = {"X-Forwarded-For": "10.0.0.2"}

    # Use up 3 requests
    for _ in range(3):
        res = client.get("/api/v1/data", headers=headers)
        assert res.status_code == 200

    # 4th request must be rejected
    rejected = client.get("/api/v1/data", headers=headers)
    assert rejected.status_code == 429
    assert rejected.headers["Retry-After"] == "10"
    assert rejected.headers["X-RateLimit-Remaining"] == "0"

    # Verify structured JSON matching Rules.md specification:
    body = rejected.json()
    assert body["error"] == "Rate limit exceeded"
    assert "retry_after" in body
    assert body["retry_after"] > 0


def test_isolated_quotas_for_different_clients(client, mock_limiter):
    """Different client IPs should have separate rate limit buckets."""
    client_a = {"X-Forwarded-For": "192.168.10.1"}
    client_b = {"X-Forwarded-For": "192.168.10.2"}

    # Exhaust Client A's quota
    for _ in range(3):
        assert client.get("/api/v1/ping", headers=client_a).status_code == 200

    # Client A is blocked
    assert client.get("/api/v1/ping", headers=client_a).status_code == 429

    # Client B should still be allowed!
    resp_b = client.get("/api/v1/ping", headers=client_b)
    assert resp_b.status_code == 200
    assert resp_b.headers["X-RateLimit-Remaining"] == "2"


def test_sliding_window_recovers_after_time_elapsed(client, mock_limiter, monkeypatch):
    """Once the window slides past the earliest requests, new requests should succeed."""
    headers = {"X-Forwarded-For": "172.16.0.5"}

    # Exhaust quota at t = 1000.0
    current_time = 1000.0
    monkeypatch.setattr(time, "time", lambda: current_time)

    for _ in range(3):
        assert client.get("/api/v1/ping", headers=headers).status_code == 200

    # 4th is blocked at current_time
    assert client.get("/api/v1/ping", headers=headers).status_code == 429

    # Advance time by 11 seconds (exceeding window of 10s)
    current_time += 11.0
    monkeypatch.setattr(time, "time", lambda: current_time)

    # Now request should be allowed again!
    resp_recovered = client.get("/api/v1/ping", headers=headers)
    assert resp_recovered.status_code == 200
    assert resp_recovered.headers["X-RateLimit-Remaining"] == "2"


def test_api_echo_and_mock_data_routes(client, mock_limiter):
    """Verify business endpoints return expected mock payloads."""
    headers = {"X-Forwarded-For": "10.0.0.99"}

    # Mock data endpoint
    data_resp = client.get("/api/v1/data", headers=headers)
    assert data_resp.status_code == 200
    assert "items" in data_resp.json()

    # Echo proxy endpoint
    echo_resp = client.post("/api/v1/echo/v2/orders", json={"item": "shield"}, headers=headers)
    assert echo_resp.status_code == 200
    payload = echo_resp.json()
    assert payload["proxy_path"] == "v2/orders"
    assert payload["method"] == "POST"


def test_rate_limit_fail_open_on_redis_error(client, monkeypatch):
    """When Redis is down or times out, gateway fails open with degraded header."""
    async def mock_failing_check(*args, **kwargs):
        raise ConnectionError("Redis connection refused")

    monkeypatch.setattr("backend.middleware.rate_limiter.check_rate_limit", mock_failing_check)

    resp = client.get("/api/v1/ping")
    assert resp.status_code == 200
    assert resp.headers.get("X-RateLimit-Error") == "Service Degraded"


@pytest.mark.asyncio
async def test_rate_limit_dependency_direct(mock_limiter):
    """Verify rate_limit_dependency function directly."""
    from backend.middleware.rate_limiter import rate_limit_dependency
    from fastapi import HTTPException

    req = Request({
        "type": "http",
        "client": ("192.168.1.55", 8080),
        "headers": [],
    })

    # Within limit of 2
    r1 = await rate_limit_dependency(req, max_requests=2, window_seconds=5)
    assert r1["remaining"] == 1

    r2 = await rate_limit_dependency(req, max_requests=2, window_seconds=5)
    assert r2["remaining"] == 0

    # Exceeding limit raises HTTPException(429)
    with pytest.raises(HTTPException) as exc_info:
        await rate_limit_dependency(req, max_requests=2, window_seconds=5)
    assert exc_info.value.status_code == 429

