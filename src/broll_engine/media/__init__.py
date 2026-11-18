"""Media processing, audio normalization, subtitle generation, and video assembly package (Phase 5)."""

from broll_engine.media.audio import AudioNormalizationError, AudioNormalizer
from broll_engine.media.scaler import ASPECT_RATIO_CONFIGS, VideoScaler
from broll_engine.media.subtitles import (
    SubtitleGenerator,
    format_ass_timestamp,
    format_srt_timestamp,
)
from broll_engine.media.assembler import VideoAssemblyEngine, VideoAssemblyError

__all__ = [
    "AudioNormalizer",
    "AudioNormalizationError",
    "SubtitleGenerator",
    "format_srt_timestamp",
    "format_ass_timestamp",
    "VideoScaler",
    "ASPECT_RATIO_CONFIGS",
    "VideoAssemblyEngine",
    "VideoAssemblyError",
]
