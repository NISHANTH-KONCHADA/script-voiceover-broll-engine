import time
import uuid
from collections import defaultdict, deque
from typing import Callable, Deque, Dict
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from broll_engine.config import settings
from broll_engine.logging import correlation_id_ctx, get_logger

logger = get_logger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Assigns or extracts X-Correlation-Id header and sets it in context."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        corr_id = request.headers.get("X-Correlation-Id") or f"req_{uuid.uuid4().hex[:12]}"
        correlation_id_ctx.set(corr_id)

        start_time = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        response.headers["X-Correlation-Id"] = corr_id
        response.headers["X-Response-Time-Ms"] = str(duration_ms)

        # Log request summary
        logger.info(
            f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)",
            extra={"status_code": response.status_code, "duration_ms": duration_ms},
        )

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory sliding-window rate limiter for the expensive job-creation endpoint.

    Limits POST /api/v1/broll/jobs to settings.api_rate_limit_per_minute requests
    per client IP per 60-second window. Disabled when the configured limit is <= 0.
    """

    _WINDOW_SECONDS = 60.0

    def __init__(self, app, max_per_minute: int = 0, protected_path: str = "/api/v1/broll/jobs"):
        super().__init__(app)
        self.max_per_minute = max_per_minute
        self.protected_path = protected_path
        self._requests: Dict[str, Deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if self.max_per_minute <= 0 or not (
            request.method == "POST" and request.url.path == self.protected_path
        ):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window = self._requests[client_ip]
        while window and now - window[0] > self._WINDOW_SECONDS:
            window.popleft()

        if len(window) >= self.max_per_minute:
            retry_after = max(1, int(self._WINDOW_SECONDS - (now - window[0]))) if window else 60
            logger.warning(f"Rate limit exceeded for client {client_ip} on {self.protected_path}")
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Too many job submissions. Please retry later.",
                        "retryable": True,
                        "details": {"limit_per_minute": self.max_per_minute},
                    }
                },
                headers={"Retry-After": str(retry_after)},
            )

        window.append(now)
        return await call_next(request)
