import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from broll_engine.api.schemas.job import JobStatus
from broll_engine.logging import get_logger, job_id_ctx
from broll_engine.repositories.base import JobRepository
from broll_engine.services.webhook import dispatch_webhook
from broll_engine.storage.base import StorageAdapter

logger = get_logger(__name__)


class JobExecutionWorker:
    """Orchestrates asynchronous pipeline execution with step-by-step progress tracking."""

    def __init__(
        self,
        repository: JobRepository,
        storage: StorageAdapter,
        step_delay_seconds: float = 0.2,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.step_delay = step_delay_seconds

    async def execute_job(self, job_id: str, request_payload: Dict[str, Any]) -> None:
        job_id_ctx.set(job_id)
        logger.info(f"Starting execution for job {job_id}")

        stages = [
            ("INGESTION", 15),
            ("TRANSCRIPTION_AND_ALIGNMENT", 35),
            ("SCENE_SEGMENTATION", 55),
            ("FOOTAGE_RETRIEVAL_AND_DEDUP", 75),
            ("VIDEO_NORMALIZATION_AND_ASSEMBLY", 90),
        ]

        try:
            # Transition to RUNNING
            await self.repository.update_job_status(
                job_id=job_id,
                status=JobStatus.RUNNING,
                progress=5,
                stage="INITIALIZING",
            )

            for stage_name, target_progress in stages:
                if self.step_delay > 0:
                    await asyncio.sleep(self.step_delay)
                await self.repository.update_job_status(
                    job_id=job_id,
                    status=JobStatus.RUNNING,
                    progress=target_progress,
                    stage=stage_name,
                )
                logger.info(f"Job {job_id} reached stage {stage_name} ({target_progress}%)")

            # Phase 1: Generate and upload initial mock manifest and placeholder artifacts to storage
            aspect_ratios = request_payload.get("aspect_ratios", ["16:9"])
            outputs: Dict[str, Any] = {"videos": {}}

            # Upload mock videos
            for ratio in aspect_ratios:
                ratio_str = ratio if isinstance(ratio, str) else ratio.value
                safe_ratio = ratio_str.replace(":", "x")
                mock_video_bytes = b"MP4_PHASE1_PLACEHOLDER_VIDEO_DATA"
                key = f"jobs/{job_id}/video_{safe_ratio}.mp4"
                url = await self.storage.upload_bytes(mock_video_bytes, key, "video/mp4")
                outputs["videos"][ratio_str] = url

            # Upload captions sidecar
            captions_data = "1\n00:00:00,000 --> 00:00:02,500\nIncuBrix video engine ready.\n".encode("utf-8")
            captions_url = await self.storage.upload_bytes(captions_data, f"jobs/{job_id}/captions.srt", "text/plain")
            outputs["captions"] = captions_url

            # Upload timeline.json
            timeline_data = json.dumps([
                {
                    "scene_index": 0,
                    "text": request_payload.get("script") or "Engine test scene.",
                    "start_time": 0.0,
                    "end_time": 2.5,
                    "duration": 2.5,
                    "clip": {
                        "clip_id": "test-clip-01",
                        "source": "procedural_mock",
                        "license": "Creative Commons Zero",
                        "attribution": "IncuBrix Test Harness",
                        "is_ai_generated": False,
                    },
                    "selection_reason": "Phase 1 initial pipeline verification",
                    "relevance_score": 5.0,
                }
            ], indent=2).encode("utf-8")
            timeline_url = await self.storage.upload_bytes(timeline_data, f"jobs/{job_id}/timeline.json", "application/json")
            outputs["timeline"] = timeline_url

            # Upload manifest.json
            manifest_data = json.dumps({
                "job_id": job_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "settings": request_payload,
                "models_and_providers": {
                    "engine_phase": "Phase 1: Foundation and Integration",
                    "storage": "S3-compatible MinIO",
                },
                "licensing_summary": {"all_commercial_cleared": True},
                "warnings": [],
            }, indent=2).encode("utf-8")
            manifest_url = await self.storage.upload_bytes(manifest_data, f"jobs/{job_id}/manifest.json", "application/json")
            outputs["manifest"] = manifest_url

            # Transition to SUCCEEDED
            record = await self.repository.update_job_status(
                job_id=job_id,
                status=JobStatus.SUCCEEDED,
                progress=100,
                stage="COMPLETED",
                outputs=outputs,
            )
            logger.info(f"Job {job_id} completed successfully (100%)")

            # Dispatch webhook callback if requested
            callback_url = request_payload.get("callback_url")
            if callback_url and record:
                payload = {
                    "job_id": record.job_id,
                    "status": record.status.value,
                    "progress": record.progress,
                    "outputs": record.outputs,
                    "completed_at": record.completed_at.isoformat() if record.completed_at else None,
                }
                await dispatch_webhook(callback_url, payload)

        except Exception as exc:
            logger.exception(f"Job {job_id} failed: {exc}")
            error_payload = {
                "code": "INTERNAL_PROCESSING_ERROR",
                "message": str(exc),
                "retryable": True,
                "details": {"exception_type": type(exc).__name__},
            }
            await self.repository.update_job_status(
                job_id=job_id,
                status=JobStatus.FAILED,
                progress=100,
                stage="FAILED",
                error=error_payload,
            )
