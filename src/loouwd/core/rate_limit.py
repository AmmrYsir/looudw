import time
import asyncio
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from loouwd.core.config import settings
from loouwd.core.logging import logger


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 120):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.window_seconds = 60
        # Storage: ip -> list of request timestamps
        self._requests: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next) -> Response:
        # If rate limiting is disabled (requests_per_minute <= 0), pass through immediately
        limit = settings.RATE_LIMIT_PER_MINUTE if hasattr(settings, "RATE_LIMIT_PER_MINUTE") else self.requests_per_minute
        if limit <= 0:
            return await call_next(request)

        # Exclude OpenAPI docs and health endpoints from rate limits
        if request.url.path in ["/", "/docs", "/openapi.json", "/redoc", "/api/v1/sources"]:
            return await call_next(request)

        client_ip = request.client.host if request.client else "127.0.0.1"
        now = time.time()
        window_start = now - self.window_seconds

        async with self._lock:
            timestamps = self._requests.get(client_ip, [])
            # Filter out timestamps outside the sliding 60-second window
            valid_timestamps = [t for t in timestamps if t > window_start]

            if len(valid_timestamps) >= limit:
                logger.warning(f"Rate limit exceeded for IP: {client_ip} on path: {request.url.path}")
                retry_after = int(valid_timestamps[0] + self.window_seconds - now) + 1
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "rate_limit_exceeded",
                        "message": f"Too many requests. Limit is {limit} requests per minute.",
                        "retry_after_seconds": retry_after,
                    },
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                    },
                )

            valid_timestamps.append(now)
            self._requests[client_ip] = valid_timestamps
            remaining = limit - len(valid_timestamps)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
