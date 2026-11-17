from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from broll_engine.api.schemas.job import JobStatus


@dataclass
class JobRecord:
    job_id: str
    idempotency_key: Optional[str]
    status: JobStatus
    progress: int
    stage: str
    request_payload: Dict[str, Any]
    outputs: Optional[Dict[str, Any]]
    error: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]


class JobRepository(ABC):
    """Abstract interface for job persistence."""

    @abstractmethod
    async def create_job(
        self,
        job_id: str,
        idempotency_key: Optional[str],
        request_payload: Dict[str, Any],
    ) -> JobRecord:
        """Atomically persists a new job record."""
        pass

    @abstractmethod
    async def get_job(self, job_id: str) -> Optional[JobRecord]:
        """Fetches a job record by its unique ID."""
        pass

    @abstractmethod
    async def get_job_by_idempotency_key(self, key: str) -> Optional[JobRecord]:
        """Retrieves a previously submitted job matching the idempotency key."""
        pass

    @abstractmethod
    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        progress: int,
        stage: str,
        outputs: Optional[Dict[str, Any]] = None,
        error: Optional[Dict[str, Any]] = None,
    ) -> Optional[JobRecord]:
        """Updates progress, stage, outputs, or error details of an existing job."""
        pass

    @abstractmethod
    async def list_jobs(self, limit: int = 50, offset: int = 0) -> List[JobRecord]:
        """Lists recent jobs ordered by creation date descending."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Verifies database connectivity."""
        pass
