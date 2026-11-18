"""Robust HMAC-signed webhook delivery service with exponential backoff and error recovery (Phase 6)."""

import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import httpx
from pydantic import BaseModel, Field

from broll_engine.config import settings
from broll_engine.logging import get_logger

logger = get_logger(__name__)


class WebhookDeliveryResult(BaseModel):
    """Execution report for outbound webhook callback."""
    status: str = Field(..., description="'delivered', 'failed', 'timeout', or 'permanent_error'")
    attempts: int = Field(default=1)
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    delivered_at: Optional[str] = None
    callback_url: str
    signature: str


def compute_signature(payload_bytes: bytes, secret: str) -> str:
    """Computes HMAC-SHA256 hex digest for outbound webhooks."""
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def verify_signature(payload_bytes: bytes, signature_header: str, secret: str) -> bool:
    """Verifies HMAC-SHA256 signature header (e.g. 'sha256=<hex>')."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    received_hash = signature_header.split("sha256=")[-1].strip()
    expected_hash = compute_signature(payload_bytes, secret)
    return hmac.compare_digest(received_hash, expected_hash)


async def dispatch_webhook(
    callback_url: str,
    payload: Dict[str, Any],
    secret: Optional[str] = None,
    max_retries: int = 3,
    initial_backoff: float = 0.5,
    timeout: float = 8.0,
) -> WebhookDeliveryResult:
    """Delivers HMAC-SHA256 signed webhook notification with exponential backoff retries.

    GUARANTEE: Webhook failures (timeouts, network errors, 5xx server issues) will log warnings
    and return a failed WebhookDeliveryResult, but will NEVER raise an unhandled exception that
    compromises or fails the completed video job.
    """
    secret_key = secret or settings.webhook_secret
    payload_bytes = json.dumps(payload, default=str).encode("utf-8")
    hex_sig = compute_signature(payload_bytes, secret_key)
    sig_header = f"sha256={hex_sig}"

    headers = {
        "Content-Type": "application/json",
        "X-IncuBrix-Signature": sig_header,
        "User-Agent": "IncuBrix-BrollEngine/0.1.0",
        "X-IncuBrix-Event": "job.completed",
    }

    last_error: Optional[str] = None
    last_status_code: Optional[int] = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info("Dispatching webhook to '%s' (attempt %d/%d)", callback_url, attempt, max_retries)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(callback_url, content=payload_bytes, headers=headers)
                last_status_code = response.status_code

            if response.is_success:
                logger.info("Webhook delivered successfully to '%s' (HTTP %d)", callback_url, response.status_code)
                return WebhookDeliveryResult(
                    status="delivered",
                    attempts=attempt,
                    status_code=response.status_code,
                    delivered_at=datetime.now(timezone.utc).isoformat(),
                    callback_url=callback_url,
                    signature=sig_header,
                )

            # Client error 4xx (e.g. 404, 401, 400) is non-retryable permanent failure
            if 400 <= response.status_code < 500:
                logger.warning(
                    "Webhook endpoint '%s' rejected request with client error HTTP %d (non-retryable)",
                    callback_url,
                    response.status_code,
                )
                return WebhookDeliveryResult(
                    status="permanent_error",
                    attempts=attempt,
                    status_code=response.status_code,
                    error_message=f"HTTP {response.status_code}: {response.text[:100]}",
                    callback_url=callback_url,
                    signature=sig_header,
                )

            # Server error 5xx is retryable
            last_error = f"HTTP {response.status_code}: {response.text[:100]}"
            logger.warning("Webhook returned HTTP %d on attempt %d: %s", response.status_code, attempt, last_error)

        except httpx.TimeoutException as e:
            last_error = f"Timeout exceeded ({timeout}s)"
            logger.warning("Webhook timeout on attempt %d to '%s': %s", attempt, callback_url, e)
        except Exception as e:
            last_error = str(e)
            logger.warning("Webhook network failure on attempt %d to '%s': %s", attempt, callback_url, e)

        if attempt < max_retries:
            backoff = initial_backoff * (2 ** (attempt - 1))
            await asyncio.sleep(backoff)

    logger.error("Webhook delivery permanently failed after %d attempts to '%s': %s", max_retries, callback_url, last_error)
    return WebhookDeliveryResult(
        status="failed",
        attempts=max_retries,
        status_code=last_status_code,
        error_message=last_error,
        callback_url=callback_url,
        signature=sig_header,
    )
