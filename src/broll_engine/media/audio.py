"""Audio loudness normalization and synchronization engine (Phase 5)."""

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Optional
from broll_engine.logging import get_logger

logger = get_logger(__name__)


class AudioNormalizationError(Exception):
    """Raised when audio normalization fails."""
    pass


class AudioNormalizer:
    """Performs EBU R128 loudness normalization and audio track synchronization."""

    def __init__(
        self,
        target_lufs: float = -16.0,
        true_peak: float = -1.5,
        loudness_range: float = 11.0,
        sample_rate: int = 48000,
        bitrate: str = "192k",
    ):
        self.target_lufs = target_lufs
        self.true_peak = true_peak
        self.loudness_range = loudness_range
        self.sample_rate = sample_rate
        self.bitrate = bitrate

    async def normalize_audio(
        self,
        input_audio_path: str,
        output_audio_path: str,
    ) -> Dict[str, any]:
        """Normalizes audio to EBU R128 standard (-16 LUFS for web/video) at 48kHz stereo AAC.

        Returns:
            Dictionary with normalized duration, sample rate, channels, and loudness profile.
        """
        src = Path(input_audio_path)
        dest = Path(output_audio_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        if not src.exists() or src.stat().st_size == 0:
            raise AudioNormalizationError(f"Input audio file '{src}' does not exist or is empty.")

        filter_str = (
            f"loudnorm=I={self.target_lufs}:TP={self.true_peak}:LRA={self.loudness_range}:"
            f"print_format=summary"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(src),
            "-af", filter_str,
            "-ar", str(self.sample_rate),
            "-ac", "2",
            "-c:a", "aac",
            "-b:a", self.bitrate,
            str(dest),
        ]

        logger.info(
            "Normalizing audio '%s' -> '%s' (target: %.1f LUFS, %d Hz stereo)",
            src.name,
            dest.name,
            self.target_lufs,
            self.sample_rate,
        )

        loop = asyncio.get_running_loop()
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
            logger.error("FFmpeg audio normalization failed: %s", err)
            raise AudioNormalizationError(f"FFmpeg loudnorm error: {err}")

        # Probe the normalized audio file
        probe_info = await self.probe_audio(str(dest))
        return {
            "output_path": str(dest),
            "target_lufs": self.target_lufs,
            "true_peak_db": self.true_peak,
            "sample_rate": probe_info.get("sample_rate", self.sample_rate),
            "channels": probe_info.get("channels", 2),
            "duration_seconds": probe_info.get("duration", 0.0),
            "bitrate": probe_info.get("bitrate", self.bitrate),
        }

    async def probe_audio(self, audio_path: str) -> Dict[str, any]:
        """Probes audio stream properties via FFprobe."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=sample_rate,channels,duration,bit_rate,codec_name",
            "-show_entries", "format=duration,size",
            "-of", "json",
            audio_path,
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
            if proc.returncode == 0:
                data = json.loads(proc.stdout.decode(errors="replace"))
                streams = data.get("streams", [])
                format_info = data.get("format", {})
                if streams:
                    s = streams[0]
                    duration = float(s.get("duration") or format_info.get("duration") or 0.0)
                    return {
                        "duration": round(duration, 3),
                        "sample_rate": int(s.get("sample_rate") or 48000),
                        "channels": int(s.get("channels") or 2),
                        "codec": s.get("codec_name", "aac"),
                        "bitrate": s.get("bit_rate") or "192k",
                    }
        except Exception as e:
            logger.warning("FFprobe audio probe fallback: %s", e)

        return {"duration": 5.0, "sample_rate": self.sample_rate, "channels": 2, "codec": "aac"}
