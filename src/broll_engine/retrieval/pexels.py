"""Pexels Video API footage provider implementation (Phase 4)."""

import asyncio
from typing import Any, Dict, List, Optional
import httpx

from broll_engine.config import settings
from broll_engine.logging import get_logger
from broll_engine.models.retrieval import (
    AssetLicense,
    CandidateAsset,
    VideoFile,
)
from broll_engine.retrieval.base import (
    BaseFootageProvider,
    FootageProviderError,
    InvalidCredentialsError,
    RateLimitExceededError,
)

logger = get_logger(__name__)


class PexelsProvider(BaseFootageProvider):
    """Integrates with the official Pexels Video Search API."""

    BASE_URL = "https://api.pexels.com/videos/search"
    LICENSE_URL = "https://www.pexels.com/license/"

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 10.0,
        max_retries: int = 2,
    ):
        self.api_key = api_key or settings.pexels_api_key
        self.timeout = timeout
        self.max_retries = max_retries

    @property
    def provider_name(self) -> str:
        return "pexels"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def _map_orientation(self, aspect_ratio: str) -> str:
        if aspect_ratio == "9:16":
            return "portrait"
        elif aspect_ratio == "1:1":
            return "square"
        return "landscape"

    async def search_videos(
        self,
        query: str,
        aspect_ratio: str = "16:9",
        per_page: int = 10,
    ) -> List[CandidateAsset]:
        """Search Pexels API for video stock matching query."""
        if not self.is_configured:
            logger.warning("Pexels API key is not configured. Skipping provider.")
            return []

        orientation = self._map_orientation(aspect_ratio)
        params = {
            "query": query,
            "per_page": min(per_page, 20),
            "orientation": orientation,
        }
        headers = {
            "Authorization": self.api_key.strip(),
            "User-Agent": "IncuBrix-BrollEngine/0.1.0",
        }

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(self.BASE_URL, params=params, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    return self._parse_candidates(data, aspect_ratio)

                if response.status_code in (401, 403):
                    logger.error("Pexels authentication failed (HTTP %d)", response.status_code)
                    raise InvalidCredentialsError(self.provider_name, response.text)

                if response.status_code == 429:
                    retry_after = None
                    if "Retry-After" in response.headers:
                        try:
                            retry_after = int(response.headers["Retry-After"])
                        except ValueError:
                            pass
                    logger.warning("Pexels rate limit hit (HTTP 429). Retry-After: %s", retry_after)
                    raise RateLimitExceededError(self.provider_name, retry_after)

                logger.warning(
                    "Pexels API returned status %d on attempt %d: %s",
                    response.status_code,
                    attempt + 1,
                    response.text,
                )
                last_error = FootageProviderError(
                    f"Pexels API returned HTTP {response.status_code}",
                    provider=self.provider_name,
                    retryable=response.status_code >= 500,
                    status_code=response.status_code,
                )

            except (httpx.RequestError, httpx.TimeoutException) as exc:
                logger.warning("Pexels connection failure on attempt %d: %s", attempt + 1, exc)
                last_error = FootageProviderError(
                    f"Pexels network error: {str(exc)}",
                    provider=self.provider_name,
                    retryable=True,
                )

            if attempt < self.max_retries:
                await asyncio.sleep(1.0 * (2 ** attempt))

        if last_error:
            raise last_error
        return []

    def _parse_candidates(self, data: Dict[str, Any], requested_aspect: str) -> List[CandidateAsset]:
        raw_videos = data.get("videos", [])
        candidates = []

        for item in raw_videos:
            try:
                asset_id = f"pexels_{item['id']}"
                creator_info = item.get("user", {})
                creator_name = creator_info.get("name") or "Pexels Creator"
                creator_url = creator_info.get("url")
                page_url = item.get("url") or f"https://www.pexels.com/video/{item['id']}/"
                duration = float(item.get("duration", 0.0))

                video_files_data = item.get("video_files", [])
                video_files = []
                best_file = None

                for vf in video_files_data:
                    link = vf.get("link")
                    if not link:
                        continue
                    width = int(vf.get("width") or 0)
                    height = int(vf.get("height") or 0)
                    quality = vf.get("quality", "sd")
                    file_type = vf.get("file_type", "video/mp4")
                    fps = float(vf.get("fps") or 30.0)

                    file_obj = VideoFile(
                        id=str(vf.get("id", "")),
                        quality=quality,
                        width=width,
                        height=height,
                        fps=fps,
                        link=link,
                        file_type=file_type,
                    )
                    video_files.append(file_obj)

                    # Prefer HD (1080p) or highest available resolution
                    if best_file is None or (width >= 1280 and width > best_file.width):
                        best_file = file_obj

                if not best_file:
                    continue

                # Licence Verification: Pexels License explicitly clears commercial use
                license_meta = AssetLicense(
                    license_name="Pexels License",
                    license_url=self.LICENSE_URL,
                    commercial_use_eligible=True,
                    attribution_required=False,
                    attribution_text=f"Video by {creator_name} on Pexels",
                    clearance_status="commercial_cleared",
                    verification_notes=(
                        "Commercially cleared under Pexels License terms. "
                        "Unaltered redistribution and endorsement implications prohibited."
                    ),
                )

                candidate = CandidateAsset(
                    asset_id=asset_id,
                    provider=self.provider_name,
                    title=f"Pexels Video {item['id']}",
                    description=page_url,
                    tags=[t.get("tag", "") for t in item.get("tags", []) if isinstance(t, dict)]
                    or [w.strip() for w in query_to_tags(page_url)],
                    duration_seconds=duration,
                    width=best_file.width,
                    height=best_file.height,
                    aspect_ratio=requested_aspect,
                    creator_name=creator_name,
                    creator_url=creator_url,
                    original_page_url=page_url,
                    download_url=best_file.link,
                    license=license_meta,
                    is_ai_generated=False,
                    is_procedural=False,
                    video_files=video_files,
                )
                candidates.append(candidate)

            except Exception as e:
                logger.warning("Error parsing Pexels video candidate: %s", e)
                continue

        return candidates


def query_to_tags(url: str) -> List[str]:
    """Helper to extract descriptive tokens from Pexels video URL slug."""
    try:
        parts = url.rstrip("/").split("/")[-1].split("-")
        return [p for p in parts if p and not p.isdigit()]
    except Exception:
        return []
