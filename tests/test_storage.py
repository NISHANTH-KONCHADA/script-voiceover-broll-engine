import os
import tempfile
import pytest
from broll_engine.storage.memory import InMemoryStorageAdapter
from broll_engine.storage.s3 import S3StorageAdapter


@pytest.mark.asyncio
async def test_in_memory_storage_bytes():
    """Verifies byte upload, download, and URL generation in memory adapter."""
    storage = InMemoryStorageAdapter(base_url="http://mock-storage.test/broll-bucket")
    test_data = b"Hello IncuBrix B-roll Engine!"
    key = "test/sample.txt"

    url = await storage.upload_bytes(test_data, key, "text/plain")
    assert url == "http://mock-storage.test/broll-bucket/test/sample.txt"

    downloaded = await storage.download_bytes(key)
    assert downloaded == test_data

    assert await storage.health_check() is True


@pytest.mark.asyncio
async def test_in_memory_storage_file():
    """Verifies file upload and download via temporary files."""
    storage = InMemoryStorageAdapter()
    content = b"Binary video frame mock chunk 12345"

    with tempfile.NamedTemporaryFile(delete=False) as tmp_in:
        tmp_in.write(content)
        tmp_in_path = tmp_in.name

    with tempfile.NamedTemporaryFile(delete=False) as tmp_out:
        tmp_out_path = tmp_out.name

    try:
        url = await storage.upload_file(tmp_in_path, "frames/chunk_01.mp4", "video/mp4")
        assert "frames/chunk_01.mp4" in url

        await storage.download_file("frames/chunk_01.mp4", tmp_out_path)
        with open(tmp_out_path, "rb") as f:
            read_back = f.read()
        assert read_back == content
    finally:
        os.remove(tmp_in_path)
        os.remove(tmp_out_path)


@pytest.mark.asyncio
async def test_s3_storage_initialization():
    """Verifies S3StorageAdapter initializes client properly."""
    s3_adapter = S3StorageAdapter(
        endpoint_url="http://localhost:9000",
        access_key_id="minioadmin",
        secret_access_key="minioadmin",
        bucket_name="test-bucket",
    )
    assert s3_adapter.bucket_name == "test-bucket"
    assert s3_adapter.client is not None
