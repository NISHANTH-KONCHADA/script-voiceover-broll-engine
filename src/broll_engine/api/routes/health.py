from datetime import datetime, timezone
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from broll_engine.repositories.base import JobRepository
from broll_engine.storage.base import StorageAdapter

router = APIRouter(tags=["Health & Diagnostics"])


class LivenessResponse(BaseModel):
    status: str = Field(default="ok", example="ok")
    timestamp: datetime = Field(..., example="2026-11-18T10:00:00Z")
    version: str = Field(default="0.1.0", example="0.1.0")


class ReadinessResponse(BaseModel):
    status: str = Field(default="ready", example="ready")
    timestamp: datetime
    dependencies: Dict[str, bool]


# Dependency injection placeholders (overridden in app.py)
def get_repository() -> JobRepository:
    raise NotImplementedError


def get_storage() -> StorageAdapter:
    raise NotImplementedError


@router.get("/health", response_model=LivenessResponse, summary="Liveness Probe")
@router.get("/api/v1/health", response_model=LivenessResponse, include_in_schema=False)
async def liveness() -> LivenessResponse:
    """Returns basic liveness status confirming process is accepting HTTP traffic."""
    return LivenessResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc),
        version="0.1.0",
    )


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness Probe")
@router.get("/api/v1/ready", response_model=ReadinessResponse, include_in_schema=False)
async def readiness(
    repo: JobRepository = Depends(get_repository),
    storage: StorageAdapter = Depends(get_storage),
) -> ReadinessResponse:
    """Verifies operational readiness of database and object storage dependencies."""
    db_ok = await repo.health_check()
    storage_ok = await storage.health_check()

    is_ready = db_ok and storage_ok
    status_str = "ready" if is_ready else "not_ready"
    timestamp = datetime.now(timezone.utc)

    response = ReadinessResponse(
        status=status_str,
        timestamp=timestamp,
        dependencies={
            "database": db_ok,
            "storage": storage_ok,
        },
    )

    if not is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response.model_dump(mode="json"),
        )

    return response
