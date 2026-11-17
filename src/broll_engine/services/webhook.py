import hashlib
import hmac
import json
from typing import Any, Dict, Optional
import httpx

from broll_engine.config import settings
from broll_engine.logging import get_logger

logger = get_logger(__name__)


def compute_signature(payload_bytes: bytes, secret: str) -> str:
    """Computes HMAC-SHA256 hex digest for outbound webhooks."""
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


async def dispatch_webhook(callback_url: str, payload: Dict[str, Any], secret: Optional[str] = None) -> bool:
    """Delivers HMAC-SHA256 signed webhook notification upon job completion."""
    secret = secret or settings.webhook_secret
    payload_bytes = json.dumps(payload, default=str).encode("utf-8")
    signature = compute_signature(payload_bytes, secret)

    headers = {
        "Content-Type": "application/json",
        "X-IncuBrix-Signature": f"sha256={signature}",
        "User-Agent": "IncuBrix-Broll-Engine/1.0",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(callback_url, content=payload_bytes, headers=headers)
            if response.is_success:
                logger.info(f"Webhook successfully delivered to {callback_url} (HTTP {response.status_code})")
                return True
            else:
                logger.warning(f"Webhook delivery to {callback_url} returned HTTP {response.status_code}")
                return False
    except Exception as e:
        logger.error(f"Failed to deliver webhook to {callback_url}: {e}")
        return False
