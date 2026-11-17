import asyncio
import io
import mimetypes
from typing import Optional
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from broll_engine.config import settings
from broll_engine.logging import get_logger
from broll_engine.storage.base import StorageAdapter

logger = get_logger(__name__)


class S3StorageAdapter(StorageAdapter):
    """S3-compatible storage adapter for MinIO, AWS S3, and Cloudflare R2."""

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        bucket_name: Optional[str] = None,
        region: Optional[str] = None,
        secure: Optional[bool] = None,
    ) -> None:
        self.endpoint_url = endpoint_url or settings.s3_endpoint_url
        self.access_key_id = access_key_id or settings.s3_access_key_id
        self.secret_access_key = secret_access_key or settings.s3_secret_access_key
        self.bucket_name = bucket_name or settings.s3_bucket_name
        self.region = region or settings.s3_region
        self.use_ssl = secure if secure is not None else settings.s3_secure

        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            region_name=self.region,
            use_ssl=self.use_ssl,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def _ensure_bucket_sync(self) -> None:
        """Creates bucket if it does not already exist."""
        try:
            self.client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code in ("404", "NoSuchBucket"):
                logger.info(f"Bucket '{self.bucket_name}' not found. Creating bucket...")
                try:
                    self.client.create_bucket(Bucket=self.bucket_name)
                except Exception as create_err:
                    logger.warning(f"Could not automatically create bucket '{self.bucket_name}': {create_err}")
            else:
                logger.warning(f"S3 head_bucket check returned: {e}")

    async def ensure_bucket(self) -> None:
        await asyncio.to_thread(self._ensure_bucket_sync)

    async def upload_file(self, local_path: str, destination_key: str, content_type: Optional[str] = None) -> str:
        if not content_type:
            content_type, _ = mimetypes.guess_type(local_path)
            content_type = content_type or "application/octet-stream"

        extra_args = {"ContentType": content_type}

        def _upload() -> None:
            self._ensure_bucket_sync()
            self.client.upload_file(local_path, self.bucket_name, destination_key, ExtraArgs=extra_args)

        await asyncio.to_thread(_upload)
        return await self.get_url(destination_key)

    async def upload_bytes(self, data: bytes, destination_key: str, content_type: Optional[str] = None) -> str:
        content_type = content_type or "application/octet-stream"

        def _upload() -> None:
            self._ensure_bucket_sync()
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=destination_key,
                Body=data,
                ContentType=content_type,
            )

        await asyncio.to_thread(_upload)
        return await self.get_url(destination_key)

    async def download_file(self, remote_key: str, local_path: str) -> None:
        def _download() -> None:
            self.client.download_file(self.bucket_name, remote_key, local_path)

        await asyncio.to_thread(_download)

    async def download_bytes(self, remote_key: str) -> bytes:
        def _download() -> bytes:
            buf = io.BytesIO()
            self.client.download_fileobj(self.bucket_name, remote_key, buf)
            return buf.getvalue()

        return await asyncio.to_thread(_download)

    async def get_url(self, remote_key: str) -> str:
        # If custom endpoint URL is provided (e.g. MinIO), construct path-based URL or presigned URL
        def _url() -> str:
            try:
                # Generate a 24-hour presigned URL for secure access
                return self.client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket_name, "Key": remote_key},
                    ExpiresIn=86400,
                )
            except Exception:
                endpoint = (self.endpoint_url or "https://s3.amazonaws.com").rstrip("/")
                return f"{endpoint}/{self.bucket_name}/{remote_key}"

        return await asyncio.to_thread(_url)

    async def health_check(self) -> bool:
        def _check() -> bool:
            try:
                self.client.head_bucket(Bucket=self.bucket_name)
                return True
            except Exception as e:
                logger.debug(f"S3 health check failed: {e}")
                return False

        return await asyncio.to_thread(_check)
