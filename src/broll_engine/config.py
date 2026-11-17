from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Server settings
    app_env: str = Field(default="development", description="Runtime environment (development, staging, production, test)")
    app_debug: bool = Field(default=False, description="Enable debug mode")
    app_host: str = Field(default="0.0.0.0", description="Host to bind API server")
    app_port: int = Field(default=8000, description="Port to bind API server")
    log_level: str = Field(default="INFO", description="Log level (DEBUG, INFO, WARNING, ERROR)")

    # Webhook signature secret
    webhook_secret: str = Field(
        default="default-test-webhook-hmac-secret-key-32chars",
        description="HMAC secret used to sign outbound callback notifications"
    )

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///data/jobs.db",
        description="Async SQLAlchemy database URL (SQLite or PostgreSQL)"
    )

    # Object storage (S3 / MinIO)
    s3_endpoint_url: Optional[str] = Field(default="http://localhost:9000", description="S3 / MinIO endpoint URL")
    s3_access_key_id: str = Field(default="minioadmin", description="S3 access key ID")
    s3_secret_access_key: str = Field(default="minioadmin", description="S3 secret access key")
    s3_bucket_name: str = Field(default="broll-engine-bucket", description="S3 bucket name for uploads & outputs")
    s3_region: str = Field(default="us-east-1", description="S3 region")
    s3_secure: bool = Field(default=False, description="Use SSL/TLS for S3 connections")

    # Processing limits & defaults
    max_audio_duration_seconds: int = Field(default=600, description="Maximum accepted audio duration in seconds")
    min_scene_duration_seconds: float = Field(default=1.8, description="Minimum scene length in seconds")
    max_scene_duration_seconds: float = Field(default=5.0, description="Maximum scene length in seconds")
    default_fps: int = Field(default=30, description="Standard video output framerate")

    # External APIs (Optional/mockable)
    pexels_api_key: Optional[str] = Field(default=None, description="Pexels Video API Key")
    pixabay_api_key: Optional[str] = Field(default=None, description="Pixabay Video API Key")
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API Key")
    gemini_api_key: Optional[str] = Field(default=None, description="Google Gemini API Key")


# Global singleton instance
settings = Settings()
