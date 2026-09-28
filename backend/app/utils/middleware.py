"""Security headers, Request ID, and Rate Limiting middlewares."""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach unique X-Request-ID to incoming requests and outgoing responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security hardening headers to all HTTP responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        # Content Security Policy
        csp = (
            "default-src 'self'; "
            "img-src 'self' data: blob:; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "connect-src 'self' http://localhost:* ws://localhost:*;"
        )
        response.headers["Content-Security-Policy"] = csp

        if not settings.DEBUG:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Sliding-window in-memory rate limiter per IP address."""

    def __init__(self, app, requests_per_minute: int = 180) -> None:
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Don't rate limit health check, readiness, or testclient in test suite
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        if (
            path.startswith("/api/health")
            or path.startswith("/api/readiness")
            or client_ip in ("testclient", "localhost", "127.0.0.1")
        ):
            return await call_next(request)

        now = time.time()
        minute_ago = now - 60.0

        # Clean old timestamps
        history = [ts for ts in self._requests[client_ip] if ts > minute_ago]
        history.append(now)
        self._requests[client_ip] = history

        if len(history) > self.requests_per_minute:
            logger.warning("Rate limit exceeded for IP: %s (path: %s)", client_ip, path)
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded. Please wait before sending more requests.",
                    "error_code": "RATE_LIMIT_EXCEEDED",
                },
                headers={"Retry-After": "60"},
            )

        return await call_next(request)
