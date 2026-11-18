"""Footage retrieval, ranking, deduplication, and attribution package (Phase 4)."""

from broll_engine.models.retrieval import (
    AssetLicense,
    CandidateAsset,
    DeduplicationReport,
    FootageRetrievalResult,
    RankedAsset,
    SelectedClip,
)
from broll_engine.retrieval.base import (
    BaseFootageProvider,
    FootageProviderError,
    InvalidCredentialsError,
    RateLimitExceededError,
)
from broll_engine.retrieval.dedup import ClipDeduplicator
from broll_engine.retrieval.downloader import AssetDownloader, MediaValidationError
from broll_engine.retrieval.engine import FootageRetrievalEngine
from broll_engine.retrieval.pexels import PexelsProvider
from broll_engine.retrieval.pixabay import PixabayProvider
from broll_engine.retrieval.procedural import ProceduralFallbackProvider
from broll_engine.retrieval.ranker import SemanticRelevanceRanker

__all__ = [
    "BaseFootageProvider",
    "FootageProviderError",
    "RateLimitExceededError",
    "InvalidCredentialsError",
    "PexelsProvider",
    "PixabayProvider",
    "ProceduralFallbackProvider",
    "SemanticRelevanceRanker",
    "ClipDeduplicator",
    "AssetDownloader",
    "MediaValidationError",
    "FootageRetrievalEngine",
    "CandidateAsset",
    "RankedAsset",
    "SelectedClip",
    "AssetLicense",
    "FootageRetrievalResult",
    "DeduplicationReport",
]
