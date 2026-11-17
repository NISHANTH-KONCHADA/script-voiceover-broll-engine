import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

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
