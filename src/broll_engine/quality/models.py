"""Pydantic data models for automated video quality assessment, visual composition, and scoring (Phase 6)."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BlackFrameEvent(BaseModel):
    start_seconds: float
    end_seconds: float
    duration_seconds: float


class FrozenFrameEvent(BaseModel):
    start_seconds: float
    end_seconds: Optional[float] = None
    duration_seconds: float


class BlackFrameDetectionResult(BaseModel):
    detected: bool
    event_count: int = 0
    total_black_duration: float = 0.0
    events: List[BlackFrameEvent] = Field(default_factory=list)


class FrozenFrameDetectionResult(BaseModel):
    detected: bool
    event_count: int = 0
    total_frozen_duration: float = 0.0
    events: List[FrozenFrameEvent] = Field(default_factory=list)


class StreamValidationResult(BaseModel):
    video_codec: str
    audio_codec: str
    pixel_format: str
    framerate_fps: float
    width: int
    height: int
    aspect_ratio: str
    is_valid_broadcast_format: bool
    issues: List[str] = Field(default_factory=list)


class SyncValidationResult(BaseModel):
    video_duration_seconds: float
    audio_duration_seconds: float
    drift_seconds: float
    is_synchronized: bool
    within_tolerance: bool  # drift <= 0.05s (50ms)


class SubtitleValidationResult(BaseModel):
    total_cues: int
    has_overlaps: bool
    has_out_of_bounds: bool
    coverage_ratio: float = 1.0
    issues: List[str] = Field(default_factory=list)

    @property
    def valid(self) -> bool:
        return len(self.issues) == 0 and not self.has_overlaps and not self.has_out_of_bounds

    @property
    def cue_count(self) -> int:
        return self.total_cues

    @property
    def timing_anomalies_count(self) -> int:
        return len(self.issues)


class SaliencyCropReport(BaseModel):
    aspect_ratio: str
    crop_strategy: str
    safe_area_energy_ratio: float = Field(..., description="Proportion of visual energy centered in title-safe 60% zone")
    is_crop_safe: bool
    recommendation: str
    analysis_type: str = "heuristic_spatial_contrast"  # Explicit disclosure: not claiming neural VLM


class SceneQualityScore(BaseModel):
    scene_id: str
    scene_index: int
    relevance_score: float = Field(..., ge=0.0, le=5.0)
    pacing_score: float = Field(..., ge=0.0, le=100.0)
    visual_diversity_score: float = Field(..., ge=0.0, le=100.0)
    composite_scene_score: float = Field(..., ge=0.0, le=100.0)
    rationale: str


class VideoQualityReport(BaseModel):
    overall_quality_score: float = Field(..., ge=0.0, le=100.0, description="Overall quality score (0-100)")
    passed: bool = Field(..., description="True if no critical quality gates failed and score >= 70.0")
    objective_metrics: Dict[str, Any] = Field(..., description="Defensible deterministic physical metrics")
    heuristic_metrics: Dict[str, Any] = Field(..., description="Composition and semantic heuristic ratings")
    scene_scores: List[SceneQualityScore] = Field(default_factory=list)
    saliency_reports: Dict[str, SaliencyCropReport] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    failures: List[str] = Field(default_factory=list)
    evaluated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
