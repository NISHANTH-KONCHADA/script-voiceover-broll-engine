"""Automated test suite for Phase 5: Audio Normalization, Subtitles & Multi-Aspect Video Assembly."""

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
import pytest
import soundfile as sf
import numpy as np

from broll_engine.media.audio import AudioNormalizer
from broll_engine.media.scaler import VideoScaler, ASPECT_RATIO_CONFIGS
from broll_engine.media.subtitles import (
    SubtitleGenerator,
    format_ass_timestamp,
    format_srt_timestamp,
)
from broll_engine.media.assembler import VideoAssemblyEngine
from broll_engine.models.retrieval import AssetLicense, SelectedClip
from broll_engine.models.scenes import (
    PacingStatus,
    Scene,
    SegmentationReason,
    TimingSource,
)
from broll_engine.retrieval.procedural import ProceduralFallbackProvider


@pytest.fixture
def temp_media_dir():
    d = tempfile.mkdtemp(prefix="broll_test_media_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_wav_file(temp_media_dir):
    """Generates a clean 3.0s stereo sine wave audio file at 44.1kHz."""
    path = os.path.join(temp_media_dir, "sample.wav")
    sr = 44100
    duration = 3.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # 440 Hz sine tone with harmonic
    tone = 0.5 * np.sin(2 * np.pi * 440 * t) + 0.2 * np.sin(2 * np.pi * 880 * t)
    stereo = np.column_stack([tone, tone])
    sf.write(path, stereo, sr)
    return path


def test_srt_and_ass_timestamp_formatting():
    # Test SRT timestamp (HH:MM:SS,mmm)
    assert format_srt_timestamp(0.0) == "00:00:00,000"
    assert format_srt_timestamp(1.234) == "00:00:01,234"
    assert format_srt_timestamp(65.500) == "00:01:05,500"
    assert format_srt_timestamp(3661.050) == "01:01:01,050"

    # Test ASS timestamp (H:MM:SS.cc)
    assert format_ass_timestamp(0.0) == "0:00:00.00"
    assert format_ass_timestamp(1.234) == "0:00:01.23"
    assert format_ass_timestamp(65.500) == "0:01:05.50"


def test_subtitle_generator_content():
    generator = SubtitleGenerator()
    scenes = [
        Scene(
            id="s1",
            index=0,
            start_seconds=0.0,
            end_seconds=2.5,
            duration_seconds=2.5,
            narration_text="Welcome to IncuBrix video engine.",
            visual_query="technology",
            visual_intent="technology",
            segmentation_reason=SegmentationReason.SENTENCE_BOUNDARY,
            pacing_status=PacingStatus.VALID,
            timing_source=TimingSource.ASR_ACOUSTIC,
        ),
        Scene(
            id="s2",
            index=1,
            start_seconds=2.5,
            end_seconds=5.0,
            duration_seconds=2.5,
            narration_text="Broadcast-ready AI video assembly.",
            visual_query="business",
            visual_intent="business",
            segmentation_reason=SegmentationReason.SENTENCE_BOUNDARY,
            pacing_status=PacingStatus.VALID,
            timing_source=TimingSource.ASR_ACOUSTIC,
        ),
    ]

    srt = generator.generate_srt_from_scenes(scenes)
    assert "1\n00:00:00,000 --> 00:00:02,500\nWelcome to IncuBrix video engine." in srt
    assert "2\n00:00:02,500 --> 00:00:05,000\nBroadcast-ready AI video assembly." in srt

    ass = generator.generate_ass_content(scenes)
    assert "[Script Info]" in ass
    assert "[V4+ Styles]" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:02.50,Default,,0,0,0,,Welcome to IncuBrix video engine." in ass


def test_video_scaler_dimensions_and_filter():
    scaler = VideoScaler()
    w16, h16 = scaler.get_dimensions("16:9")
    assert (w16, h16) == (1920, 1080)

    w9, h9 = scaler.get_dimensions("9:16")
    assert (w9, h9) == (1080, 1920)

    w1, h1 = scaler.get_dimensions("1:1")
    assert (w1, h1) == (1080, 1080)

    f16 = scaler.build_scale_crop_filter("16:9", fps=30)
    assert "scale=w=1920:h=1080" in f16
    assert "crop=1920:1080" in f16
    assert "format=yuv420p" in f16


@pytest.mark.asyncio
async def test_audio_normalizer_ebu_r128(sample_wav_file, temp_media_dir):
    normalizer = AudioNormalizer(target_lufs=-16.0, sample_rate=48000)
    out_aac = os.path.join(temp_media_dir, "normalized.aac")

    res = await normalizer.normalize_audio(sample_wav_file, out_aac)
    assert os.path.exists(out_aac)
    assert res["sample_rate"] == 48000
    assert res["channels"] == 2
    assert res["duration_seconds"] > 2.8


@pytest.mark.asyncio
async def test_render_scene_clip_and_multi_aspect(temp_media_dir):
    procedural = ProceduralFallbackProvider(output_dir=temp_media_dir)
    source_clip = os.path.join(temp_media_dir, "source_proc.mp4")
    await procedural.generate_clip(source_clip, duration=4.0, aspect_ratio="16:9", theme="technology")

    engine = VideoAssemblyEngine()

    # Render scene to 9:16 vertical
    target_vertical = os.path.join(temp_media_dir, "scene_vertical.mp4")
    out_file = await engine.render_scene_clip(
        input_media_path=source_clip,
        target_path=target_vertical,
        duration=2.0,
        aspect_ratio="9:16",
    )

    probe = await engine.probe_video(out_file, require_audio=False)
    assert probe["width"] == 1080
    assert probe["height"] == 1920
    assert probe["video_codec"] == "h264"
    assert probe["pixel_format"] == "yuv420p"
    assert abs(probe["duration_seconds"] - 2.0) <= 0.10


@pytest.mark.asyncio
async def test_multi_aspect_assembly_end_to_end(sample_wav_file, temp_media_dir):
    """Verifies end-to-end assembly producing 16:9, 9:16 and 1:1 broadcast MP4s with zero drift."""
    procedural = ProceduralFallbackProvider(output_dir=temp_media_dir)
    clip1_path = os.path.join(temp_media_dir, "clip1.mp4")
    clip2_path = os.path.join(temp_media_dir, "clip2.mp4")
    await procedural.generate_clip(clip1_path, duration=3.0, aspect_ratio="16:9", theme="technology")
    await procedural.generate_clip(clip2_path, duration=3.0, aspect_ratio="16:9", theme="business")

    scenes = [
        Scene(
            id="scene_001",
            index=0,
            start_seconds=0.0,
            end_seconds=1.5,
            duration_seconds=1.5,
            narration_text="Cloud computing transforms modern infrastructure.",
            visual_query="technology",
            visual_intent="technology",
            segmentation_reason=SegmentationReason.SENTENCE_BOUNDARY,
            pacing_status=PacingStatus.VALID,
            timing_source=TimingSource.ASR_ACOUSTIC,
        ),
        Scene(
            id="scene_002",
            index=1,
            start_seconds=1.5,
            end_seconds=3.0,
            duration_seconds=1.5,
            narration_text="Enterprise security and scalable execution.",
            visual_query="business",
            visual_intent="business",
            segmentation_reason=SegmentationReason.SENTENCE_BOUNDARY,
            pacing_status=PacingStatus.VALID,
            timing_source=TimingSource.ASR_ACOUSTIC,
        ),
    ]

    license_meta = AssetLicense(
        license_name="Procedurally Generated (Commercial CC0 Equivalent)",
        license_url="https://incubrix.internal/license",
        commercial_use_eligible=True,
        attribution_text="IncuBrix",
    )

    clips = [
        SelectedClip(
            scene_id="scene_001",
            scene_index=0,
            asset_id="proc_clip_1",
            provider="procedural",
            relevance_score=4.5,
            selection_reason="Matched",
            license=license_meta,
            creator="IncuBrix",
            original_page_url="https://incubrix.internal",
            download_url=f"file://{clip1_path}",
            local_path=clip1_path,
            duration_seconds=1.5,
        ),
        SelectedClip(
            scene_id="scene_002",
            scene_index=1,
            asset_id="proc_clip_2",
            provider="procedural",
            relevance_score=4.5,
            selection_reason="Matched",
            license=license_meta,
            creator="IncuBrix",
            original_page_url="https://incubrix.internal",
            download_url=f"file://{clip2_path}",
            local_path=clip2_path,
            duration_seconds=1.5,
        ),
    ]

    engine = VideoAssemblyEngine()
    result = await engine.assemble_multi_aspect_videos(
        scenes=scenes,
        clips=clips,
        master_audio_path=sample_wav_file,
        output_dir=os.path.join(temp_media_dir, "outputs"),
        aspect_ratios=["16:9", "9:16", "1:1"],
        burn_in_captions=True,
        job_id="test_p5_assembly",
    )

    assert "16:9" in result["videos"]
    assert "9:16" in result["videos"]
    assert "1:1" in result["videos"]
    assert os.path.exists(result["captions_srt_path"])

    # Probe 16:9 landscape variant
    p16 = result["media_probes"]["16:9"]
    assert p16["width"] == 1920
    assert p16["height"] == 1080
    assert p16["video_codec"] == "h264"
    assert p16["audio_codec"] == "aac"
    assert p16["drift_seconds"] <= 0.05  # Zero audio drift

    # Probe 9:16 vertical variant
    p9 = result["media_probes"]["9:16"]
    assert p9["width"] == 1080
    assert p9["height"] == 1920
    assert p9["video_codec"] == "h264"

    # Probe 1:1 square variant
    p1 = result["media_probes"]["1:1"]
    assert p1["width"] == 1080
    assert p1["height"] == 1080
    assert p1["video_codec"] == "h264"
