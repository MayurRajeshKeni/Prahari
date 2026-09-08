import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.redis_client.client import init_redis, close_redis
from backend.middleware.rate_limiter import RateLimitMiddleware
from backend.routes.api import router as api_router

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("prahari.gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager: sets up and tears down Redis pool."""
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}...")
    try:
        await init_redis()
        logger.info("Redis client and rate limiter Lua script successfully initialized.")
    except Exception as exc:
        logger.warning(
            f"Redis initialization encountered an issue: {exc}. "
            "Gateway will run in degraded mode until Redis connection is re-established."
        )

    yield

    logger.info("Shutting down gateway...")
    try:
        await close_redis()
    except Exception as exc:
        logger.error(f"Error during Redis shutdown: {exc}")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Distributed API Gateway with Atomic Sliding Window Rate Limiting and ML Traffic Protection.",
    lifespan=lifespan,
)

# Enable CORS for local React dashboard and external API clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Attach atomic rate limiting middleware
app.add_middleware(
    RateLimitMiddleware,
    max_requests=settings.RATE_LIMIT_MAX_REQUESTS,
    window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
)

# Register routes
app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=settings.GATEWAY_HOST,
        port=settings.GATEWAY_PORT,
        reload=settings.DEBUG,
    )
