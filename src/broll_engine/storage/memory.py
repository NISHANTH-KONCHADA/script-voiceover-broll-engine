from typing import Dict, Optional
from broll_engine.storage.base import StorageAdapter


class InMemoryStorageAdapter(StorageAdapter):
    """In-memory object storage adapter for isolated, zero-dependency testing."""

    def __init__(self, base_url: str = "http://storage.local/broll-bucket") -> None:
        self.base_url = base_url.rstrip("/")
        self._store: Dict[str, bytes] = {}

    async def upload_file(self, local_path: str, destination_key: str, content_type: Optional[str] = None) -> str:
        with open(local_path, "rb") as f:
            data = f.read()
        self._store[destination_key] = data
        return await self.get_url(destination_key)

    async def upload_bytes(self, data: bytes, destination_key: str, content_type: Optional[str] = None) -> str:
        self._store[destination_key] = data
        return await self.get_url(destination_key)

    async def download_file(self, remote_key: str, local_path: str) -> None:
        if remote_key not in self._store:
            raise FileNotFoundError(f"Key '{remote_key}' not found in in-memory storage.")
        with open(local_path, "wb") as f:
            f.write(self._store[remote_key])

    async def download_bytes(self, remote_key: str) -> bytes:
        if remote_key not in self._store:
            raise FileNotFoundError(f"Key '{remote_key}' not found in in-memory storage.")
        return self._store[remote_key]

    async def get_url(self, remote_key: str) -> str:
        return f"{self.base_url}/{remote_key}"

    async def health_check(self) -> bool:
        return True
