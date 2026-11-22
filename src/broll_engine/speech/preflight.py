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
    vad_provider: str = "silero"
    silero_detected: bool = True


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
    Integrates Silero VAD as the primary speech detector, retaining energy analysis
    for complementary audio validation. Fails fast on corrupted files, unsupported codecs,
    and silent/music-only tracks.
    """

    def __init__(
        self,
        max_duration_seconds: float = settings.max_audio_duration_seconds,
        min_duration_seconds: float = settings.min_audio_duration_seconds,
        silence_threshold_dbfs: float = -45.0,
        min_speech_ratio: float = 0.05,
        vad_provider: Optional[str] = None,
    ) -> None:
        self.max_duration = max_duration_seconds
        self.min_duration = min_duration_seconds
        self.silence_threshold_dbfs = silence_threshold_dbfs
        self.min_speech_ratio = min_speech_ratio
        self.vad_provider = vad_provider or settings.vad_provider

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
            data, sample_rate = sf.read(str(path), always_2d=True, dtype="float32")
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
        rms_dbfs, speech_ratio, silero_detected = self._analyze_speech_activity(data, sample_rate)

        if rms_dbfs < self.silence_threshold_dbfs or speech_ratio < self.min_speech_ratio or not silero_detected:
            raise AudioPreflightError(
                code="NO_SPEECH_DETECTED",
                message="No human speech detected in audio file. Audio appears to be completely silent, corrupted, or contains background music only.",
                details={
                    "duration_seconds": round(duration, 2),
                    "rms_dbfs": round(rms_dbfs, 2),
                    "speech_ratio": round(speech_ratio, 3),
                    "silero_detected": silero_detected,
                    "vad_provider": self.vad_provider,
                    "silence_threshold_dbfs": self.silence_threshold_dbfs,
                },
            )

        logger.info(
            f"Audio preflight passed for {path.name}: {duration:.2f}s, {sample_rate}Hz, {channels}ch, "
            f"RMS={rms_dbfs:.1f}dBFS, speech_ratio={speech_ratio:.2%}, vad={self.vad_provider}"
        )

        return AudioMetadata(
            file_path=str(path),
            format=ext.lstrip("."),
            duration_seconds=round(duration, 3),
            sample_rate=sample_rate,
            channels=channels,
            rms_dbfs=round(rms_dbfs, 2),
            speech_ratio=round(speech_ratio, 3),
            vad_provider=self.vad_provider,
            silero_detected=silero_detected,
        )

    def _analyze_speech_activity(self, data: np.ndarray, sample_rate: int) -> Tuple[float, float, bool]:
        """
        Analyzes speech activity using Silero VAD (ONNX) as primary detector,
        complemented by RMS dBFS energy distribution analysis.
        Returns (overall_rms_dbfs, speech_ratio, speech_detected).
        """
        # Convert to mono float32
        mono = data.mean(axis=1) if data.ndim > 1 else data
        mono = mono.astype(np.float32)

        # 1. Overall RMS dBFS energy check (complementary audio validation)
        mean_square = np.mean(mono ** 2)
        if mean_square <= 1e-12:
            return -100.0, 0.0, False

        rms = math.sqrt(mean_square)
        overall_dbfs = 20.0 * math.log10(max(rms, 1e-6))

        # Check if the audio is essentially digital silence (< -70 dBFS)
        if overall_dbfs < -70.0:
            return overall_dbfs, 0.0, False

        speech_detected = False
        speech_ratio = 0.0
        vad_completed = False

        # 2. Silero VAD as primary speech detector
        if self.vad_provider == "silero":
            try:
                from faster_whisper.vad import get_speech_timestamps, VadOptions

                # Resample mono audio to 16,000 Hz if necessary (Silero VAD standard)
                if sample_rate != 16000:
                    new_len = int(round(len(mono) * 16000.0 / sample_rate))
                    resampled_mono = np.interp(
                        np.linspace(0, len(mono), new_len, endpoint=False),
                        np.arange(len(mono)),
                        mono,
                    ).astype(np.float32)
                else:
                    resampled_mono = mono

                speech_timestamps = get_speech_timestamps(
                    resampled_mono,
                    sampling_rate=16000,
                    vad_options=VadOptions(threshold=0.4, min_speech_duration_ms=100),
                )

                vad_completed = True
                if speech_timestamps:
                    total_speech_samples = sum(item["end"] - item["start"] for item in speech_timestamps)
                    speech_ratio = float(total_speech_samples) / float(len(resampled_mono))
                    speech_detected = speech_ratio >= self.min_speech_ratio
                else:
                    speech_detected = False
                    speech_ratio = 0.0
            except Exception as vad_err:
                logger.warning(f"Silero VAD execution failed, falling back to energy analysis: {vad_err}")
                speech_detected = False

        # 3. Energy-based fallback when vad_provider == 'energy', Silero failed to execute,
        #    or a non-silero provider detected nothing
        if self.vad_provider == "energy" or (self.vad_provider == "silero" and not vad_completed) or (not speech_detected and self.vad_provider not in ("silero", "energy")):
            frame_size = int(sample_rate * 0.030)
            if frame_size == 0 or len(mono) < frame_size:
                speech_ratio = 1.0 if overall_dbfs > -35.0 else 0.0
            else:
                num_chunks = len(mono) // frame_size
                chunks = mono[:num_chunks * frame_size].reshape((num_chunks, frame_size))
                chunk_rms = np.sqrt(np.mean(chunks ** 2, axis=1) + 1e-12)
                chunk_dbfs = 20.0 * np.log10(np.maximum(chunk_rms, 1e-6))
                active_speech_frames = np.sum(chunk_dbfs > -38.0)
                speech_ratio = float(active_speech_frames) / float(num_chunks)

            speech_detected = speech_ratio >= self.min_speech_ratio

        return overall_dbfs, speech_ratio, speech_detected
