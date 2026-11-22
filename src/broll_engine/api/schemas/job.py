from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class AspectRatio(str, Enum):
    RATIO_16_9 = "16:9"
    RATIO_9_16 = "9:16"
    RATIO_1_1 = "1:1"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class CaptionOptions(BaseModel):
    burn_in: bool = Field(default=True, description="Burn subtitles directly onto video frames")
    srt: bool = Field(default=True, description="Generate standalone SubRip .srt sidecar file")


class SceneHint(BaseModel):
    text: str = Field(..., description="Narration line for scene", min_length=1)
    visual_hint: Optional[str] = Field(default=None, description="Director guidance for footage search")


class JobCreateRequest(BaseModel):
    """Payload for POST /api/v1/broll/jobs."""
    audio_url: Optional[str] = Field(default=None, description="Direct URL to pre-recorded audio file (mp3, wav, m4a)")
    script: Optional[str] = Field(default=None, description="Plain text script for narration synthesis", min_length=1)
    scenes: Optional[List[SceneHint]] = Field(default=None, description="Pre-segmented IncuBrix scene list with hints")
    voice: str = Field(default="en-IN-female", description="TTS voice identifier for text input")
    aspect_ratios: List[AspectRatio] = Field(default=[AspectRatio.RATIO_16_9], min_length=1, description="Target aspect ratios")
    target_aspect_ratios: Optional[List[AspectRatio]] = Field(default=None, description="Alternative alias for aspect_ratios")
    style: Optional[str] = Field(default="bright, modern, real-world footage", description="Aesthetic style description")
    avoid: Optional[List[str]] = Field(default_factory=list, description="Negative visual concepts or content to avoid")
    captions: CaptionOptions = Field(default_factory=CaptionOptions, description="Caption generation preferences")
    callback_url: Optional[str] = Field(default=None, description="Optional webhook URL called upon job completion")
    webhook_secret: Optional[str] = Field(default=None, description="Optional custom shared secret for HMAC-SHA256 callback signing")

    @model_validator(mode="after")
    def validate_inputs(self) -> "JobCreateRequest":
        if self.target_aspect_ratios and (self.aspect_ratios == [AspectRatio.RATIO_16_9] or not self.aspect_ratios):
            self.aspect_ratios = self.target_aspect_ratios
        if self.script is not None and not self.script.strip():
            raise ValueError("script must contain non-whitespace text.")
        inputs = [bool(self.audio_url), bool(self.script), bool(self.scenes)]
        if sum(inputs) == 0:
            raise ValueError("At least one input must be provided: audio_url, script, or scenes.")
        return self


class JobCreateResponse(BaseModel):
    """Response returned upon successful job enqueueing (HTTP 202)."""
    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatus = Field(default=JobStatus.QUEUED, description="Initial job status")
    progress: int = Field(default=0, ge=0, le=100, description="Processing progress percentage")
    created_at: datetime = Field(..., description="UTC creation timestamp")
    check_status_url: str = Field(..., description="Direct status endpoint URL")


class JobOutputs(BaseModel):
    """Download links to generated media artifacts."""
    videos: Dict[str, str] = Field(default_factory=dict, description="Map of aspect_ratio to video download URL")
    audio: Optional[str] = Field(default=None, description="Download URL for master narration audio")
    transcript: Optional[str] = Field(default=None, description="Download URL for word-aligned transcript.json")
    scenes: Optional[str] = Field(default=None, description="Download URL for scenes.json (Phase 3)")
    captions: Optional[str] = Field(default=None, description="Download URL for captions.srt")
    timeline: Optional[str] = Field(default=None, description="Download URL for timeline.json")
    manifest: Optional[str] = Field(default=None, description="Download URL for manifest.json")
    quality_report: Optional[str] = Field(default=None, description="Download URL for quality_report.json (Phase 6)")


class JobDetailResponse(BaseModel):
    """Full job details returned by GET /api/v1/jobs/{job_id}."""
    job_id: str
    status: JobStatus
    progress: int = Field(..., ge=0, le=100)
    stage: str = Field(..., description="Current engine pipeline stage")
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    outputs: Optional[JobOutputs] = None
    error: Optional[Dict[str, Any]] = None


class ClipSwapRequest(BaseModel):
    """Payload for POST /api/v1/broll/jobs/{job_id}/swap-clip."""
    model_config = ConfigDict(populate_by_name=True)

    scene_index: int = Field(..., ge=0, description="0-indexed scene to replace")
    new_clip_url: Optional[str] = Field(default=None, description="Direct URL to replacement video clip")
    replacement_clip_url: Optional[str] = Field(default=None, description="Direct URL to replacement video clip (alias for new_clip_url)")
    new_query: Optional[str] = Field(default=None, description="New visual search query to retrieve replacement clip")
    style: Optional[str] = Field(default=None, description="Optional style override")

    @model_validator(mode="after")
    def reconcile_urls(self) -> "ClipSwapRequest":
        if not self.new_clip_url and self.replacement_clip_url:
            self.new_clip_url = self.replacement_clip_url
        elif not self.replacement_clip_url and self.new_clip_url:
            self.replacement_clip_url = self.new_clip_url
        return self


class ClipSwapResponse(BaseModel):
    """Response returned upon successful scene replacement and partial re-render."""
    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatus = Field(default=JobStatus.SUCCEEDED, description="Job status")
    scene_index: int = Field(..., description="Index of replaced scene")
    re_rendered_scene_id: str = Field(..., description="ID of replaced scene")
    previous_clip_id: str = Field(..., description="Asset ID of previous clip")
    new_clip_id: str = Field(..., description="Asset ID of new replacement clip")
    processing_time_seconds: float = Field(..., description="Wall-clock time for partial re-render in seconds")
    outputs: JobOutputs = Field(..., description="Updated media download URLs")
    message: str = Field(default="Scene successfully replaced and video re-rendered")


class TimelineClipModel(BaseModel):
    """Individual editable clip instance placed on the timeline."""
    id: str = Field(..., description="Unique clip instance identifier")
    media_id: Optional[str] = Field(default=None, description="Original asset reference")
    media_url: Optional[str] = Field(default=None, description="Source video, audio, or image URL")
    local_path: Optional[str] = Field(default=None, description="Cached local path if available")
    track_id: str = Field(default="V1", description="Track identifier: V1, V2, A1, A2, TXT")
    start_time: float = Field(default=0.0, ge=0.0, description="Timeline start timestamp in seconds")
    duration: float = Field(default=3.0, gt=0.0, description="Duration on the timeline in seconds")
    source_in: float = Field(default=0.0, ge=0.0, description="Media in-point in seconds")
    source_out: float = Field(default=3.0, gt=0.0, description="Media out-point in seconds")
    speed: float = Field(default=1.0, gt=0.1, le=5.0, description="Playback speed multiplier")
    volume: float = Field(default=1.0, ge=0.0, le=2.0, description="Audio volume multiplier")
    scale: float = Field(default=1.0, gt=0.1, le=3.0, description="Visual scale zoom factor")
    text: Optional[str] = Field(default=None, description="Caption or subtitle text content")
    name: Optional[str] = Field(default=None, description="Display label in timeline")


class TimelineTrackModel(BaseModel):
    """Timeline track metadata."""
    id: str = Field(..., description="Track identifier e.g. V1, V2, A1, A2, TXT")
    name: str = Field(..., description="Display name for the track")
    type: str = Field(..., description="video, audio, or caption")
    muted: bool = Field(default=False)
    locked: bool = Field(default=False)
    visible: bool = Field(default=True)


class TimelineProjectModel(BaseModel):
    """Full persisted timeline project state."""
    job_id: str = Field(..., description="Associated job ID")
    aspect_ratio: str = Field(default="16:9", description="Current framing aspect ratio")
    duration: float = Field(default=20.0, ge=0.0, description="Total project duration")
    tracks: List[TimelineTrackModel] = Field(default_factory=list)
    clips: List[TimelineClipModel] = Field(default_factory=list)


class TimelineExportRequest(BaseModel):
    """Payload for POST /api/v1/jobs/{job_id}/export-timeline."""
    aspect_ratio: str = Field(default="16:9", description="Target aspect ratio: 16:9, 9:16, 1:1")
    tracks: List[TimelineTrackModel] = Field(default_factory=list)
    clips: List[TimelineClipModel] = Field(default_factory=list)
    burn_in_captions: bool = Field(default=True, description="Whether to burn captions onto video")
    caption_style: Optional[Dict[str, Any]] = Field(default=None, description="Custom styling for burned captions")


class TimelineExportResponse(BaseModel):
    """Response returned upon rendering the edited timeline composition."""
    job_id: str
    status: JobStatus = Field(default=JobStatus.SUCCEEDED)
    aspect_ratio: str
    video_url: str
    duration_seconds: float
    processing_time_seconds: float
    message: str = Field(default="Timeline composition rendered and exported successfully")


class MediaUploadResponse(BaseModel):
    """Response returned when an asset is imported or uploaded."""
    media_id: str
    filename: str
    media_type: str  # video, audio, image
    duration_seconds: float = 0.0
    width: Optional[int] = None
    height: Optional[int] = None
    url: str

