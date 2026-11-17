import uuid
from typing import Any, Dict, List, Optional
from broll_engine.api.schemas.job import (
    JobCreateRequest,
    JobCreateResponse,
    JobDetailResponse,
    JobOutputs,
    JobStatus,
)
from broll_engine.logging import get_logger
from broll_engine.repositories.base import JobRecord, JobRepository
from broll_engine.worker.execution import JobExecutionWorker

logger = get_logger(__name__)


class JobService:
    """Business logic orchestrator managing job lifecycle, idempotency, and background dispatch."""

    def __init__(self, repository: JobRepository, worker: JobExecutionWorker) -> None:
        self.repository = repository
        self.worker = worker

    def _generate_job_id(self) -> str:
        return f"broll_{uuid.uuid4().hex[:12]}"

    def _record_to_detail_response(self, record: JobRecord) -> JobDetailResponse:
        outputs = None
        if record.outputs:
            outputs = JobOutputs(
                videos=record.outputs.get("videos", {}),
                captions=record.outputs.get("captions"),
                timeline=record.outputs.get("timeline"),
                manifest=record.outputs.get("manifest"),
            )

        return JobDetailResponse(
            job_id=record.job_id,
            status=record.status,
            progress=record.progress,
            stage=record.stage,
            created_at=record.created_at,
            updated_at=record.updated_at,
            completed_at=record.completed_at,
            outputs=outputs,
            error=record.error,
        )

    async def submit_job(
        self,
        request: JobCreateRequest,
        idempotency_key: Optional[str] = None,
        background_tasks: Optional[Any] = None,
    ) -> tuple[JobCreateResponse, bool]:
        """
        Submits or deduplicates a B-roll creation job.
        Returns (JobCreateResponse, is_duplicate).
        """
        # Step 1: Idempotency check
        if idempotency_key:
            existing_record = await self.repository.get_job_by_idempotency_key(idempotency_key)
            if existing_record:
                logger.info(
                    f"Idempotent request detected for key '{idempotency_key}'; returning existing job {existing_record.job_id}"
                )
                return (
                    JobCreateResponse(
                        job_id=existing_record.job_id,
                        status=existing_record.status,
                        progress=existing_record.progress,
                        created_at=existing_record.created_at,
                        check_status_url=f"/api/v1/jobs/{existing_record.job_id}",
                    ),
                    True,
                )

        # Step 2: Create new job record
        job_id = self._generate_job_id()
        payload_dict = request.model_dump(mode="json")

        record = await self.repository.create_job(
            job_id=job_id,
            idempotency_key=idempotency_key,
            request_payload=payload_dict,
        )

        # Step 3: Trigger async execution
        if background_tasks:
            background_tasks.add_task(self.worker.execute_job, job_id, payload_dict)
        else:
            # Fallback if no FastAPI background_tasks object passed (e.g. CLI/tests)
            import asyncio
            asyncio.create_task(self.worker.execute_job, job_id, payload_dict)

        logger.info(f"Enqueued new job {job_id} (idempotency_key={idempotency_key})")
        return (
            JobCreateResponse(
                job_id=record.job_id,
                status=record.status,
                progress=record.progress,
                created_at=record.created_at,
                check_status_url=f"/api/v1/jobs/{record.job_id}",
            ),
            False,
        )

    async def get_job(self, job_id: str) -> Optional[JobDetailResponse]:
        record = await self.repository.get_job(job_id)
        if not record:
            return None
        return self._record_to_detail_response(record)

    async def list_jobs(self, limit: int = 50, offset: int = 0) -> List[JobDetailResponse]:
        records = await self.repository.list_jobs(limit=limit, offset=offset)
        return [self._record_to_detail_response(r) for r in records]
