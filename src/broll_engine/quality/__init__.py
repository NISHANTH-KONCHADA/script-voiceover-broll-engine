"""Video quality assessment, composition analysis, and scoring package (Phase 6)."""

from broll_engine.quality.evaluator import VideoQualityEvaluator
from broll_engine.quality.models import (
    BlackFrameDetectionResult,
    FrozenFrameDetectionResult,
    SaliencyCropReport,
    SceneQualityScore,
    StreamValidationResult,
    SubtitleValidationResult,
    SyncValidationResult,
    VideoQualityReport,
)
from broll_engine.quality.saliency import VisualSaliencyAnalyzer
from broll_engine.quality.scorer import QualityScorer
from broll_engine.quality.video_inspector import VideoQualityInspector

__all__ = [
    "VideoQualityEvaluator",
    "VideoQualityInspector",
    "VisualSaliencyAnalyzer",
    "QualityScorer",
    "VideoQualityReport",
    "BlackFrameDetectionResult",
    "FrozenFrameDetectionResult",
    "StreamValidationResult",
    "SyncValidationResult",
    "SubtitleValidationResult",
    "SaliencyCropReport",
    "SceneQualityScore",
]
