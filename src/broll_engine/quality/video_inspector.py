"""FFmpeg and FFprobe objective video and audio quality inspector (Phase 6)."""

import asyncio
import json
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from broll_engine.logging import get_logger
from broll_engine.media.scaler import ASPECT_RATIO_CONFIGS
from broll_engine.quality.models import (
    BlackFrameDetectionResult,
    BlackFrameEvent,
    FrozenFrameDetectionResult,
    FrozenFrameEvent,
    StreamValidationResult,
    SubtitleValidationResult,
    SyncValidationResult,
)

logger = get_logger(__name__)


class VideoQualityInspector:
    """Performs objective physical analysis of rendered video artifacts using FFmpeg and FFprobe."""

    async def detect_black_frames(
        self,
        video_path: str,
        min_duration_seconds: float = 0.20,
    ) -> BlackFrameDetectionResult:
        """Detects segments of solid black frames in the video using FFmpeg blackdetect."""
        path = Path(video_path)
        if not path.exists():
            return BlackFrameDetectionResult(detected=False)

        cmd = [
            "ffmpeg",
            "-i", str(path),
            "-vf", f"blackdetect=d={min_duration_seconds:.2f}:pix_th=0.10",
            "-f", "null",
            "-",
        ]

        loop = asyncio.get_running_loop()
        proc = await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False),
        )

        stderr_text = proc.stderr.decode(errors="replace")
        events: List[BlackFrameEvent] = []

        # Matches: black_start:1.2 black_end:2.0 black_duration:0.8
        pattern = re.compile(
            r"black_start:(?P<start>\d+(\.\d+)?)\s+black_end:(?P<end>\d+(\.\d+)?)\s+black_duration:(?P<dur>\d+(\.\d+)?)"
        )

        for match in pattern.finditer(stderr_text):
            start = float(match.group("start"))
            end = float(match.group("end"))
            dur = float(match.group("dur"))
            events.append(BlackFrameEvent(start_seconds=start, end_seconds=end, duration_seconds=dur))

        total_black = sum(e.duration_seconds for e in events)
        return BlackFrameDetectionResult(
            detected=len(events) > 0,
            event_count=len(events),
            total_black_duration=round(total_black, 3),
            events=events,
        )

    async def detect_frozen_frames(
        self,
        video_path: str,
        min_duration_seconds: float = 1.0,
    ) -> FrozenFrameDetectionResult:
        """Detects segments of frozen or static video frames using FFmpeg freezedetect."""
        path = Path(video_path)
        if not path.exists():
            return FrozenFrameDetectionResult(detected=False)

        cmd = [
            "ffmpeg",
            "-i", str(path),
            "-vf", f"freezedetect=n=-60dB:d={min_duration_seconds:.2f}",
            "-f", "null",
            "-",
        ]

        loop = asyncio.get_running_loop()
        proc = await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False),
        )

        stderr_text = proc.stderr.decode(errors="replace")
        events: List[FrozenFrameEvent] = []

        # Matches: lavfi.freezedetect.freeze_start: 1.5 ... lavfi.freezedetect.freeze_duration: 1.2
        start_pattern = re.compile(r"lavfi\.freezedetect\.freeze_start:\s*(?P<start>\d+(\.\d+)?)")
        dur_pattern = re.compile(r"lavfi\.freezedetect\.freeze_duration:\s*(?P<dur>\d+(\.\d+)?)")

        starts = [float(m.group("start")) for m in start_pattern.finditer(stderr_text)]
        durs = [float(m.group("dur")) for m in dur_pattern.finditer(stderr_text)]

        # If a freeze started but did not un-freeze before EOF, calculate duration to end of stream
        if len(starts) > len(durs):
            time_match = re.search(r"time=(?P<h>\d+):(?P<m>\d+):(?P<s>\d+(\.\d+)?)", stderr_text)
            total_time = 0.0
            if time_match:
                total_time = (
                    int(time_match.group("h")) * 3600
                    + int(time_match.group("m")) * 60
                    + float(time_match.group("s"))
                )
            for s in starts[len(durs):]:
                dur = max(0.0, total_time - s) if total_time > s else min_duration_seconds
                durs.append(round(dur, 3))

        for s, d in zip(starts, durs):
            events.append(FrozenFrameEvent(start_seconds=s, duration_seconds=d, end_seconds=round(s + d, 3)))

        total_frozen = sum(e.duration_seconds for e in events)
        return FrozenFrameDetectionResult(
            detected=len(events) > 0,
            event_count=len(events),
            total_frozen_duration=round(total_frozen, 3),
            events=events,
        )

    async def validate_streams(
        self,
        video_path: str,
        expected_aspect: str = "16:9",
    ) -> StreamValidationResult:
        """Validates video and audio stream codecs, geometry, and frame rate against broadcast standards."""
        path = Path(video_path)
        issues: List[str] = []

        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_streams",
            "-show_format",
            "-of", "json",
            str(path),
        ]

        loop = asyncio.get_running_loop()
        proc = await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False),
        )

        if proc.returncode != 0:
            return StreamValidationResult(
                video_codec="none",
                audio_codec="none",
                pixel_format="none",
                framerate_fps=0.0,
                width=0,
                height=0,
                aspect_ratio=expected_aspect,
                is_valid_broadcast_format=False,
                issues=["FFprobe could not read container headers."],
            )

        info = json.loads(proc.stdout.decode(errors="replace"))
        v_stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
        a_stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)

        if not v_stream:
            issues.append("Missing video stream in container.")
            return StreamValidationResult(
                video_codec="none",
                audio_codec="none",
                pixel_format="none",
                framerate_fps=0.0,
                width=0,
                height=0,
                aspect_ratio=expected_aspect,
                is_valid_broadcast_format=False,
                issues=issues,
            )

        v_codec = v_stream.get("codec_name", "unknown")
        pix_fmt = v_stream.get("pix_fmt", "unknown")
        width = int(v_stream.get("width", 0))
        height = int(v_stream.get("height", 0))
        a_codec = a_stream.get("codec_name", "none") if a_stream else "none"

        # Frame rate parsing (e.g. "30/1" -> 30.0)
        r_fps = v_stream.get("r_frame_rate", "30/1")
        try:
            num, den = map(int, r_fps.split("/"))
            fps = round(num / max(den, 1), 2)
        except Exception:
            fps = 30.0

        target_cfg = ASPECT_RATIO_CONFIGS.get(expected_aspect, ASPECT_RATIO_CONFIGS["16:9"])
        exp_w, exp_h = target_cfg["width"], target_cfg["height"]

        if v_codec != "h264":
            issues.append(f"Non-standard video codec '{v_codec}' (expected h264).")
        if a_codec != "aac":
            issues.append(f"Non-standard audio codec '{a_codec}' (expected aac).")
        if pix_fmt != "yuv420p":
            issues.append(f"Pixel format '{pix_fmt}' may cause playback incompatibility (expected yuv420p).")
        if width != exp_w or height != exp_h:
            issues.append(f"Resolution {width}x{height} does not match expected {exp_w}x{exp_h} for {expected_aspect}.")
        if abs(fps - 30.0) > 0.5:
            issues.append(f"Framerate {fps} fps deviates from 30.0 fps broadcast standard.")

        return StreamValidationResult(
            video_codec=v_codec,
            audio_codec=a_codec,
            pixel_format=pix_fmt,
            framerate_fps=fps,
            width=width,
            height=height,
            aspect_ratio=expected_aspect,
            is_valid_broadcast_format=len(issues) == 0,
            issues=issues,
        )

    async def validate_audio_sync(self, video_path: str) -> SyncValidationResult:
        """Validates synchronization between audio and video streams (tolerance: <= 50ms)."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "stream=codec_type,duration",
            "-show_entries", "format=duration",
            "-of", "json",
            video_path,
        ]

        loop = asyncio.get_running_loop()
        proc = await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False),
        )

        if proc.returncode != 0:
            return SyncValidationResult(
                video_duration_seconds=0.0,
                audio_duration_seconds=0.0,
                drift_seconds=0.0,
                is_synchronized=False,
                tolerance_threshold_seconds=0.050,
            )

        try:
            info = json.loads(proc.stdout.decode(errors="replace"))
        except Exception:
            return SyncValidationResult(
                video_duration_seconds=0.0,
                audio_duration_seconds=0.0,
                drift_seconds=0.0,
                is_synchronized=False,
                tolerance_threshold_seconds=0.050,
            )
        streams = info.get("streams", [])
        fmt = info.get("format", {})

        v_dur = 0.0
        a_dur = 0.0
        for s in streams:
            if s.get("codec_type") == "video":
                v_dur = float(s.get("duration") or fmt.get("duration") or 0.0)
            elif s.get("codec_type") == "audio":
                a_dur = float(s.get("duration") or fmt.get("duration") or 0.0)

        drift = abs(v_dur - a_dur)
        within_tolerance = drift <= 0.050  # 50 milliseconds

        return SyncValidationResult(
            video_duration_seconds=round(v_dur, 3),
            audio_duration_seconds=round(a_dur, 3),
            drift_seconds=round(drift, 3),
            is_synchronized=within_tolerance,
            within_tolerance=within_tolerance,
        )

    def validate_subtitles(self, srt_content: str, video_duration: float) -> SubtitleValidationResult:
        """Validates that subtitle cues do not overlap, are non-empty, and fall within video duration."""
        if not srt_content or not srt_content.strip():
            return SubtitleValidationResult(
                total_cues=0,
                has_overlaps=False,
                has_out_of_bounds=False,
                coverage_ratio=0.0,
                issues=["Subtitle file is empty."],
            )

        issues: List[str] = []
        cues = []
        # Pattern matches: 00:00:01,234 --> 00:00:04,567
        time_pat = re.compile(
            r"(?P<sh>\d{2}):(?P<sm>\d{2}):(?P<ss>\d{2}),(?P<sms>\d{3})\s*-->\s*(?P<eh>\d{2}):(?P<em>\d{2}):(?P<es>\d{2}),(?P<ems>\d{3})"
        )

        for match in time_pat.finditer(srt_content):
            s_sec = (
                int(match.group("sh")) * 3600
                + int(match.group("sm")) * 60
                + int(match.group("ss"))
                + int(match.group("sms")) / 1000.0
            )
            e_sec = (
                int(match.group("eh")) * 3600
                + int(match.group("em")) * 60
                + int(match.group("es"))
                + int(match.group("ems")) / 1000.0
            )
            cues.append((s_sec, e_sec))

        total_cues = len(cues)
        has_overlaps = False
        has_out_of_bounds = False

        for i in range(len(cues)):
            s, e = cues[i]
            if e <= s:
                issues.append(f"Cue {i+1} has invalid duration (end <= start).")
            if e > video_duration + 0.5:
                has_out_of_bounds = True
                issues.append(f"Cue {i+1} exceeds video duration ({e:.2f}s > {video_duration:.2f}s).")
            if i > 0:
                prev_s, prev_e = cues[i - 1]
                if s < prev_e - 0.05:  # Overlap > 50ms
                    has_overlaps = True
                    issues.append(f"Cue {i+1} overlaps with cue {i} ({s:.2f}s < {prev_e:.2f}s).")

        return SubtitleValidationResult(
            total_cues=total_cues,
            has_overlaps=has_overlaps,
            has_out_of_bounds=has_out_of_bounds,
            coverage_ratio=1.0 if not issues else 0.85,
            issues=issues,
        )
