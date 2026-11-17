from abc import ABC, abstractmethod
from typing import Optional


class StorageAdapter(ABC):
    """Abstract interface for object storage adapters."""

    @abstractmethod
    async def upload_file(self, local_path: str, destination_key: str, content_type: Optional[str] = None) -> str:
        """Uploads a local file to storage and returns its accessible download URL."""
        pass

    @abstractmethod
    async def upload_bytes(self, data: bytes, destination_key: str, content_type: Optional[str] = None) -> str:
        """Uploads raw bytes to storage and returns its accessible download URL."""
        pass

    @abstractmethod
    async def download_file(self, remote_key: str, local_path: str) -> None:
        """Downloads an object to a local file path."""
        pass

    @abstractmethod
    async def download_bytes(self, remote_key: str) -> bytes:
        """Downloads an object and returns its raw bytes."""
        pass

    @abstractmethod
    async def get_url(self, remote_key: str) -> str:
        """Returns the public or presigned URL for an object."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Verifies that storage connectivity is healthy."""
        pass
