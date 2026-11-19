"""SSRF protection and secure media download engine.

Provides strict validation against:
- SSRF (Server-Side Request Forgery) to internal / loopback / link-local / cloud-metadata IPs
- Unsafe / unpermitted URI protocols (e.g. ftp, gopher, file, data, dict)
- Malicious redirect chains attempting to bypass host checks
- Oversized media downloads causing memory or disk exhaustion (DoS)
- Corrupted or non-video media files via FFprobe stream verification
"""

import ipaddress
import json
import os
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Set
from urllib.parse import urljoin, urlparse

import httpx

from broll_engine.api.routes.errors import APIError
from broll_engine.logging import get_logger

logger = get_logger(__name__)

# Maximum allowed size for a single B-roll clip download (100 MB)
MAX_MEDIA_DOWNLOAD_SIZE_BYTES = 100 * 1024 * 1024
DEFAULT_DOWNLOAD_TIMEOUT = 30.0
MAX_REDIRECT_HOPS = 3

DISALLOWED_HOSTNAMES: Set[str] = {
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "host.docker.internal",
    "minio",
    "metadata.google.internal",
    "169.254.169.254",
}


def is_ip_private_or_reserved(ip_str: str) -> bool:
    """Checks whether an IP address is private, loopback, link-local, multicast, or reserved."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        )
    except ValueError:
        return True


def validate_url_security(url: str, allow_private_for_test: bool = False) -> None:
    """Validates URL protocol and hostname against SSRF, internal network probing, and unsupported schemes."""
    if not url or not isinstance(url, str):
        raise APIError(
            code="INVALID_URL",
            message="Media URL must be a non-empty string.",
            status_code=400,
            retryable=False,
        )

    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()

    if scheme not in ("http", "https"):
        raise APIError(
            code="UNSUPPORTED_PROTOCOL",
            message=f"Unsupported protocol scheme '{scheme}'. Only http:// and https:// are permitted.",
            status_code=400,
            retryable=False,
        )

    hostname = parsed.hostname
    if not hostname:
        raise APIError(
            code="INVALID_URL_HOST",
            message="Media URL must include a valid host name.",
            status_code=400,
            retryable=False,
        )

    clean_host = hostname.lower().strip("[]")

    if not allow_private_for_test:
        if (
            clean_host in DISALLOWED_HOSTNAMES
            or clean_host.endswith(".internal")
            or clean_host.endswith(".local")
            or clean_host.endswith(".localhost")
        ):
            raise APIError(
                code="SSRF_FORBIDDEN",
                message=f"Access to internal or private host '{hostname}' is forbidden.",
                status_code=400,
                retryable=False,
            )

        # Check if the hostname itself is a raw IP literal
        try:
            raw_ip = ipaddress.ip_address(clean_host)
            if (
                raw_ip.is_private
                or raw_ip.is_loopback
                or raw_ip.is_link_local
                or raw_ip.is_reserved
                or raw_ip.is_multicast
                or raw_ip.is_unspecified
            ):
                raise APIError(
                    code="SSRF_FORBIDDEN",
                    message=f"Access to private IP address '{clean_host}' is forbidden.",
                    status_code=400,
                    retryable=False,
                )
        except ValueError:
            # Not an IP literal, proceed to DNS resolution
            pass

        # DNS resolution check for SSRF / private IP ranges
        try:
            addr_info = socket.getaddrinfo(clean_host, None)
            for family, _, _, _, sockaddr in addr_info:
                ip_addr = sockaddr[0]
                if is_ip_private_or_reserved(ip_addr):
                    raise APIError(
                        code="SSRF_FORBIDDEN",
                        message=f"Access to private IP address '{ip_addr}' resolved from '{hostname}' is forbidden.",
                        status_code=400,
                        retryable=False,
                    )
        except socket.gaierror as e:
            raise APIError(
                code="DNS_RESOLUTION_FAILED",
                message=f"Failed to resolve host '{hostname}': {e}",
                status_code=400,
                retryable=False,
            )


def validate_media_integrity(file_path: str) -> dict:
    """Validates video file integrity using FFprobe to detect corrupted or unreadable containers."""
    path = Path(file_path)
    if not path.exists() or path.stat().st_size < 1024:
        raise APIError(
            code="CORRUPTED_MEDIA",
            message=f"Downloaded media file is empty or too small ({path.stat().st_size if path.exists() else 0} bytes).",
            status_code=400,
            retryable=False,
        )

    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration,codec_name",
        "-show_entries", "format=duration,size,bit_rate",
        "-of", "json",
        str(path),
    ]

    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if proc.returncode != 0:
            err = proc.stderr.decode(errors="replace")
            raise APIError(
                code="CORRUPTED_MEDIA",
                message=f"Downloaded media failed FFprobe integrity verification: {err.strip()}",
                status_code=400,
                retryable=False,
            )

        info = json.loads(proc.stdout.decode(errors="replace"))
        streams = info.get("streams", [])
        if not streams:
            raise APIError(
                code="CORRUPTED_MEDIA",
                message="Downloaded media contains no valid video stream.",
                status_code=400,
                retryable=False,
            )

        v_stream = streams[0]
        width = int(v_stream.get("width") or 0)
        height = int(v_stream.get("height") or 0)
        if width <= 0 or height <= 0:
            raise APIError(
                code="CORRUPTED_MEDIA",
                message=f"Downloaded media has invalid dimensions: {width}x{height}",
                status_code=400,
                retryable=False,
            )

        return {
            "width": width,
            "height": height,
            "codec": v_stream.get("codec_name"),
            "duration": float(v_stream.get("duration") or info.get("format", {}).get("duration") or 0.0),
        }
    except json.JSONDecodeError:
        raise APIError(
            code="CORRUPTED_MEDIA",
            message="Downloaded media metadata could not be decoded.",
            status_code=400,
            retryable=False,
        )


async def download_media_securely(
    url: str,
    target_path: str,
    max_bytes: int = MAX_MEDIA_DOWNLOAD_SIZE_BYTES,
    timeout: float = DEFAULT_DOWNLOAD_TIMEOUT,
    allow_private_for_test: bool = False,
) -> dict:
    """Securely downloads media from URL with SSRF protection, redirect verification, size limits, and FFprobe validation.

    Returns:
        dict: FFprobe stream metadata
    """
    current_url = url
    total_redirects = 0

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        while True:
            # 1. Validate URL security on every hop
            validate_url_security(current_url, allow_private_for_test=allow_private_for_test)

            try:
                resp = await client.get(current_url)
            except Exception as e:
                if isinstance(e, APIError):
                    raise
                raise APIError(
                    code="CLIP_DOWNLOAD_FAILED",
                    message=f"Failed to fetch replacement clip from {current_url}: {e}",
                    status_code=400,
                    retryable=False,
                )

            # Handle redirects securely
            if resp.is_redirect:
                total_redirects += 1
                if total_redirects > MAX_REDIRECT_HOPS:
                    raise APIError(
                        code="TOO_MANY_REDIRECTS",
                        message=f"Media download exceeded maximum of {MAX_REDIRECT_HOPS} redirects.",
                        status_code=400,
                        retryable=False,
                    )
                location = resp.headers.get("Location")
                if not location:
                    raise APIError(
                        code="INVALID_REDIRECT",
                        message="Redirect response missing Location header.",
                        status_code=400,
                        retryable=False,
                    )
                current_url = urljoin(current_url, location)
                continue

            # Check HTTP status
            if resp.status_code != 200:
                raise APIError(
                    code="CLIP_DOWNLOAD_FAILED",
                    message=f"Failed to download replacement clip from {current_url}: HTTP {resp.status_code}",
                    status_code=400,
                    retryable=False,
                )

            # Check Content-Length if present
            cl = resp.headers.get("Content-Length")
            if cl and cl.isdigit() and int(cl) > max_bytes:
                raise APIError(
                    code="OVERSIZED_DOWNLOAD",
                    message=f"Media file size ({int(cl)} bytes) exceeds maximum allowed limit ({max_bytes} bytes).",
                    status_code=400,
                    retryable=False,
                )

            # Check response body size
            body = resp.content
            if len(body) > max_bytes:
                raise APIError(
                    code="OVERSIZED_DOWNLOAD",
                    message=f"Media file size ({len(body)} bytes) exceeds maximum allowed limit ({max_bytes} bytes).",
                    status_code=400,
                    retryable=False,
                )

            with open(target_path, "wb") as f:
                f.write(body)
            break

    # 2. Validate media integrity via FFprobe
    meta = validate_media_integrity(target_path)
    return meta
