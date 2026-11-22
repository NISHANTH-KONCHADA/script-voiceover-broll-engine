"""Pixabay Video API footage provider implementation (Phase 4)."""

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


class PixabayProvider(BaseFootageProvider):
    """Integrates with the official Pixabay Video Search API."""

    BASE_URL = "https://pixabay.com/api/videos/"
    LICENSE_URL = "https://pixabay.com/service/license-summary/"

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 10.0,
        max_retries: int = 2,
    ):
        self.api_key = api_key or settings.pixabay_api_key
        self.timeout = timeout
        self.max_retries = max_retries

    @property
    def provider_name(self) -> str:
        return "pixabay"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    async def search_videos(
        self,
        query: str,
        aspect_ratio: str = "16:9",
        per_page: int = 10,
    ) -> List[CandidateAsset]:
        """Search Pixabay API for video stock matching query."""
        if not self.is_configured:
            logger.warning("Pixabay API key is not configured. Skipping provider.")
            return []

        # Pixabay rejects queries longer than 100 characters; trim at a word boundary.
        if len(query) > 100:
            trimmed = query[:100].rsplit(" ", 1)[0].rstrip(" ,")
            logger.info("Truncating over-length Pixabay query (%d -> %d chars)", len(query), len(trimmed))
            query = trimmed or query[:100]

        params = {
            "key": self.api_key.strip(),
            "q": query,
            "per_page": min(max(per_page, 3), 20),
            "video_type": "film",
        }
        headers = {
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

                if response.status_code in (400, 401, 403) and "key" in response.text.lower():
                    logger.error("Pixabay authentication failed (HTTP %d)", response.status_code)
                    raise InvalidCredentialsError(self.provider_name, response.text)

                if response.status_code == 429:
                    logger.warning("Pixabay rate limit hit (HTTP 429).")
                    raise RateLimitExceededError(self.provider_name)

                logger.warning(
                    "Pixabay API returned status %d on attempt %d: %s",
                    response.status_code,
                    attempt + 1,
                    response.text,
                )
                last_error = FootageProviderError(
                    f"Pixabay API returned HTTP {response.status_code}",
                    provider=self.provider_name,
                    retryable=response.status_code >= 500,
                    status_code=response.status_code,
                )

            except (httpx.RequestError, httpx.TimeoutException) as exc:
                logger.warning("Pixabay connection failure on attempt %d: %s", attempt + 1, exc)
                last_error = FootageProviderError(
                    f"Pixabay network error: {str(exc)}",
                    provider=self.provider_name,
                    retryable=True,
                )

            if attempt < self.max_retries:
                await asyncio.sleep(1.0 * (2 ** attempt))

        if last_error:
            raise last_error
        return []

    def _parse_candidates(self, data: Dict[str, Any], requested_aspect: str) -> List[CandidateAsset]:
        hits = data.get("hits", [])
        candidates = []

        for item in hits:
            try:
                asset_id = f"pixabay_{item['id']}"
                creator_name = item.get("user") or "Pixabay Contributor"
                creator_url = f"https://pixabay.com/users/{item.get('user')}-{item.get('user_id')}/" if item.get("user") else None
                page_url = item.get("pageURL") or f"https://pixabay.com/videos/id-{item['id']}/"
                duration = float(item.get("duration", 0.0))
                tags_str = item.get("tags", "")
                tags = [t.strip() for t in tags_str.split(",") if t.strip()]

                raw_videos = item.get("videos", {})
                video_files = []
                best_file = None

                # Rendition order: large (1080p), medium (720p), small (540p), tiny (360p)
                for size_key in ("large", "medium", "small", "tiny"):
                    v_meta = raw_videos.get(size_key)
                    if not v_meta or not v_meta.get("url"):
                        continue
                    width = int(v_meta.get("width") or 0)
                    height = int(v_meta.get("height") or 0)
                    link = v_meta.get("url")

                    file_obj = VideoFile(
                        id=f"{asset_id}_{size_key}",
                        quality=size_key,
                        width=width,
                        height=height,
                        fps=30.0,
                        link=link,
                        file_type="video/mp4",
                    )
                    video_files.append(file_obj)

                    if best_file is None or (width >= 1280 and width > best_file.width):
                        best_file = file_obj

                if not best_file:
                    continue

                # Licence Verification: Pixabay Content License clears commercial use
                license_meta = AssetLicense(
                    license_name="Pixabay Content License",
                    license_url=self.LICENSE_URL,
                    commercial_use_eligible=True,
                    attribution_required=False,
                    attribution_text=f"Video by {creator_name} from Pixabay",
                    clearance_status="commercial_cleared",
                    verification_notes=(
                        "Commercially cleared under Pixabay Content License terms. "
                        "Standalone redistribution prohibited."
                    ),
                )

                candidate = CandidateAsset(
                    asset_id=asset_id,
                    provider=self.provider_name,
                    title=f"Pixabay Video {item['id']}: {tags_str[:40]}",
                    description=page_url,
                    tags=tags,
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
                logger.warning("Error parsing Pixabay video candidate: %s", e)
                continue

        return candidates
