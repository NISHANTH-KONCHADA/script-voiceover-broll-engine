"""Verification script for live footage providers (Pexels, Pixabay, Procedural)."""

import asyncio
import os
import sys
from pathlib import Path

# Add src to pythonpath
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from broll_engine.config import settings
from broll_engine.models.scenes import PacingStatus, Scene, SegmentationReason, TimingSource
from broll_engine.retrieval.downloader import AssetDownloader
from broll_engine.retrieval.engine import FootageRetrievalEngine
from broll_engine.retrieval.pexels import PexelsProvider
from broll_engine.retrieval.pixabay import PixabayProvider
from broll_engine.retrieval.procedural import ProceduralFallbackProvider
from broll_engine.retrieval.ranker import SemanticRelevanceRanker


async def main():
    print("=" * 70)
    print("IncuBrix B-roll Engine: Phase 4 Footage Retrieval Verification")
    print("=" * 70)

    # 1. Pexels Provider Status
    pexels = PexelsProvider()
    print(f"\n1. Pexels Provider:")
    print(f"   - Configured: {pexels.is_configured}")
    if pexels.is_configured:
        print("   - Testing live query: 'datacenter server technology'...")
        try:
            candidates = await pexels.search_videos("datacenter server technology", per_page=3)
            print(f"   - Successfully retrieved {len(candidates)} candidates:")
            for c in candidates:
                print(f"     * [{c.asset_id}] {c.title} by {c.creator_name} ({c.width}x{c.height}, {c.duration_seconds}s)")
                print(f"       Licence: {c.license.license_name} (Commercial: {c.license.commercial_use_eligible})")
        except Exception as e:
            print(f"   - Error querying Pexels: {e}")
    else:
        print("   - PEXELS_API_KEY not set in environment. Skipping live API call.")

    # 2. Pixabay Provider Status
    pixabay = PixabayProvider()
    print(f"\n2. Pixabay Provider:")
    print(f"   - Configured: {pixabay.is_configured}")
    if pixabay.is_configured:
        print("   - Testing live query: 'server database technology'...")
        try:
            candidates = await pixabay.search_videos("server database technology", per_page=3)
            print(f"   - Successfully retrieved {len(candidates)} candidates:")
            for c in candidates:
                print(f"     * [{c.asset_id}] {c.title} by {c.creator_name} ({c.width}x{c.height}, {c.duration_seconds}s)")
                print(f"       Licence: {c.license.license_name} (Commercial: {c.license.commercial_use_eligible})")
        except Exception as e:
            print(f"   - Error querying Pixabay: {e}")
    else:
        print("   - PIXABAY_API_KEY not set in environment. Skipping live API call.")

    # 3. Procedural Fallback Engine
    print(f"\n3. Procedural Fallback Engine (Offline, Zero External API):")
    procedural = ProceduralFallbackProvider(output_dir="data/cache/footage")
    print(f"   - Configured: {procedural.is_configured} (100% offline via FFmpeg)")
    test_out = "data/cache/footage/verify_test_proc.mp4"
    rendered = await procedural.generate_clip(
        target_path=test_out,
        duration=3.0,
        aspect_ratio="16:9",
        theme="technology",
    )
    downloader = AssetDownloader()
    meta = await downloader.validate_media(rendered)
    sha256 = downloader._compute_sha256(rendered)
    print(f"   - Generated: {rendered}")
    print(f"   - Dimensions: {meta['width']}x{meta['height']} @ {meta['duration']}s (codec: {meta['codec']})")
    print(f"   - Content Hash (SHA-256): {sha256[:16]}...")
    print(f"   - Licence: Procedurally Generated (Commercial CC0 Equivalent)")

    # 4. Multi-scene Orchestration Test
    print(f"\n4. Multi-Scene Retrieval & Deduplication Test:")
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
            visual_query="two business partners shaking hands in corporate office",
            visual_intent="business",
            negative_constraints=["cartoons"],
            segmentation_reason=SegmentationReason.SENTENCE_BOUNDARY,
            pacing_status=PacingStatus.VALID,
            timing_source=TimingSource.ASR_ACOUSTIC,
        ),
    ]

    engine = FootageRetrievalEngine()
    result = await engine.retrieve_for_scenes(scenes, aspect_ratio="16:9", job_id="verify_test")
    print(f"   - Total scenes: {result.total_scenes}")
    print(f"   - Unique clips selected: {result.deduplication.unique_clips_selected}")
    print(f"   - Providers queried: {result.providers_queried}")
    print(f"   - Fallback rate: {result.procedural_fallback_rate * 100:.1f}%")
    for clip in result.clips:
        print(f"     * Scene {clip.scene_index} -> Clip {clip.asset_id} ({clip.provider}): {clip.selection_reason}")
        print(f"       Licence: {clip.license.license_name} | Commercial: {clip.license.commercial_use_eligible}")

    print("\n" + "=" * 70)
    print("Verification complete.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
