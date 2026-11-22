"""Footage retrieval, ranking, deduplication, and attribution orchestrator (Phase 4)."""

import asyncio
from typing import List, Optional, Set
from broll_engine.config import settings
from broll_engine.logging import get_logger
from broll_engine.models.retrieval import (
    CandidateAsset,
    DeduplicationReport,
    FootageRetrievalResult,
    RankedAsset,
    SelectedClip,
)
from broll_engine.models.scenes import Scene
from broll_engine.retrieval.base import (
    BaseFootageProvider,
    FootageProviderError,
    RateLimitExceededError,
)
from broll_engine.retrieval.dedup import ClipDeduplicator
from broll_engine.retrieval.downloader import AssetDownloader, MediaValidationError
from broll_engine.retrieval.pexels import PexelsProvider
from broll_engine.retrieval.pixabay import PixabayProvider
from broll_engine.retrieval.storyblocks import StoryblocksFootageProvider
from broll_engine.retrieval.procedural import ProceduralFallbackProvider
from broll_engine.retrieval.ranker import SemanticRelevanceRanker

logger = get_logger(__name__)


class FootageRetrievalEngine:
    """Orchestrates multi-source footage search, semantic ranking, deduplication,

    licence verification, asset download, and procedural fallback.
    """

    def __init__(
        self,
        providers: Optional[List[BaseFootageProvider]] = None,
        ranker: Optional[SemanticRelevanceRanker] = None,
        deduplicator: Optional[ClipDeduplicator] = None,
        downloader: Optional[AssetDownloader] = None,
        procedural_provider: Optional[ProceduralFallbackProvider] = None,
        min_relevance_threshold: Optional[float] = None,
    ):
        self.procedural_provider = procedural_provider or ProceduralFallbackProvider()
        self.downloader = downloader or AssetDownloader()
        self.ranker = ranker or SemanticRelevanceRanker(
            min_threshold=min_relevance_threshold or settings.min_relevance_threshold
        )
        self.deduplicator = deduplicator or ClipDeduplicator()

        if providers is not None:
            self.providers = providers
        else:
            # Default provider chain: Pexels -> Pixabay -> Storyblocks -> Procedural
            self.providers = [
                PexelsProvider(),
                PixabayProvider(),
                StoryblocksFootageProvider(
                    public_key=settings.storyblocks_public_key,
                    private_key=settings.storyblocks_private_key,
                    enabled=settings.storyblocks_enabled,
                ),
            ]

    async def _query_providers_with_failover(
        self,
        query: str,
        aspect_ratio: str,
        per_page: int = 8,
    ) -> List[CandidateAsset]:
        """Queries external providers with automatic failover across Pexels and Pixabay."""
        candidates: List[CandidateAsset] = []

        for provider in self.providers:
            if not provider.is_configured:
                continue

            try:
                logger.info("Searching provider '%s' for visual query: '%s'", provider.provider_name, query)
                results = await provider.search_videos(
                    query=query,
                    aspect_ratio=aspect_ratio,
                    per_page=per_page,
                )
                if results:
                    # Filter candidates for strict commercial-use eligibility
                    valid_candidates = [
                        c for c in results
                        if c.license.commercial_use_eligible and c.license.clearance_status == "commercial_cleared"
                    ]
                    candidates.extend(valid_candidates)
                    if len(candidates) >= per_page:
                        break

            except RateLimitExceededError as e:
                logger.warning("Provider '%s' rate limited. Failing over to next provider.", provider.provider_name)
                continue
            except FootageProviderError as e:
                logger.warning("Provider '%s' failed (%s). Failing over.", provider.provider_name, e)
                continue
            except Exception as e:
                logger.warning("Unexpected error from provider '%s': %s", provider.provider_name, e)
                continue

        return candidates

    async def retrieve_for_scene(
        self,
        scene: Scene,
        aspect_ratio: str = "16:9",
        job_id: str = "default",
    ) -> SelectedClip:
        """Retrieves, deduplicates, and validates a B-roll video clip for a single scene."""
        query = scene.visual_query or scene.narration_text
        candidates = await self._query_providers_with_failover(
            query=query,
            aspect_ratio=aspect_ratio,
        )

        ranked_candidates: List[RankedAsset] = []
        if candidates:
            ranked_candidates = self.ranker.rank_candidates(
                candidates=candidates,
                visual_query=scene.visual_query,
                narration_text=scene.narration_text,
                visual_intent=scene.visual_intent,
                negative_constraints=scene.negative_constraints,
                requested_aspect=aspect_ratio,
            )

        # Select best candidate passing deduplication and threshold
        best_ranked = self.deduplicator.filter_and_select_best(
            ranked_candidates=ranked_candidates,
            min_threshold=self.ranker.min_threshold,
        )

        # If a valid stock candidate was chosen, attempt to download and validate media
        if best_ranked:
            cand = best_ranked.candidate
            try:
                local_path, content_hash, meta = await self.downloader.download_asset(
                    asset_id=cand.asset_id,
                    download_url=cand.download_url,
                )
                return SelectedClip(
                    scene_id=scene.id,
                    scene_index=scene.index,
                    asset_id=cand.asset_id,
                    provider=cand.provider,
                    relevance_score=best_ranked.relevance_score,
                    selection_reason=best_ranked.selection_reason,
                    license=cand.license,
                    creator=cand.creator_name,
                    creator_url=cand.creator_url,
                    original_page_url=cand.original_page_url,
                    download_url=cand.download_url,
                    local_path=local_path,
                    download_status="downloaded",
                    fallback_status="none",
                    width=meta.get("width", cand.width),
                    height=meta.get("height", cand.height),
                    duration_seconds=meta.get("duration", cand.duration_seconds),
                    is_ai_generated=cand.is_ai_generated,
                    is_procedural=False,
                    content_hash=content_hash,
                )
            except MediaValidationError as e:
                logger.warning(
                    "Media download/validation failed for asset '%s' (%s). Triggering procedural fallback.",
                    cand.asset_id,
                    e,
                )

        # Fallback to deterministic procedural generation
        logger.info(
            "Scene %d ('%s') invoking procedural fallback (theme=%s)",
            scene.index,
            scene.id,
            scene.visual_intent,
        )
        proc_candidates = await self.procedural_provider.search_videos(
            query=f"{scene.visual_intent} {scene.visual_query[:20]}",
            aspect_ratio=aspect_ratio,
        )
        proc_cand = proc_candidates[0]

        # Generate actual procedural video via FFmpeg
        target_path = str(self.downloader.get_cached_path(f"{job_id}_{scene.id}_{proc_cand.asset_id}"))
        await self.procedural_provider.generate_clip(
            target_path=target_path,
            duration=scene.duration_seconds,
            aspect_ratio=aspect_ratio,
            theme=scene.visual_intent,
        )

        meta = await self.downloader.validate_media(target_path)
        sha256 = self.downloader._compute_sha256(target_path)
        self.deduplicator.register_selection(proc_cand, content_hash=sha256)

        return SelectedClip(
            scene_id=scene.id,
            scene_index=scene.index,
            asset_id=proc_cand.asset_id,
            provider="procedural",
            relevance_score=3.5,
            selection_reason=(
                f"Procedural geometric motion background synthesized for '{scene.visual_intent}' "
                f"theme (zero gaps, commercial CC0 equivalent)."
            ),
            license=proc_cand.license,
            creator=proc_cand.creator_name,
            creator_url=proc_cand.creator_url,
            original_page_url=proc_cand.original_page_url,
            download_url=f"file://{target_path}",
            local_path=target_path,
            download_status="procedural_fallback",
            fallback_status="procedural_gradient",
            width=meta.get("width", 1920),
            height=meta.get("height", 1080),
            duration_seconds=meta.get("duration", scene.duration_seconds),
            is_ai_generated=False,
            is_procedural=True,
            content_hash=sha256,
        )

    def reset_deduplication(self) -> None:
        """Clears the deduplication registry.

        The engine is a long-lived singleton shared across jobs; per-video
        uniqueness must be tracked per job, so the registry is reset at the
        start of every retrieve_for_scenes call (and single-scene swaps).
        """
        self.deduplicator = ClipDeduplicator()

    async def retrieve_for_scenes(
        self,
        scenes: List[Scene],
        aspect_ratio: str = "16:9",
        job_id: str = "job_default",
    ) -> FootageRetrievalResult:
        """Retrieves and maps footage assets for all scenes sequentially."""
        self.reset_deduplication()
        clips: List[SelectedClip] = []
        providers_used: Set[str] = set()

        for scene in scenes:
            clip = await self.retrieve_for_scene(
                scene=scene,
                aspect_ratio=aspect_ratio,
                job_id=job_id,
            )
            clips.append(clip)
            providers_used.add(clip.provider)

        dedup_report = self.deduplicator.generate_report()
        total = len(scenes)
        procedural_count = sum(1 for c in clips if c.is_procedural)
        stock_count = total - procedural_count

        return FootageRetrievalResult(
            job_id=job_id,
            total_scenes=total,
            clips=clips,
            deduplication=dedup_report,
            providers_queried=[p.provider_name for p in self.providers if p.is_configured],
            retrieval_success_rate=round(stock_count / max(total, 1), 3),
            procedural_fallback_rate=round(procedural_count / max(total, 1), 3),
        )
