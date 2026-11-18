from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from broll_engine.speech.asr.base import WordTiming


class TimingSource(str, Enum):
    """
    Distinguishes genuine acoustic speech recognition timestamps from
    synthesized word boundaries interpolated from text-to-speech sentences.
    """
    ASR_ACOUSTIC = "asr_acoustic"
    TTS_INTERPOLATED = "tts_interpolated"


class PacingStatus(str, Enum):
    """Pacing validation and adjustment status for a scene."""
    VALID = "valid"
    MERGED_UNDER_MIN = "merged_under_min"
    SPLIT_OVER_MAX = "split_over_max"


class SegmentationReason(str, Enum):
    """Reason a scene boundary was created."""
    DIRECTOR_HINT = "director_hint"
    SENTENCE_BOUNDARY = "sentence_boundary"
    CLAUSE_BOUNDARY = "clause_boundary"
    PACING_SPLIT_MAX_DURATION = "pacing_split_max_duration"
    PACING_MERGE_MIN_DURATION = "pacing_merge_min_duration"


class Scene(BaseModel):
    """
    Structured visual scene representing a continuous slice of the video narration.
    Satisfies all IncuBrix Phase 3 schema requirements.
    """
    id: str = Field(..., description="Unique scene identifier, e.g. 'scene_001'")
    index: int = Field(..., ge=0, description="Sequential 0-indexed scene order")
    start_seconds: float = Field(..., ge=0.0, description="Exact start time in seconds")
    end_seconds: float = Field(..., ge=0.0, description="Exact end time in seconds")
    duration_seconds: float = Field(..., ge=0.0, description="Duration of this scene in seconds")
    narration_text: str = Field(..., description="Spoken transcript segment for this scene")
    language: str = Field(default="en", description="Language code (en, hi, ta)")
    visual_query: str = Field(..., description="Disambiguated, concise search query for B-roll retrieval")
    visual_intent: str = Field(default="concrete_action", description="Intent category: concrete_action, metaphor, technology, environment")
    negative_constraints: List[str] = Field(
        default_factory=list,
        description="Negative visual search constraints (e.g. no identifiable faces, no logos, no watermarks)"
    )
    segmentation_reason: SegmentationReason = Field(
        default=SegmentationReason.SENTENCE_BOUNDARY,
        description="Underlying rule or model that defined this scene boundary"
    )
    pacing_status: PacingStatus = Field(
        default=PacingStatus.VALID,
        description="Whether pacing constraints were met natively or required merge/split"
    )
    timing_source: TimingSource = Field(
        default=TimingSource.ASR_ACOUSTIC,
        description="Indicates whether word timings are from acoustic ASR alignment or TTS sentence interpolation"
    )
    words: List[WordTiming] = Field(default_factory=list, description="Word-level timings contained within this scene")


class SceneSegmentationResult(BaseModel):
    """Output bundle from the semantic scene segmentation pipeline."""
    scenes: List[Scene] = Field(default_factory=list, description="Ordered list of segmented scenes")
    total_duration_seconds: float = Field(..., ge=0.0, description="Total narration duration covered")
    scene_count: int = Field(..., ge=0, description="Total number of scenes")
    timing_source: TimingSource = Field(..., description="Origin of speech timing data")
    has_gaps: bool = Field(default=False, description="True if any un-covered gaps exist between scenes")
    has_overlaps: bool = Field(default=False, description="True if any scenes overlap in time")
    pacing_adherence_rate: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Fraction of scenes adhering to [1.8s, 5.0s] limits"
    )
