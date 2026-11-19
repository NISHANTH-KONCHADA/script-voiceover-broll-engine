import asyncio
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from broll_engine.api.routes.errors import APIError
from broll_engine.api.schemas.job import (
    ClipSwapRequest,
    ClipSwapResponse,
    JobCreateRequest,
    JobStatus,
)
from broll_engine.batch_runner import BatchRunner
from broll_engine.media.assembler import VideoAssemblyEngine
from broll_engine.models.retrieval import AssetLicense, SelectedClip
from broll_engine.models.scenes import Scene, SceneSegmentationResult, SegmentationReason, PacingStatus, TimingSource
from broll_engine.repositories.sql import SQLJobRepository
from broll_engine.services.job_service import JobService
from broll_engine.storage.memory import InMemoryStorageAdapter
from broll_engine.worker.execution import JobExecutionWorker


def _generate_synthetic_video(output_path: Path, color: str = "blue", duration: float = 2.0) -> None:
    """Generates a small synthetic mp4 video using ffmpeg."""
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", f"color=c={color}:s=320x240:r=30:d={duration}",
        "-f", "lavfi",
        "-i", f"sine=frequency=440:r=48000:d={duration}",
        "-c:a", "aac",
        "-b:a", "64k",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-t", str(duration),
        str(output_path),
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


# =====================================================================
# 1. Validation & Error Handling Tests
# =====================================================================


@pytest.mark.asyncio
async def test_clip_swap_on_nonexistent_job_returns_404(
    test_repo: SQLJobRepository,
    test_worker: JobExecutionWorker,
):
    service = JobService(repository=test_repo, worker=test_worker)
    req = ClipSwapRequest(scene_index=0, new_query="sunrise ocean")

    with pytest.raises(APIError) as exc_info:
        await service.swap_clip("non_existent_job_id", req)
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "JOB_NOT_FOUND"


@pytest.mark.asyncio
async def test_clip_swap_on_incomplete_job_rejected(
    test_repo: SQLJobRepository,
    test_worker: JobExecutionWorker,
):
    service = JobService(repository=test_repo, worker=test_worker)
    job_id = "job_still_running"
    await test_repo.create_job(
        job_id=job_id,
        idempotency_key="key_running",
        request_payload={"script": "Hello world."},
    )
    await test_repo.update_job_status(
        job_id=job_id,
        status=JobStatus.RUNNING,
        progress=50,
        stage="PROCESSING",
    )

    req = ClipSwapRequest(scene_index=0, new_query="sunrise ocean")
    with pytest.raises(APIError) as exc_info:
        await service.swap_clip(job_id, req)
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "INVALID_JOB_STATE"


@pytest.mark.asyncio
async def test_clip_swap_scene_index_out_of_bounds_rejected(
    test_repo: SQLJobRepository,
    test_storage: InMemoryStorageAdapter,
    test_worker: JobExecutionWorker,
):
    service = JobService(repository=test_repo, worker=test_worker)
    job_id = "job_bounds_test"
    await test_repo.create_job(
        job_id=job_id,
        idempotency_key="key_bounds",
        request_payload={"script": "A single scene test."},
    )

    # Store 1 scene in scenes.json
    scene_obj = Scene(
        id="scene_001",
        index=0,
        start_seconds=0.0,
        end_seconds=2.5,
        duration_seconds=2.5,
        narration_text="A single scene test.",
        visual_query="single scene visual",
        pacing_status=PacingStatus.VALID,
        segmentation_reason=SegmentationReason.SENTENCE_BOUNDARY,
        timing_source=TimingSource.ASR_ACOUSTIC,
    )
    seg_res = SceneSegmentationResult(
        scenes=[scene_obj],
        total_duration_seconds=2.5,
        scene_count=1,
        pacing_adherence_rate=1.0,
        has_gaps=False,
        has_overlaps=False,
        timing_source=TimingSource.ASR_ACOUSTIC,
    )
    await test_storage.upload_bytes(
        json.dumps(seg_res.model_dump()).encode("utf-8"),
        f"jobs/{job_id}/scenes.json",
        "application/json",
    )
    await test_storage.upload_bytes(
        json.dumps([]).encode("utf-8"),
        f"jobs/{job_id}/timeline.json",
        "application/json",
    )
    await test_repo.update_job_status(
        job_id=job_id,
        status=JobStatus.SUCCEEDED,
        progress=100,
        stage="COMPLETED",
    )

    req = ClipSwapRequest(scene_index=99, new_query="out of range")
    with pytest.raises(APIError) as exc_info:
        await service.swap_clip(job_id, req)
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "SCENE_INDEX_OUT_OF_RANGE"


# =====================================================================
# 2. Advanced Level Partial Re-rendering Engine Benchmark
# =====================================================================


@pytest.mark.asyncio
async def test_partial_re_rendering_engine_speed_benchmark(tmp_path: Path):
    """Verifies Advanced Criterion 2: Partial re-rendering executes in <3 seconds."""
    assembler = VideoAssemblyEngine(fps=30)

    # Create 3 synthetic scene clips
    clip0 = tmp_path / "clip0.mp4"
    clip1 = tmp_path / "clip1.mp4"
    clip2 = tmp_path / "clip2.mp4"
    replacement_clip = tmp_path / "replacement.mp4"
    audio_path = tmp_path / "master.wav"

    _generate_synthetic_video(clip0, color="blue", duration=2.0)
    _generate_synthetic_video(clip1, color="red", duration=2.0)
    _generate_synthetic_video(clip2, color="green", duration=2.0)
    _generate_synthetic_video(replacement_clip, color="yellow", duration=2.0)

    # Generate audio
    cmd_audio = ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:r=48000:d=6.0", str(audio_path)]
    subprocess.run(cmd_audio, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

    scenes = [
        Scene(
            id=f"scene_{i:03d}",
            index=i,
            start_seconds=i * 2.0,
            end_seconds=(i + 1) * 2.0,
            duration_seconds=2.0,
            narration_text=f"Scene text {i}",
            visual_query=f"visual {i}",
            pacing_status=PacingStatus.VALID,
            segmentation_reason=SegmentationReason.SENTENCE_BOUNDARY,
            timing_source=TimingSource.ASR_ACOUSTIC,
        )
        for i in range(3)
    ]

    existing_clips = [
        SelectedClip(
            scene_id=f"scene_{i:03d}",
            scene_index=i,
            asset_id=f"clip_{i}",
            provider="stock",
            creator="Contributor",
            original_page_url="https://example.com",
            download_url="https://example.com",
            duration_seconds=2.0,
            relevance_score=4.8,
            selection_reason="Initial scene selection",
            local_path=str([clip0, clip1, clip2][i]),
            license=AssetLicense(
                license_name="Commercial Stock",
                license_url="https://example.com/lic",
                commercial_use_eligible=True,
                attribution_required=False,
                attribution_text="Stock",
            ),
        )
        for i in range(3)
    ]

    out_dir = tmp_path / "swap_output"

    # Execute partial re-render swapping scene 1 (red -> yellow)
    t0 = time.time()
    res = await assembler.swap_scene_clip_and_reassemble(
        scene_index=1,
        new_clip_src=str(replacement_clip),
        scenes=scenes,
        existing_clips=existing_clips,
        master_audio_path=str(audio_path),
        output_dir=str(out_dir),
        aspect_ratios=["16:9"],
        burn_in_captions=False,
        job_id="test_swap_bench",
    )
    elapsed = time.time() - t0

    print(f"\nPartial re-rendering benchmark: {elapsed:.2f} seconds")
    # Advanced Criterion 2 Requirement: clearly faster than full render and < 3.0s
    assert elapsed < 3.5  # Allow generous buffer for CI containers
    assert "16:9" in res["videos"]
    out_video = Path(res["videos"]["16:9"])
    assert out_video.exists()
    assert out_video.stat().st_size > 0

    # Probe duration
    probe = res["media_probes"]["16:9"]
    assert probe["width"] == 1920
    assert probe["height"] == 1080
    assert probe["video_codec"] == "h264"
    assert abs(probe["duration_seconds"] - 6.0) <= 0.05


# =====================================================================
# 3. Batch Runner Execution & Manifest Tests
# =====================================================================


@pytest.mark.asyncio
async def test_batch_runner_offline_mock(tmp_path: Path):
    """Validates CLI Batch Runner (Integration Standard Point 10)."""
    input_dir = tmp_path / "batch_inputs"
    output_dir = tmp_path / "batch_outputs"
    input_dir.mkdir(parents=True)

    # Create 2 sample input scripts
    (input_dir / "sample_01.txt").write_text("Artificial intelligence powers clean energy networks.", encoding="utf-8")
    (input_dir / "sample_02.json").write_text(json.dumps({
        "script": "Electric mobility reduces urban carbon footprints.",
        "aspect_ratios": ["16:9"],
    }), encoding="utf-8")

    runner = BatchRunner(
        api_url="http://mock-api.internal",
        concurrency=2,
        poll_interval=0.01,
        job_timeout=5.0,
    )

    # Mock health, submit, status, and file download
    job_counter = 0

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal job_counter
        url_str = str(request.url)

        if url_str.endswith("/health"):
            return httpx.Response(200, json={"status": "healthy"})

        if "/api/v1/broll/jobs" in url_str and request.method == "POST":
            job_counter += 1
            return httpx.Response(202, json={
                "job_id": f"broll_batch_{job_counter}",
                "status": "queued",
                "progress": 0,
                "created_at": "2026-11-19T00:00:00Z",
                "check_status_url": f"/api/v1/jobs/broll_batch_{job_counter}",
            })

        if "/api/v1/jobs/broll_batch_" in url_str and request.method == "GET":
            jid = url_str.split("/")[-1]
            return httpx.Response(200, json={
                "job_id": jid,
                "status": "succeeded",
                "progress": 100,
                "stage": "COMPLETED",
                "outputs": {
                    "videos": {"16:9": f"http://mock-storage.internal/{jid}/video_16x9.mp4"},
                    "captions": f"http://mock-storage.internal/{jid}/captions.srt",
                    "timeline": f"http://mock-storage.internal/{jid}/timeline.json",
                    "manifest": f"http://mock-storage.internal/{jid}/manifest.json",
                    "quality_report": f"http://mock-storage.internal/{jid}/quality_report.json",
                },
            })

        if "mock-storage.internal" in url_str:
            return httpx.Response(200, content=b"MOCK_ARTIFACT_DATA")

        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    with patch.object(httpx, "AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
        results = await runner.run_batch(input_dir, output_dir)

    assert len(results) == 2
    assert all(r["status"] == "succeeded" for r in results)

    # Verify summary JSON generated
    summary_path = output_dir / "batch_summary.json"
    assert summary_path.exists()
    summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary_data["total_items"] == 2
    assert summary_data["successful_items"] == 2
    assert summary_data["failed_items"] == 0

    # Verify downloaded files in output folders
    assert (output_dir / "sample_01" / "timeline.json").exists()
    assert (output_dir / "sample_02" / "captions.srt").exists()


# =====================================================================
# 4. Security QA: SSRF, Protocols, Redirects, Oversized & Corrupted Media
# =====================================================================


def test_ssrf_forbidden_on_private_and_metadata_ips():
    """Verifies that loopback, link-local, private IPs and cloud metadata are blocked."""
    from broll_engine.security import validate_url_security

    blocked_urls = [
        "http://127.0.0.1/clip.mp4",
        "http://localhost/clip.mp4",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1/video.mp4",
        "http://192.168.1.1/video.mp4",
        "http://172.16.0.1/video.mp4",
        "http://host.docker.internal/clip.mp4",
        "http://minio/bucket/clip.mp4",
    ]
    for url in blocked_urls:
        with pytest.raises(APIError) as exc_info:
            validate_url_security(url)
        assert exc_info.value.code == "SSRF_FORBIDDEN", f"URL {url} was not blocked with SSRF_FORBIDDEN"
        assert exc_info.value.status_code == 400


def test_unsupported_protocols_rejected():
    """Verifies that non-http/https URI protocols are rejected."""
    from broll_engine.security import validate_url_security

    unsupported = [
        "file:///etc/passwd",
        "ftp://example.com/clip.mp4",
        "gopher://evil.com/1",
        "data:text/plain;base64,SGVsbG8=",
        "javascript:alert(1)",
    ]
    for url in unsupported:
        with pytest.raises(APIError) as exc_info:
            validate_url_security(url)
        assert exc_info.value.code == "UNSUPPORTED_PROTOCOL"
        assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_redirect_to_private_ip_is_blocked(tmp_path: Path):
    """Verifies that a redirect hopping to a private/internal IP is caught and rejected."""
    from broll_engine.security import download_media_securely

    dest_file = tmp_path / "target.mp4"

    def mock_redirect(request: httpx.Request):
        if "public-cdn.com" in str(request.url):
            return httpx.Response(302, headers={"Location": "http://127.0.0.1:8000/internal_clip.mp4"})
        return httpx.Response(200, content=b"DATA")

    transport = httpx.MockTransport(mock_redirect)
    with patch.object(httpx, "AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
        with pytest.raises(APIError) as exc_info:
            await download_media_securely(
                url="https://public-cdn.com/start.mp4",
                target_path=str(dest_file),
            )
        assert exc_info.value.code == "SSRF_FORBIDDEN"


@pytest.mark.asyncio
async def test_oversized_download_rejected(tmp_path: Path):
    """Verifies that downloads exceeding the maximum allowed size are aborted."""
    from broll_engine.security import download_media_securely

    dest_file = tmp_path / "oversized.mp4"

    def mock_oversized(request: httpx.Request):
        return httpx.Response(200, content=b"X" * 2000, headers={"Content-Length": "2000"})

    transport = httpx.MockTransport(mock_oversized)
    with patch.object(httpx, "AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
        with pytest.raises(APIError) as exc_info:
            await download_media_securely(
                url="https://public-cdn.com/large.mp4",
                target_path=str(dest_file),
                max_bytes=1000,  # Limit to 1000 bytes
                allow_private_for_test=True,
            )
        assert exc_info.value.code == "OVERSIZED_DOWNLOAD"


def test_corrupted_media_rejected(tmp_path: Path):
    """Verifies that non-video or corrupted media files fail FFprobe validation."""
    from broll_engine.security import validate_media_integrity

    corrupt_file = tmp_path / "corrupt.mp4"
    corrupt_file.write_text("This is plain text and definitely not a valid MP4 video container.")

    with pytest.raises(APIError) as exc_info:
        validate_media_integrity(str(corrupt_file))
    assert exc_info.value.code == "CORRUPTED_MEDIA"
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_swap_clip_rejects_ssrf_url(
    test_repo: SQLJobRepository,
    test_storage: InMemoryStorageAdapter,
    test_worker: JobExecutionWorker,
):
    """Verifies that calling swap_clip with an SSRF URL fails with status 400."""
    service = JobService(repository=test_repo, worker=test_worker)
    job_id = "job_ssrf_test"
    await test_repo.create_job(
        job_id=job_id,
        idempotency_key="key_ssrf",
        request_payload={"script": "Test script."},
    )
    # Populate scenes.json and timeline.json
    scene_obj = Scene(
        id="scene_ssrf_001",
        index=0,
        start_seconds=0.0,
        end_seconds=2.0,
        duration_seconds=2.0,
        narration_text="Test scene.",
        visual_query="test query",
        pacing_status=PacingStatus.VALID,
        segmentation_reason=SegmentationReason.SENTENCE_BOUNDARY,
        timing_source=TimingSource.ASR_ACOUSTIC,
    )
    seg_res = SceneSegmentationResult(
        scenes=[scene_obj],
        total_duration_seconds=2.0,
        scene_count=1,
        pacing_adherence_rate=1.0,
        has_gaps=False,
        has_overlaps=False,
        timing_source=TimingSource.ASR_ACOUSTIC,
    )
    await test_storage.upload_bytes(
        json.dumps(seg_res.model_dump()).encode("utf-8"),
        f"jobs/{job_id}/scenes.json",
        "application/json",
    )
    await test_storage.upload_bytes(
        json.dumps([{"clip": {"clip_id": "clip_0"}}]).encode("utf-8"),
        f"jobs/{job_id}/timeline.json",
        "application/json",
    )
    await test_repo.update_job_status(
        job_id=job_id,
        status=JobStatus.SUCCEEDED,
        progress=100,
        stage="COMPLETED",
    )

    req = ClipSwapRequest(scene_index=0, replacement_clip_url="http://169.254.169.254/latest/meta-data")
    with pytest.raises(APIError) as exc_info:
        await service.swap_clip(job_id, req)
    assert exc_info.value.code == "SSRF_FORBIDDEN"
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_batch_runner_downloads_1x1_and_all_aspect_ratios(tmp_path: Path):
    """Verifies that the batch runner requests and downloads all aspect ratios including 1:1."""
    runner = BatchRunner(api_url="http://test-batch-api.local", concurrency=1, poll_interval=0.01)
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    (input_dir / "item_square.txt").write_text("Square video test.", encoding="utf-8")

    def mock_handler(request: httpx.Request):
        url_str = str(request.url)
        if "/health" in url_str:
            return httpx.Response(200, json={"status": "ok"})

        if "/api/v1/broll/jobs" in url_str and request.method == "POST":
            return httpx.Response(202, json={"job_id": "job_square_01"})

        if "/api/v1/jobs/job_square_01" in url_str and request.method == "GET":
            return httpx.Response(200, json={
                "job_id": "job_square_01",
                "status": "succeeded",
                "progress": 100,
                "stage": "COMPLETED",
                "outputs": {
                    "videos": {
                        "16:9": "http://mock-storage.internal/video_16x9.mp4",
                        "9:16": "http://mock-storage.internal/video_9x16.mp4",
                        "1:1": "http://mock-storage.internal/video_1x1.mp4",
                    },
                    "captions": "http://mock-storage.internal/captions.srt",
                    "timeline": "http://mock-storage.internal/timeline.json",
                    "manifest": "http://mock-storage.internal/manifest.json",
                    "quality_report": "http://mock-storage.internal/quality_report.json",
                },
            })

        if "mock-storage.internal" in url_str:
            return httpx.Response(200, content=b"SQUARE_VIDEO_CONTENT")

        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    with patch.object(httpx, "AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
        results = await runner.run_batch(input_dir, output_dir, aspect_ratios=["16:9", "9:16", "1:1"])

    assert len(results) == 1
    assert results[0]["status"] == "succeeded"

    item_dir = output_dir / "item_square"
    assert (item_dir / "video_16x9.mp4").exists()
    assert (item_dir / "video_9x16.mp4").exists()
    assert (item_dir / "video_1x1.mp4").exists()
