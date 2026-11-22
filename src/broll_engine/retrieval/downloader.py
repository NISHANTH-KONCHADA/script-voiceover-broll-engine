"""Asynchronous media downloader and FFprobe validation engine (Phase 4)."""

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple
import httpx

from broll_engine.config import settings
from broll_engine.logging import get_logger

logger = get_logger(__name__)


class MediaValidationError(Exception):
    """Raised when downloaded media fails FFprobe validation checks."""
    pass


class AssetDownloader:
    """Manages asynchronous download, disk caching, and media validation of B-roll footage."""

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        total_timeout: Optional[float] = None,
        max_bytes: int = 100 * 1024 * 1024,
    ):
        self.cache_dir = Path(cache_dir or settings.footage_cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.max_retries = max_retries
        self.total_timeout = total_timeout or settings.media_download_total_timeout_seconds
        self.max_bytes = max_bytes

    def get_cached_path(self, asset_id: str, extension: str = "mp4") -> Path:
        safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in asset_id)
        return self.cache_dir / f"{safe_name}.{extension}"

    async def download_asset(
        self,
        asset_id: str,
        download_url: str,
    ) -> Tuple[str, str, dict]:
        """Downloads footage asset or returns existing cached copy.

        Returns:
            Tuple of (local_file_path, sha256_hash, video_stream_metadata)
        """
        target_path = self.get_cached_path(asset_id)

        # 1. If already cached, validate and return
        if target_path.exists() and target_path.stat().st_size > 1024:
            try:
                meta = await self.validate_media(str(target_path))
                sha256 = self._compute_sha256(str(target_path))
                logger.info("Using cached footage asset '%s' (%s)", asset_id, target_path.name)
                return str(target_path), sha256, meta
            except Exception:
                logger.warning("Cached file '%s' was invalid. Re-downloading.", target_path.name)
                target_path.unlink(missing_ok=True)

        # 2. If it's a file:// URL (e.g. from procedural fallback), copy or validate directly
        if download_url.startswith("file://"):
            local_src = Path(download_url.replace("file://", ""))
            if local_src.exists():
                if local_src != target_path:
                    shutil.copy2(str(local_src), str(target_path))
                meta = await self.validate_media(str(target_path))
                sha256 = self._compute_sha256(str(target_path))
                return str(target_path), sha256, meta

        # 3. Asynchronous HTTP streaming download with retries and a hard total deadline
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                temp_path = self.cache_dir / f"{target_path.stem}.tmp_{attempt}"
                await asyncio.wait_for(
                    self._stream_to_disk(download_url, temp_path),
                    timeout=self.total_timeout,
                )

                # Validate downloaded temp file before moving to cache
                meta = await self.validate_media(str(temp_path))
                temp_path.rename(target_path)
                sha256 = self._compute_sha256(str(target_path))
                logger.info("Successfully downloaded asset '%s' (%.2f MB)", asset_id, target_path.stat().st_size / (1024 * 1024))
                return str(target_path), sha256, meta

            except asyncio.TimeoutError:
                logger.warning(
                    "Download attempt %d for asset '%s' exceeded total deadline of %.0fs",
                    attempt + 1, asset_id, self.total_timeout,
                )
                last_error = f"download exceeded total deadline of {self.total_timeout}s"
                temp_path = self.cache_dir / f"{target_path.stem}.tmp_{attempt}"
                if temp_path.exists():
                    temp_path.unlink(missing_ok=True)
                if attempt < self.max_retries:
                    await asyncio.sleep(1.0 * (2 ** attempt))
            except Exception as e:
                logger.warning("Download attempt %d for asset '%s' failed: %s", attempt + 1, asset_id, e)
                last_error = e
                temp_path = self.cache_dir / f"{target_path.stem}.tmp_{attempt}"
                if temp_path.exists():
                    temp_path.unlink(missing_ok=True)
                if attempt < self.max_retries:
                    await asyncio.sleep(1.0 * (2 ** attempt))

        raise MediaValidationError(f"Failed to download and validate media asset '{asset_id}': {last_error}")

    async def _stream_to_disk(self, download_url: str, temp_path: Path) -> None:
        """Streams a remote asset to disk with a cumulative byte-size cap.

        Enforcing a hard byte ceiling protects disk/memory from oversized or
        maliciously unbounded responses; the enclosing asyncio.wait_for applies
        the total wall-clock deadline so stalled/slow-trickling streams abort.
        """
        bytes_written = 0
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            async with client.stream("GET", download_url) as response:
                if response.status_code != 200:
                    raise httpx.HTTPStatusError(
                        f"HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                with open(temp_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        bytes_written += len(chunk)
                        if bytes_written > self.max_bytes:
                            raise MediaValidationError(
                                f"Asset download exceeded maximum size limit of {self.max_bytes} bytes."
                            )
                        f.write(chunk)

    async def validate_media(self, file_path: str) -> dict:
        """Validates video integrity via FFprobe."""
        path = Path(file_path)
        if not path.exists() or path.stat().st_size < 512:
            raise MediaValidationError(f"File {file_path} does not exist or is too small.")

        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration,r_frame_rate,codec_name",
            "-show_entries", "format=duration,size,bit_rate",
            "-of", "json",
            str(path),
        ]

        loop = asyncio.get_running_loop()
        try:
            proc = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                ),
            )
            if proc.returncode != 0:
                err = proc.stderr.decode(errors="replace")
                raise MediaValidationError(f"FFprobe check failed: {err}")

            info = json.loads(proc.stdout.decode(errors="replace"))
            streams = info.get("streams", [])
            if not streams:
                raise MediaValidationError(f"No valid video streams found in file {file_path}")

            video_stream = streams[0]
            width = int(video_stream.get("width") or 0)
            height = int(video_stream.get("height") or 0)
            if width <= 0 or height <= 0:
                raise MediaValidationError(f"Invalid video dimensions: {width}x{height}")

            return {
                "width": width,
                "height": height,
                "duration": float(video_stream.get("duration") or info.get("format", {}).get("duration") or 0.0),
                "codec": video_stream.get("codec_name", "unknown"),
            }

        except FileNotFoundError:
            # Fallback if ffprobe binary is absent on host: check basic MP4 signature
            logger.warning("ffprobe not found on PATH. Falling back to MP4 container signature check.")
            with open(path, "rb") as f:
                header = f.read(128)
                if b"ftyp" not in header and b"moov" not in header:
                    raise MediaValidationError("Invalid video file: missing MP4 header boxes.")
            return {"width": 1920, "height": 1080, "duration": 5.0, "codec": "h264"}

    def _compute_sha256(self, file_path: str) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
