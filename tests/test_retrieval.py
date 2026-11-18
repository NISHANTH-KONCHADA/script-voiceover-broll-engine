"""Automated test suite for Phase 4: Footage Retrieval, Ranking, Deduplication & Attribution."""

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest

from broll_engine.models.retrieval import (
    AssetLicense,
    CandidateAsset,
    VideoFile,
)
from broll_engine.models.scenes import (
    PacingStatus,
    Scene,
    SceneSegmentationResult,
    SegmentationReason,
    TimingSource,
)
from broll_engine.retrieval.base import (
    FootageProviderError,
    InvalidCredentialsError,
    RateLimitExceededError,
)
from broll_engine.retrieval.dedup import ClipDeduplicator
from broll_engine.retrieval.downloader import AssetDownloader, MediaValidationError
from broll_engine.retrieval.engine import FootageRetrievalEngine
from broll_engine.retrieval.pexels import PexelsProvider
from broll_engine.retrieval.pixabay import PixabayProvider
from broll_engine.retrieval.procedural import ProceduralFallbackProvider
from broll_engine.retrieval.ranker import SemanticRelevanceRanker

# Mock API payloads for offline determinism
MOCK_PEXELS_PAYLOAD = {
    "page": 1,
    "per_page": 2,
    "total_results": 100,
    "url": "https://www.pexels.com/search/videos/datacenter/",
    "videos": [
        {
            "id": 1409899,
            "width": 1920,
            "height": 1080,
            "duration": 15.0,
            "url": "https://www.pexels.com/video/datacenter-server-racks-1409899/",
            "user": {"id": 1234, "name": "Cottonbro Studio", "url": "https://www.pexels.com/@cottonbro"},
            "video_files": [
                {
                    "id": 1,
                    "quality": "hd",
                    "file_type": "video/mp4",
                    "width": 1920,
                    "height": 1080,
                    "fps": 29.97,
                    "link": "https://player.vimeo.com/external/1409899.hd.mp4",
                }
            ],
        }
    ],
}

MOCK_PIXABAY_PAYLOAD = {
    "total": 50,
    "totalHits": 50,
    "hits": [
        {
            "id": 31298,
            "pageURL": "https://pixabay.com/videos/server-database-tech-31298/",
            "type": "film",
            "tags": "server, database, technology, datacenter",
            "duration": 18.0,
            "videos": {
                "large": {
                    "url": "https://cdn.pixabay.com/video/31298/large.mp4",
                    "width": 1920,
                    "height": 1080,
                    "size": 543210,
                }
            },
            "user_id": 5678,
            "user": "TechFilmer",
        }
    ],
}


@pytest.fixture
def temp_cache_dir():
    d = tempfile.mkdtemp(prefix="broll_test_cache_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.mark.asyncio
async def test_pexels_adapter_parses_candidates_and_licenses():
    provider = PexelsProvider(api_key="test_pexels_key")
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = MOCK_PEXELS_PAYLOAD
        mock_get.return_value = mock_resp

        candidates = await provider.search_videos("datacenter server racks", aspect_ratio="16:9")

    assert len(candidates) == 1
    c = candidates[0]
    assert c.asset_id == "pexels_1409899"
    assert c.provider == "pexels"
    assert c.creator_name == "Cottonbro Studio"
    assert c.license.commercial_use_eligible is True
    assert c.license.license_name == "Pexels License"
    assert "Cottonbro Studio" in c.license.attribution_text
    assert c.download_url == "https://player.vimeo.com/external/1409899.hd.mp4"


@pytest.mark.asyncio
async def test_pixabay_adapter_parses_candidates_and_licenses():
    provider = PixabayProvider(api_key="test_pixabay_key")
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = MOCK_PIXABAY_PAYLOAD
        mock_get.return_value = mock_resp

        candidates = await provider.search_videos("server database", aspect_ratio="16:9")

    assert len(candidates) == 1
    c = candidates[0]
    assert c.asset_id == "pixabay_31298"
    assert c.provider == "pixabay"
    assert c.creator_name == "TechFilmer"
    assert c.license.commercial_use_eligible is True
    assert c.license.license_name == "Pixabay Content License"
    assert "server" in c.tags


@pytest.mark.asyncio
async def test_provider_invalid_credentials_raises_error():
    provider = PexelsProvider(api_key="bad_key")
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock(status_code=401, text="Unauthorized: Invalid API Key")
        mock_get.return_value = mock_resp

        with pytest.raises(InvalidCredentialsError):
            await provider.search_videos("test")


@pytest.mark.asyncio
async def test_provider_rate_limit_and_retries():
    provider = PixabayProvider(api_key="test_key")
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock(status_code=429, text="Rate limit exceeded")
        mock_get.return_value = mock_resp

        with pytest.raises(RateLimitExceededError):
            await provider.search_videos("test")


@pytest.mark.asyncio
async def test_provider_failover():
    """Verify that when primary provider (Pexels) fails, engine falls back to secondary (Pixabay)."""
    pexels_mock = PexelsProvider(api_key="failing_key")
    pixabay_mock = PixabayProvider(api_key="working_key")

    with patch.object(pexels_mock, "search_videos", side_effect=FootageProviderError("Timeout", "pexels")):
        with patch.object(pixabay_mock, "search_videos") as mock_pixabay_search:
            mock_candidate = CandidateAsset(
                asset_id="pixabay_999",
                provider="pixabay",
                title="Secondary Stock",
                tags=["technology"],
                duration_seconds=10.0,
                width=1920,
                height=1080,
                original_page_url="https://pixabay.com/test",
                download_url="https://pixabay.com/test.mp4",
                license=AssetLicense(
                    license_name="Pixabay Content License",
                    license_url="https://pixabay.com/service/license-summary/",
                    commercial_use_eligible=True,
                    attribution_text="Credit Pixabay",
                ),
            )
            mock_pixabay_search.return_value = [mock_candidate]

            engine = FootageRetrievalEngine(providers=[pexels_mock, pixabay_mock])
            candidates = await engine._query_providers_with_failover("test query", "16:9")

    assert len(candidates) == 1
    assert candidates[0].asset_id == "pixabay_999"


@pytest.mark.asyncio
async def test_procedural_fallback_generates_valid_mp4(temp_cache_dir):
    provider = ProceduralFallbackProvider(output_dir=temp_cache_dir)
    target_mp4 = os.path.join(temp_cache_dir, "test_proc.mp4")

    out_file = await provider.generate_clip(
        target_path=target_mp4,
        duration=2.5,
        aspect_ratio="16:9",
        theme="technology",
    )

    assert os.path.exists(out_file)
    assert os.path.getsize(out_file) > 1024

    downloader = AssetDownloader(cache_dir=temp_cache_dir)
    meta = await downloader.validate_media(out_file)
    assert meta["width"] == 1920
    assert meta["height"] == 1080
    assert meta["duration"] > 2.0


def test_semantic_relevance_ranking_and_homonym_penalty():
    ranker = SemanticRelevanceRanker()

    tech_candidate = CandidateAsset(
        asset_id="stock_tech_01",
        provider="pexels",
        title="Server racks in datacenter room",
        tags=["datacenter", "servers", "cloud", "computing", "technology"],
        duration_seconds=12.0,
        original_page_url="https://example.com/1",
        download_url="https://example.com/1.mp4",
        license=AssetLicense(
            license_name="Commercial",
            license_url="https://example.com",
            commercial_use_eligible=True,
            attribution_text="Credit",
        ),
    )

    sky_candidate = CandidateAsset(
        asset_id="stock_sky_02",
        provider="pixabay",
        title="White clouds in bright blue sky",
        tags=["clouds", "sky", "weather", "atmosphere", "cumulus"],
        duration_seconds=15.0,
        original_page_url="https://example.com/2",
        download_url="https://example.com/2.mp4",
        license=AssetLicense(
            license_name="Commercial",
            license_url="https://example.com",
            commercial_use_eligible=True,
            attribution_text="Credit",
        ),
    )

    query = "datacenter server racks glowing blue lights technology"
    ranked_tech = ranker.rank_candidate(
        candidate=tech_candidate,
        visual_query=query,
        narration_text="Cloud computing enables scalable backend apps",
        visual_intent="technology",
    )

    ranked_sky = ranker.rank_candidate(
        candidate=sky_candidate,
        visual_query=query,
        narration_text="Cloud computing enables scalable backend apps",
        visual_intent="technology",
    )

    # Tech candidate should score high (> 3.5), sky candidate should suffer homonym penalty (< 1.5)
    assert ranked_tech.relevance_score >= 3.5
    assert ranked_sky.relevance_score <= 1.5
    assert ranked_sky.penalty_applied > 0.5
    assert "Homonym collision" in ranked_sky.selection_reason


def test_clip_deduplication_exact_and_near_duplicates():
    dedup = ClipDeduplicator(near_duplicate_threshold=0.80)
    ranker = SemanticRelevanceRanker()

    c1 = CandidateAsset(
        asset_id="clip_001",
        provider="pexels",
        title="Modern business meeting room",
        tags=["business", "office", "meeting", "handshake"],
        creator_name="Alex Filmer",
        duration_seconds=10.0,
        original_page_url="https://example.com/c1",
        download_url="https://example.com/c1.mp4",
        license=AssetLicense(
            license_name="Commercial",
            license_url="https://example.com",
            commercial_use_eligible=True,
            attribution_text="Alex",
        ),
    )

    # Near duplicate of c1 by same author
    c1_near = CandidateAsset(
        asset_id="clip_002",
        provider="pexels",
        title="Modern corporate office meeting",
        tags=["business", "office", "meeting", "colleagues"],
        creator_name="Alex Filmer",
        duration_seconds=10.0,
        original_page_url="https://example.com/c2",
        download_url="https://example.com/c2.mp4",
        license=AssetLicense(
            license_name="Commercial",
            license_url="https://example.com",
            commercial_use_eligible=True,
            attribution_text="Alex",
        ),
    )

    # Distinct clip by different author
    c2_distinct = CandidateAsset(
        asset_id="clip_003",
        provider="pixabay",
        title="Modern glass corporate office tower skyline",
        tags=["business", "corporate", "office", "skyline"],
        creator_name="Urban Drone",
        duration_seconds=10.0,
        original_page_url="https://example.com/c3",
        download_url="https://example.com/c3.mp4",
        license=AssetLicense(
            license_name="Commercial",
            license_url="https://example.com",
            commercial_use_eligible=True,
            attribution_text="Urban",
        ),
    )

    ranked_1 = ranker.rank_candidates([c1, c1_near, c2_distinct], visual_query="business meeting office")

    # First scene selection accepts c1
    selected_1 = dedup.filter_and_select_best(ranked_1)
    assert selected_1 is not None
    assert selected_1.candidate.asset_id == "clip_001"

    # Second scene with same candidates should reject exact duplicate (c1) AND near duplicate (c1_near)
    selected_2 = dedup.filter_and_select_best(ranked_1)
    assert selected_2 is not None
    assert selected_2.candidate.asset_id == "clip_003"  # Prefers distinct asset

    # Deduplication report verification
    report = dedup.generate_report()
    assert report.unique_clips_selected == 2
    assert report.duplicate_candidates_rejected >= 1


@pytest.mark.asyncio
async def test_media_downloader_rejects_corrupted_file(temp_cache_dir):
    downloader = AssetDownloader(cache_dir=temp_cache_dir)
    corrupted_file = os.path.join(temp_cache_dir, "corrupt.mp4")
    with open(corrupted_file, "wb") as f:
        f.write(b"NOT_A_VALID_MP4_HEADER")

    with pytest.raises(MediaValidationError):
        await downloader.validate_media(corrupted_file)


@pytest.mark.asyncio
async def test_end_to_end_scene_retrieval_and_manifest_provenance(temp_cache_dir):
    """Verifies complete scene-to-clip mapping with zero duplicates and full provenance."""
    downloader = AssetDownloader(cache_dir=temp_cache_dir)
    procedural = ProceduralFallbackProvider(output_dir=temp_cache_dir)

    scenes = [
        Scene(
            id="scene_001",
            index=0,
            start_seconds=0.0,
            end_seconds=3.0,
            duration_seconds=3.0,
            narration_text="Cloud computing allows developers to deploy code.",
            visual_query="datacenter server racks glowing blue lights technology",
            visual_intent="technology",
            negative_constraints=["clouds", "sky"],
            segmentation_reason=SegmentationReason.SENTENCE_BOUNDARY,
            pacing_status=PacingStatus.VALID,
            timing_source=TimingSource.ASR_ACOUSTIC,
        ),
        Scene(
            id="scene_002",
            index=1,
            start_seconds=3.0,
            end_seconds=6.0,
            duration_seconds=3.0,
            narration_text="Trust and security are essential for modern enterprises.",
            visual_query="two business partners shaking hands in well-lit corporate boardroom",
            visual_intent="business",
            negative_constraints=["cartoons"],
            segmentation_reason=SegmentationReason.SENTENCE_BOUNDARY,
            pacing_status=PacingStatus.VALID,
            timing_source=TimingSource.ASR_ACOUSTIC,
        ),
    ]

    engine = FootageRetrievalEngine(
        downloader=downloader,
        procedural_provider=procedural,
        providers=[],  # Empty external providers forces procedural generation
    )

    result = await engine.retrieve_for_scenes(scenes, aspect_ratio="16:9", job_id="test_job_p4")

    assert result.total_scenes == 2
    assert len(result.clips) == 2
    assert result.clips[0].scene_id == "scene_001"
    assert result.clips[1].scene_id == "scene_002"

    # Clips must be distinct (no duplicate asset IDs)
    assert result.clips[0].asset_id != result.clips[1].asset_id
    assert result.clips[0].license.commercial_use_eligible is True
    assert result.clips[1].license.commercial_use_eligible is True
    assert os.path.exists(result.clips[0].local_path)
    assert os.path.exists(result.clips[1].local_path)
    assert result.clips[0].content_hash is not None
    assert result.clips[1].content_hash is not None
