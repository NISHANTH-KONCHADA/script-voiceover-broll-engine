"""Pydantic data models for footage retrieval, licensing, attribution, and deduplication (Phase 4)."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class LicenseType(str, Enum):
    PEXELS = "Pexels License"
    PIXABAY = "Pixabay Content License"
    CC0 = "Creative Commons Zero (CC0)"
    PROCEDURAL = "Procedurally Generated (Commercial CC0 Equivalent)"
    CUSTOM_COMMERCIAL = "Custom Commercial License"
    UNVERIFIED = "Unverified Rights (Rejected)"


class AssetLicense(BaseModel):
    """Complete licence and legal clearance metadata for an asset."""
    license_name: str = Field(..., description="Official name of the licence")
    license_url: str = Field(..., description="Authoritative URL detailing licence terms")
    commercial_use_eligible: bool = Field(
        ...,
        description="Whether this asset is verified as eligible for commercial video production"
    )
    attribution_required: bool = Field(
        default=False,
        description="Whether attribution is legally required by the licence terms"
    )
    attribution_text: str = Field(
        ...,
        description="Human-readable attribution citation credit"
    )
    clearance_status: str = Field(
        default="commercial_cleared",
        description="'commercial_cleared' or 'rejected_unclear_rights'"
    )
    verification_notes: Optional[str] = Field(
        default=None,
        description="Legal verification explanation and restriction disclosures"
    )


class VideoFile(BaseModel):
    """Specific rendition of a video asset."""
    id: Optional[str] = None
    quality: str = Field(default="hd", description="'hd', 'uhd', 'sd', or 'original'")
    width: int
    height: int
    fps: Optional[float] = 30.0
    link: str = Field(..., description="Direct downloadable media URL")
    file_type: Optional[str] = "video/mp4"


class CandidateAsset(BaseModel):
    """Raw footage candidate retrieved from a provider before ranking."""
    asset_id: str = Field(..., description="Unique provider-scoped asset identifier (e.g. pexels_12345)")
    provider: str = Field(..., description="Source provider name ('pexels', 'pixabay', 'procedural')")
    title: str = Field(default="", description="Asset title or caption")
    description: Optional[str] = ""
    tags: List[str] = Field(default_factory=list, description="Descriptive tags provided by source")
    duration_seconds: float = Field(..., description="Asset duration in seconds")
    width: int = Field(default=1920, description="Native frame width")
    height: int = Field(default=1080, description="Native frame height")
    aspect_ratio: str = Field(default="16:9", description="'16:9', '9:16', or '1:1'")
    creator_name: str = Field(default="Unknown Creator", description="Author or videographer name")
    creator_url: Optional[str] = Field(default=None, description="Profile URL of the creator")
    original_page_url: str = Field(..., description="Web page URL of the original asset")
    download_url: str = Field(..., description="Direct URL to fetch the MP4 asset")
    license: AssetLicense = Field(..., description="Licence verification metadata")
    is_ai_generated: bool = Field(default=False, description="Flag if source identifies clip as AI-generated")
    is_procedural: bool = Field(default=False, description="Flag if clip was procedurally synthesized")
    video_files: List[VideoFile] = Field(default_factory=list, description="Available rendition formats")
    retrieved_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC retrieval timestamp"
    )


class RankedAsset(BaseModel):
    """Scored candidate asset with semantic relevance explanation."""
    candidate: CandidateAsset
    relevance_score: float = Field(..., ge=0.0, le=5.0, description="Normalized relevance score on 0.0 - 5.0 scale")
    relevance_ratio: float = Field(..., ge=0.0, le=1.0, description="Normalized relevance score on 0.0 - 1.0 scale")
    selection_reason: str = Field(..., description="Detailed explanation of score and tag alignment")
    matched_keywords: List[str] = Field(default_factory=list, description="Keywords matched from scene query")
    penalty_applied: float = Field(default=0.0, description="Score deductions from negative/homonym mismatch")


class SelectedClip(BaseModel):
    """Final clip bound to a scene with complete provenance and download information."""
    scene_id: str
    scene_index: int
    asset_id: str
    provider: str
    relevance_score: float = Field(..., ge=0.0, le=5.0)
    selection_reason: str
    license: AssetLicense
    creator: str
    creator_url: Optional[str] = None
    original_page_url: str
    download_url: str
    local_path: Optional[str] = Field(default=None, description="Local cached filesystem path to MP4")
    s3_key: Optional[str] = Field(default=None, description="S3 storage key if uploaded")
    download_status: str = Field(
        default="pending",
        description="'downloaded', 'cached', 'procedural_fallback', 'failed'"
    )
    fallback_status: str = Field(
        default="none",
        description="'none', 'procedural_gradient', 'procedural_motion'"
    )
    width: int = 1920
    height: int = 1080
    duration_seconds: float
    is_ai_generated: bool = False
    is_procedural: bool = False
    content_hash: Optional[str] = Field(default=None, description="SHA-256 hash of media file for deduplication")


class DeduplicationReport(BaseModel):
    """Audit summary of deduplication checks across scenes."""
    unique_clips_selected: int
    duplicate_candidates_rejected: int
    near_duplicates_rejected: int
    procedural_fallbacks_invoked: int
    used_asset_ids: List[str] = Field(default_factory=list)


class FootageRetrievalResult(BaseModel):
    """Full result of Phase 4 footage retrieval for an entire video job."""
    job_id: str
    total_scenes: int
    clips: List[SelectedClip]
    deduplication: DeduplicationReport
    providers_queried: List[str]
    retrieval_success_rate: float
    procedural_fallback_rate: float
