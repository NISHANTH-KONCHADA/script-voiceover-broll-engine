import asyncio
import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from broll_engine.api.schemas.job import JobStatus
from broll_engine.media.assembler import VideoAssemblyEngine
from broll_engine.models.retrieval import AssetLicense, SelectedClip
from broll_engine.models.scenes import Scene, SceneSegmentationResult, SegmentationReason, PacingStatus, TimingSource
from broll_engine.quality.evaluator import VideoQualityEvaluator
from broll_engine.quality.models import (
    BlackFrameDetectionResult,
    FrozenFrameDetectionResult,
    StreamValidationResult,
    SubtitleValidationResult,
    SyncValidationResult,
    VideoQualityReport,
)
from broll_engine.quality.saliency import VisualSaliencyAnalyzer
from broll_engine.quality.scorer import QualityScorer
from broll_engine.quality.video_inspector import VideoQualityInspector
from broll_engine.repositories.sql import SQLJobRepository
from broll_engine.services.webhook import (
    compute_signature,
    dispatch_webhook,
    verify_signature,
    WebhookDeliveryResult,
)
from broll_engine.speech.asr.base import TranscriptionResult, WordTiming
from broll_engine.storage.memory import InMemoryStorageAdapter
from broll_engine.worker.execution import JobExecutionWorker


def _generate_synthetic_video(output_path: Path, color: str = "blue", duration: float = 1.5, with_audio: bool = True) -> None:
    """Generates a small synthetic mp4 video using ffmpeg."""
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", f"color=c={color}:s=320x240:r=30:d={duration}",
    ]
    if with_audio:
        cmd.extend([
            "-f", "lavfi",
            "-i", f"sine=frequency=440:r=48000:d={duration}",
            "-c:a", "aac",
            "-b:a", "64k",
        ])
    cmd.extend([
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-t", str(duration),
        str(output_path),
    ])
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


# =====================================================================
# 1. Video Inspector: Black & Frozen Frames & Streams
# =====================================================================


@pytest.mark.asyncio
async def test_black_frame_detection_on_black_and_normal_videos(tmp_path: Path):
    inspector = VideoQualityInspector()

    # 1. Non-existent file
    res_none = await inspector.detect_black_frames(str(tmp_path / "non_existent.mp4"))
    assert not res_none.detected
    assert res_none.event_count == 0

    # 2. Pure black video (1.5 seconds)
    black_video = tmp_path / "black.mp4"
    _generate_synthetic_video(black_video, color="black", duration=1.5)
    res_black = await inspector.detect_black_frames(str(black_video), min_duration_seconds=0.2)
    assert res_black.detected
    assert res_black.event_count >= 1
    assert res_black.total_black_duration >= 0.5

    # 3. Normal colorful video
    blue_video = tmp_path / "blue.mp4"
    _generate_synthetic_video(blue_video, color="blue", duration=1.5)
    res_blue = await inspector.detect_black_frames(str(blue_video), min_duration_seconds=0.2)
    assert not res_blue.detected
    assert res_blue.event_count == 0


@pytest.mark.asyncio
async def test_frozen_frame_detection_on_static_video(tmp_path: Path):
    inspector = VideoQualityInspector()

    # Static solid video for 2.5 seconds (freezedetect threshold: 1.0s)
    static_video = tmp_path / "static.mp4"
    _generate_synthetic_video(static_video, color="red", duration=2.5)
    res = await inspector.detect_frozen_frames(str(static_video), min_duration_seconds=1.0)
    assert res.detected
    assert res.event_count >= 1
    assert res.total_frozen_duration >= 1.0


@pytest.mark.asyncio
async def test_stream_validation_and_sync(tmp_path: Path):
    inspector = VideoQualityInspector()

    video_path = tmp_path / "valid.mp4"
    _generate_synthetic_video(video_path, color="green", duration=2.0, with_audio=True)

    # Audio sync
    sync_res = await inspector.validate_audio_sync(str(video_path))
    assert sync_res.is_synchronized
    assert sync_res.drift_seconds <= 0.050

    # Streams validation (expecting 16:9 config will note 320x240 difference, but codecs are h264/aac)
    stream_res = await inspector.validate_streams(str(video_path), expected_aspect="16:9")
    assert stream_res.video_codec == "h264"
    assert stream_res.audio_codec == "aac"
    assert stream_res.pixel_format == "yuv420p"
    assert abs(stream_res.framerate_fps - 30.0) <= 0.5


# =====================================================================
# 2. Subtitle Validation
# =====================================================================


def test_subtitle_validation():
    inspector = VideoQualityInspector()

    valid_srt = """1
00:00:00,000 --> 00:00:02,500
First scene subtitle cue.

2
00:00:02,500 --> 00:00:05,000
Second scene subtitle cue.
"""
    res_valid = inspector.validate_subtitles(valid_srt, video_duration=5.0)
    assert res_valid.valid
    assert res_valid.cue_count == 2
    assert res_valid.timing_anomalies_count == 0

    invalid_srt = """1
00:00:03,000 --> 00:00:01,000
Backwards cue timing.

2
00:00:04,000 --> 00:00:07,500
Cue extending beyond video.
"""
    res_invalid = inspector.validate_subtitles(invalid_srt, video_duration=5.0)
    assert not res_invalid.valid
    assert res_invalid.timing_anomalies_count >= 2


# =====================================================================
# 3. Visual Saliency & Crop Composition
# =====================================================================


@pytest.mark.asyncio
async def test_visual_saliency_and_crop_safety(tmp_path: Path):
    analyzer = VisualSaliencyAnalyzer()

    video_path = tmp_path / "saliency_test.mp4"
    _generate_synthetic_video(video_path, color="cyan", duration=1.0)

    # 16:9 Landscape master
    report_16_9 = await analyzer.evaluate_composition(str(video_path), aspect_ratio="16:9")
    assert report_16_9.is_crop_safe
    assert report_16_9.crop_strategy == "native_fit"
    assert report_16_9.analysis_type == "heuristic_spatial_contrast"

    # 9:16 Vertical crop
    report_9_16 = await analyzer.evaluate_composition(str(video_path), aspect_ratio="9:16")
    assert report_9_16.analysis_type == "heuristic_spatial_contrast"
    assert report_9_16.safe_area_energy_ratio > 0.0

    # Missing file
    report_missing = await analyzer.evaluate_composition(str(tmp_path / "missing.mp4"), aspect_ratio="1:1")
    assert report_missing.is_crop_safe
    assert "not available" in report_missing.recommendation


# =====================================================================
# 4. Quality Scorer & Composite Report
# =====================================================================


def test_quality_scorer_objective_and_heuristic_scoring():
    scorer = QualityScorer()

    mock_scene = Scene(
        id="scene_001",
        index=0,
        start_seconds=0.0,
        end_seconds=3.0,
        duration_seconds=3.0,
        narration_text="Modern renewable solar farm",
        visual_query="solar panels sunny field",
        visual_intent="clean green energy infrastructure",
        pacing_status=PacingStatus.VALID,
        segmentation_reason=SegmentationReason.SENTENCE_BOUNDARY,
        timing_source=TimingSource.ASR_ACOUSTIC,
    )
    mock_clip = SelectedClip(
        scene_id="scene_001",
        scene_index=0,
        asset_id="clip_123",
        provider="pexels",
        creator="Pexels Contributor",
        original_page_url="https://www.pexels.com/video/123/",
        download_url="https://example.com/solar.mp4",
        duration_seconds=5.0,
        relevance_score=4.9,
        selection_reason="Optimal match",
        license=AssetLicense(
            license_name="Pexels License",
            commercial_use_eligible=True,
            attribution_required=False,
            attribution_text="Photo by John on Pexels",
            license_url="https://www.pexels.com/license/",
        ),
    )

    scene_score = scorer.score_scene(scene=mock_scene, clip=mock_clip, used_clip_ids={"clip_123": 1})
    assert scene_score.relevance_score == 4.9
    assert scene_score.composite_scene_score >= 80.0
    assert scene_score.visual_diversity_score == 100.0

    # Overall calculation with perfect objective metrics
    stream_res = StreamValidationResult(
        video_codec="h264",
        audio_codec="aac",
        pixel_format="yuv420p",
        framerate_fps=30.0,
        width=1920,
        height=1080,
        aspect_ratio="16:9",
        is_valid_broadcast_format=True,
        issues=[],
    )
    black_res = BlackFrameDetectionResult(detected=False)
    frozen_res = FrozenFrameDetectionResult(detected=False)
    sync_res = SyncValidationResult(
        video_duration_seconds=3.0,
        audio_duration_seconds=3.0,
        drift_seconds=0.002,
        is_synchronized=True,
        within_tolerance=True,
    )
    sub_res = SubtitleValidationResult(
        total_cues=1,
        has_overlaps=False,
        has_out_of_bounds=False,
        issues=[],
    )

    overall, passed, warnings, failures = scorer.compute_overall_quality(
        scene_scores=[scene_score],
        stream_validation=stream_res,
        black_frames=black_res,
        frozen_frames=frozen_res,
        sync_validation=sync_res,
        subtitle_validation=sub_res,
    )

    assert passed
    assert overall >= 85.0
    assert len(failures) == 0


def test_quality_scorer_flags_black_frames_and_drift_failures():
    scorer = QualityScorer()

    stream_res = StreamValidationResult(
        video_codec="mpeg4",  # Non-standard
        audio_codec="mp3",    # Non-standard
        pixel_format="yuv420p",
        framerate_fps=24.0,
        width=1280,
        height=720,
        aspect_ratio="16:9",
        is_valid_broadcast_format=False,
        issues=["Codec deviation"],
    )
    black_res = BlackFrameDetectionResult(detected=True, total_black_duration=1.2)
    frozen_res = FrozenFrameDetectionResult(detected=True, total_frozen_duration=2.0)
    sync_res = SyncValidationResult(
        video_duration_seconds=5.0,
        audio_duration_seconds=4.8,
        drift_seconds=0.200,
        is_synchronized=False,
        within_tolerance=False,
    )
    sub_res = SubtitleValidationResult(
        total_cues=0,
        has_overlaps=True,
        has_out_of_bounds=True,
        issues=["Missing cues"],
    )

    overall, passed, warnings, failures = scorer.compute_overall_quality(
        scene_scores=[],
        stream_validation=stream_res,
        black_frames=black_res,
        frozen_frames=frozen_res,
        sync_validation=sync_res,
        subtitle_validation=sub_res,
    )

    assert not passed
    assert overall < 50.0
    assert any("Black frames" in f for f in failures)
    assert any("frozen" in w.lower() for w in warnings)
    assert any("drift" in f for f in failures)


# =====================================================================
# 5. Webhook Delivery: HMAC Signature & Retry Resilience
# =====================================================================


def test_webhook_hmac_signature_generation_and_verification():
    secret = "super_secret_signing_key_456"
    payload = {"job_id": "broll_test_123", "status": "SUCCEEDED", "progress": 100}
    payload_bytes = json.dumps(payload).encode("utf-8")

    sig = compute_signature(payload_bytes, secret)
    assert len(sig) == 64  # SHA-256 hex string

    header = f"sha256={sig}"
    assert verify_signature(payload_bytes, header, secret)
    assert not verify_signature(payload_bytes, header, "wrong_secret")
    assert not verify_signature(payload_bytes, "invalid_header_format", secret)


@pytest.mark.asyncio
async def test_webhook_delivery_success_with_signature():
    callback_url = "https://client-api.example.com/webhook"
    secret = "test_webhook_secret"
    payload = {"job_id": "broll_abc", "status": "SUCCEEDED"}

    captured_request = {}

    async def mock_post(self, url, content=None, headers=None, **kwargs):
        captured_request["url"] = url
        captured_request["content"] = content
        captured_request["headers"] = headers
        return httpx.Response(200, json={"received": True}, request=httpx.Request("POST", url))

    with patch.object(httpx.AsyncClient, "post", new=mock_post):
        res = await dispatch_webhook(
            callback_url=callback_url,
            payload=payload,
            secret=secret,
            max_retries=2,
            initial_backoff=0.01,
        )

        assert res.status == "delivered"
        assert res.attempts == 1
        assert res.status_code == 200

        sig_header = captured_request["headers"].get("X-IncuBrix-Signature")
        assert sig_header and sig_header.startswith("sha256=")
        assert verify_signature(captured_request["content"], sig_header, secret)


@pytest.mark.asyncio
async def test_webhook_retries_and_recovers_on_500():
    callback_url = "https://client-api.example.com/webhook-flaky"
    call_count = 0

    async def flaky_post(self, url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(503, text="Service Unavailable", request=httpx.Request("POST", url))
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

    with patch.object(httpx.AsyncClient, "post", new=flaky_post):
        res = await dispatch_webhook(
            callback_url=callback_url,
            payload={"job_id": "broll_retry"},
            max_retries=3,
            initial_backoff=0.01,
        )

        assert res.status == "delivered"
        assert res.attempts == 2
        assert res.status_code == 200


@pytest.mark.asyncio
async def test_webhook_fails_gracefully_on_persistent_5xx_without_raising():
    callback_url = "https://client-api.example.com/webhook-down"

    async def fail_post(self, url, **kwargs):
        return httpx.Response(500, text="Internal Server Error", request=httpx.Request("POST", url))

    with patch.object(httpx.AsyncClient, "post", new=fail_post):
        res = await dispatch_webhook(
            callback_url=callback_url,
            payload={"job_id": "broll_fail"},
            max_retries=2,
            initial_backoff=0.01,
        )

        assert res.status == "failed"
        assert res.attempts == 2
        assert res.status_code == 500


@pytest.mark.asyncio
async def test_webhook_permanent_error_on_404_no_retry():
    callback_url = "https://client-api.example.com/webhook-notfound"

    async def not_found_post(self, url, **kwargs):
        return httpx.Response(404, text="Not Found", request=httpx.Request("POST", url))

    with patch.object(httpx.AsyncClient, "post", new=not_found_post):
        res = await dispatch_webhook(
            callback_url=callback_url,
            payload={"job_id": "broll_404"},
            max_retries=3,
            initial_backoff=0.01,
        )

        assert res.status == "permanent_error"
        assert res.attempts == 1  # 4xx is non-retryable
        assert res.status_code == 404


# =====================================================================
# 6. Worker End-to-End Pipeline with Quality Assessment & Webhook
# =====================================================================


@pytest.mark.asyncio
async def test_worker_end_to_end_includes_quality_report_and_webhook(
    test_repo: SQLJobRepository,
    test_storage: InMemoryStorageAdapter,
):
    repository = test_repo
    storage = test_storage

    # Create dummy job in repository
    job_id = "broll_phase6_test"
    await repository.create_job(
        job_id=job_id,
        idempotency_key="key_phase6",
        request_payload={
            "script": "Clean energy drives tomorrow's sustainable cities.",
            "callback_url": "https://webhook.site/test-target",
        },
    )

    worker = JobExecutionWorker(
        repository=repository,
        storage=storage,
        step_delay_seconds=0.0,
    )

    callback_called = False

    async def mock_dispatch(url, payload, secret=None, **kwargs):
        nonlocal callback_called
        callback_called = True
        return WebhookDeliveryResult(
            status="delivered",
            attempts=1,
            status_code=200,
            callback_url=url,
            signature="mock_sig",
        )

    with patch("broll_engine.worker.execution.dispatch_webhook", side_effect=mock_dispatch):
        await worker.execute_job(
            job_id=job_id,
            request_payload={
                "script": "Clean energy drives tomorrow's sustainable cities.",
                "callback_url": "https://webhook.site/test-target",
            },
        )

    job_rec = await repository.get_job(job_id)
    assert job_rec is not None
    assert job_rec.status == JobStatus.SUCCEEDED
    assert job_rec.progress == 100

    # Verify quality report artifact is present in outputs
    assert "quality_report" in job_rec.outputs
    quality_report_url = job_rec.outputs["quality_report"]
    assert "quality_report.json" in quality_report_url

    # Check content of quality_report.json in storage
    quality_bytes = await storage.download_bytes(f"jobs/{job_id}/quality_report.json")
    quality_data = json.loads(quality_bytes.decode("utf-8"))
    assert "overall_quality_score" in quality_data
    assert "objective_metrics" in quality_data
    assert "heuristic_metrics" in quality_data
    assert "saliency_reports" in quality_data

    # Check manifest.json contains quality_assessment
    manifest_bytes = await storage.download_bytes(f"jobs/{job_id}/manifest.json")
    manifest_data = json.loads(manifest_bytes.decode("utf-8"))
    assert "quality_assessment" in manifest_data
    assert manifest_data["quality_assessment"]["overall_quality_score"] == quality_data["overall_quality_score"]

    # Verify webhook dispatch was triggered
    assert callback_called
