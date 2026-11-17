from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, Header, Response, status

from broll_engine.api.routes.errors import APIError
from broll_engine.api.schemas.job import (
    JobCreateRequest,
    JobCreateResponse,
    JobDetailResponse,
)
from broll_engine.logging import get_logger
from broll_engine.services.job_service import JobService

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["B-roll Jobs"])


def get_job_service() -> JobService:
    raise NotImplementedError


@router.post(
    "/broll/jobs",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit B-roll Video Generation Job",
    description="Asynchronously queues video generation from audio or script. Enforces Idempotency-Key header for safe retries.",
)
async def create_broll_job(
    request: JobCreateRequest,
    background_tasks: BackgroundTasks,
    response: Response,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", description="Unique client key for safe request retry"),
    service: JobService = Depends(get_job_service),
) -> JobCreateResponse:
    job_response, is_duplicate = await service.submit_job(
        request=request,
        idempotency_key=idempotency_key,
        background_tasks=background_tasks,
    )

    if is_duplicate:
        response.headers["X-Idempotent-Replay"] = "true"

    return job_response


@router.get(
    "/jobs/{job_id}",
    response_model=JobDetailResponse,
    summary="Get Job Status and Results",
    description="Returns processing status, progress percentage (0-100), stage, and output download links.",
)
async def get_job_status(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> JobDetailResponse:
    job = await service.get_job(job_id)
    if not job:
        raise APIError(
            code="JOB_NOT_FOUND",
            message=f"Job with ID '{job_id}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            retryable=False,
            details={"job_id": job_id},
        )
    return job


@router.get(
    "/jobs",
    response_model=List[JobDetailResponse],
    summary="List Recent Jobs",
    description="Returns a paginated list of recently submitted jobs.",
)
async def list_jobs(
    limit: int = 50,
    offset: int = 0,
    service: JobService = Depends(get_job_service),
) -> List[JobDetailResponse]:
    return await service.list_jobs(limit=limit, offset=offset)
