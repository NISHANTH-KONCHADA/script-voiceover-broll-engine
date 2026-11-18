"""Abstract base class and exceptions for footage retrieval providers."""

from abc import ABC, abstractmethod
from typing import List, Optional
from broll_engine.models.retrieval import CandidateAsset


class FootageProviderError(Exception):
    """Base exception for external footage retrieval providers."""
    def __init__(self, message: str, provider: str, retryable: bool = False, status_code: Optional[int] = None):
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable
        self.status_code = status_code


class RateLimitExceededError(FootageProviderError):
    """Raised when an external API rate limit (HTTP 429) is encountered."""
    def __init__(self, provider: str, retry_after: Optional[int] = None):
        msg = f"Rate limit exceeded for provider '{provider}'."
        if retry_after:
            msg += f" Retry after {retry_after} seconds."
        super().__init__(msg, provider=provider, retryable=True, status_code=429)
        self.retry_after = retry_after


class InvalidCredentialsError(FootageProviderError):
    """Raised when authentication fails (HTTP 401 or 403)."""
    def __init__(self, provider: str, message: str = "Invalid or missing API key"):
        super().__init__(f"Provider '{provider}' authentication failed: {message}", provider=provider, retryable=False, status_code=401)


class BaseFootageProvider(ABC):
    """Abstract interface for all video stock and procedural footage sources."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider (e.g. 'pexels', 'pixabay', 'procedural')."""
        pass

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Returns True if the provider has necessary API keys or operational runtime."""
        pass

    @abstractmethod
    async def search_videos(
        self,
        query: str,
        aspect_ratio: str = "16:9",
        per_page: int = 10,
    ) -> List[CandidateAsset]:
        """Search for candidate video assets matching the visual query.

        Args:
            query: Visual search terms (e.g. 'datacenter server racks glowing blue lights')
            aspect_ratio: '16:9', '9:16', or '1:1'
            per_page: Number of candidates to request

        Returns:
            List of CandidateAsset objects with verified licence information.
        """
        pass
