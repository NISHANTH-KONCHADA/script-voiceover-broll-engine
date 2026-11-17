from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Structured error payload complying with Integration Standard Point 5."""
    code: str = Field(..., description="UPPER_SNAKE_CASE error identifier", examples=["VALIDATION_ERROR", "JOB_NOT_FOUND"])
    message: str = Field(..., description="Human-readable explanation of error")
    retryable: bool = Field(default=False, description="Whether client should attempt retry")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Detailed diagnostic key-value pairs")


class ErrorResponse(BaseModel):
    """Top-level error wrapper."""
    error: ErrorDetail
