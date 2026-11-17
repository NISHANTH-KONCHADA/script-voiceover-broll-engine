import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import soundfile as sf
import numpy as np

from broll_engine.api.routes.errors import APIError
from broll_engine.config import settings
from broll_engine.logging import get_logger

logger = get_logger(__name__)

SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a"}


@dataclass
class AudioMetadata:
    """Inspected properties of an input audio file."""
    file_path: str
    format: str
    duration_seconds: float
    sample_rate: int
    channels: int
    rms_dbfs: float
    speech_ratio: float


class AudioPreflightError(APIError):
    """Specialized exception for audio validation failures."""
    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=code,
            message=message,
            status_code=400,
            retryable=False,
            details=details or {},
        )


class AudioPreflightValidator:
    """
    Validates audio files for format, duration, integrity, and speech activity.
    Fails fast on corrupted files, unsupported codecs, and silent/music-only tracks.
    """

    def __init__(
        self,
        max_duration_seconds: float = settings.max_audio_duration_seconds,
        min_duration_seconds: float = settings.min_audio_duration_seconds,
        silence_threshold_dbfs: float = -45.0,
        min_speech_ratio: float = 0.05,
    ) -> None:
        self.max_duration = max_duration_seconds
        self.min_duration = min_duration_seconds
        self.silence_threshold_dbfs = silence_threshold_dbfs
        self.min_speech_ratio = min_speech_ratio

    def validate_file(self, file_path: str) -> AudioMetadata:
        """Runs complete preflight inspection on an audio file path."""
        path = Path(file_path)

        # Step 1: File existence check
        if not path.is_file():
            raise AudioPreflightError(
                code="AUDIO_FILE_NOT_FOUND",
                message=f"Audio file not found at path: {file_path}",
                details={"file_path": file_path},
            )

        # Step 2: Format & extension validation
        ext = path.suffix.lower()
        if ext not in SUPPORTED_AUDIO_EXTENSIONS:
            raise AudioPreflightError(
                code="UNSUPPORTED_AUDIO_FORMAT",
                message=f"Audio format '{ext}' is unsupported. Accepted formats: mp3, wav, m4a.",
                details={"provided_extension": ext, "supported_formats": list(SUPPORTED_AUDIO_EXTENSIONS)},
            )

        # Step 3: Decode & integrity check
        try:
            data, sample_rate = sf.read(str(path), always_2d=True)
        except Exception as exc:
            # Fallback check using pydub if soundfile lacks codec support for m4a
            try:
                from pydub import AudioSegment
                seg = AudioSegment.from_file(str(path))
                sample_rate = seg.frame_rate
                samples = np.array(seg.get_array_of_samples(), dtype=np.float32)
                # Normalize based on sample width
                max_val = float(1 << (seg.sample_width * 8 - 1))
                samples = samples / max_val
                if seg.channels > 1:
                    data = samples.reshape((-1, seg.channels))
                else:
                    data = samples.reshape((-1, 1))
            except Exception as inner_exc:
                logger.warning(f"Audio read failed on {file_path}: {exc} / {inner_exc}")
                raise AudioPreflightError(
                    code="CORRUPTED_AUDIO_FILE",
                    message=f"Audio file is corrupted or cannot be decoded: {path.name}",
                    details={"error": str(exc)},
                )

        # Step 4: Duration limits check
        num_frames, channels = data.shape
        duration = float(num_frames) / float(sample_rate)

        if duration > self.max_duration:
            raise AudioPreflightError(
                code="AUDIO_EXCEEDS_MAX_DURATION",
                message=f"Audio duration ({duration:.2f}s) exceeds the maximum limit of {self.max_duration:.1f}s (10 minutes).",
                details={"duration_seconds": round(duration, 2), "max_duration_seconds": self.max_duration},
            )

        if duration < self.min_duration:
            raise AudioPreflightError(
                code="AUDIO_TOO_SHORT",
                message=f"Audio duration ({duration:.2f}s) is shorter than minimum required ({self.min_duration:.1f}s).",
                details={"duration_seconds": round(duration, 2), "min_duration_seconds": self.min_duration},
            )

        # Step 5: Voice Activity Detection (VAD) & Energy Analysis
        rms_dbfs, speech_ratio = self._analyze_speech_activity(data, sample_rate)

        if rms_dbfs < self.silence_threshold_dbfs or speech_ratio < self.min_speech_ratio:
            raise AudioPreflightError(
                code="NO_SPEECH_DETECTED",
                message="No speech detected in audio file. Audio appears to be completely silent or contains background music only.",
                details={
                    "duration_seconds": round(duration, 2),
                    "rms_dbfs": round(rms_dbfs, 2),
                    "speech_ratio": round(speech_ratio, 3),
                    "silence_threshold_dbfs": self.silence_threshold_dbfs,
                },
            )

        logger.info(
            f"Audio preflight passed for {path.name}: {duration:.2f}s, {sample_rate}Hz, {channels}ch, "
            f"RMS={rms_dbfs:.1f}dBFS, speech_ratio={speech_ratio:.2%}"
        )

        return AudioMetadata(
            file_path=str(path),
            format=ext.lstrip("."),
            duration_seconds=round(duration, 3),
            sample_rate=sample_rate,
            channels=channels,
            rms_dbfs=round(rms_dbfs, 2),
            speech_ratio=round(speech_ratio, 3),
        )

    def _analyze_speech_activity(self, data: np.ndarray, sample_rate: int) -> Tuple[float, float]:
        """
        Analyzes energy distribution and speech presence in 30ms frames.
        Returns (overall_rms_dbfs, speech_frame_ratio).
        """
        # Convert to mono
        mono = data.mean(axis=1) if data.ndim > 1 else data

        # Overall RMS
        mean_square = np.mean(mono ** 2)
        if mean_square <= 1e-12:
            return -100.0, 0.0

        rms = math.sqrt(mean_square)
        overall_dbfs = 20.0 * math.log10(max(rms, 1e-6))

        # Chunk into 30ms windows
        frame_size = int(sample_rate * 0.030)
        if frame_size == 0 or len(mono) < frame_size:
            return overall_dbfs, (1.0 if overall_dbfs > -35.0 else 0.0)

        num_chunks = len(mono) // frame_size
        chunks = mono[:num_chunks * frame_size].reshape((num_chunks, frame_size))

        chunk_rms = np.sqrt(np.mean(chunks ** 2, axis=1) + 1e-12)
        chunk_dbfs = 20.0 * np.log10(np.maximum(chunk_rms, 1e-6))

        # Speech frames typically sit between -35 dBFS and -12 dBFS
        # Background noise sits below -45 dBFS
        active_speech_frames = np.sum(chunk_dbfs > -38.0)
        speech_ratio = float(active_speech_frames) / float(num_chunks)

        return overall_dbfs, speech_ratio
