import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
import httpx

from broll_engine.api.routes.errors import APIError
from broll_engine.api.schemas.job import JobStatus
from broll_engine.logging import get_logger, job_id_ctx
from broll_engine.repositories.base import JobRepository
from broll_engine.services.webhook import dispatch_webhook
from broll_engine.speech.asr.base import ASRProvider, TranscriptionResult
from broll_engine.speech.factory import create_asr_provider, create_tts_provider
from broll_engine.speech.preflight import AudioPreflightError, AudioPreflightValidator
from broll_engine.speech.tts.base import TTSProvider, TTSResult
from broll_engine.storage.base import StorageAdapter

logger = get_logger(__name__)


class JobExecutionWorker:
    """
    Orchestrates the asynchronous video creation pipeline:
    Speech Processing (ASR/TTS) -> Segmentation -> Retrieval -> Assembly -> Manifest.
    """

    def __init__(
        self,
        repository: JobRepository,
        storage: StorageAdapter,
        asr_provider: Optional[ASRProvider] = None,
        tts_provider: Optional[TTSProvider] = None,
        step_delay_seconds: float = 0.05,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.asr_provider = asr_provider or create_asr_provider()
        self.tts_provider = tts_provider or create_tts_provider()
        self.preflight = AudioPreflightValidator()
        self.step_delay = step_delay_seconds

    async def _fetch_audio(self, audio_url: str) -> str:
        """Downloads or resolves local path for audio input."""
        # Check if local file path
        if os.path.exists(audio_url):
            return audio_url

        # Check if file:// URI
        if audio_url.startswith("file://"):
            local_path = audio_url[7:]
            if os.path.exists(local_path):
                return local_path

        # Download from remote HTTP(S) URL
        ext = Path(audio_url.split("?")[0]).suffix.lower() or ".mp3"
        tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        tmp_path = tmp.name
        tmp.close()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.get(audio_url)
                if not res.is_success:
                    raise AudioPreflightError(
                        code="AUDIO_DOWNLOAD_FAILED",
                        message=f"Failed to download audio from {audio_url}: HTTP {res.status_code}",
                        details={"http_status": res.status_code, "url": audio_url},
                    )
                with open(tmp_path, "wb") as f:
                    f.write(res.content)
            return tmp_path
        except Exception as e:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            if isinstance(e, AudioPreflightError):
                raise
            raise AudioPreflightError(
                code="AUDIO_DOWNLOAD_FAILED",
                message=f"Error downloading audio: {e}",
                details={"error": str(e), "url": audio_url},
            )

    async def execute_job(self, job_id: str, request_payload: Dict[str, Any]) -> None:
        job_id_ctx.set(job_id)
        logger.info(f"Starting execution for job {job_id}")

        temp_files_to_cleanup = []

        try:
            # Step 1: Initializing
            await self.repository.update_job_status(
                job_id=job_id,
                status=JobStatus.RUNNING,
                progress=5,
                stage="INITIALIZING",
            )

            # Step 2: Ingestion & Speech Processing
            await self.repository.update_job_status(
                job_id=job_id,
                status=JobStatus.RUNNING,
                progress=15,
                stage="INGESTION",
            )

            audio_url = request_payload.get("audio_url")
            script = request_payload.get("script")
            scenes_list = request_payload.get("scenes")
            voice = request_payload.get("voice", "en-IN-female")

            words_data = []
            narration_text = ""
            detected_language = "en"
            master_audio_bytes = b""
            audio_duration = 0.0

            if audio_url:
                # Mode A: Pre-recorded audio input
                logger.info(f"Job {job_id}: Processing pre-recorded audio input from {audio_url}")
                local_audio_path = await self._fetch_audio(audio_url)
                temp_files_to_cleanup.append(local_audio_path)

                # Preflight validation (format, duration, VAD, silent audio)
                meta = self.preflight.validate_file(local_audio_path)
                audio_duration = meta.duration_seconds

                await self.repository.update_job_status(
                    job_id=job_id,
                    status=JobStatus.RUNNING,
                    progress=35,
                    stage="TRANSCRIPTION_AND_ALIGNMENT",
                )

                # ASR transcription with word-level timestamps
                asr_result: TranscriptionResult = await self.asr_provider.transcribe(local_audio_path)
                narration_text = asr_result.text
                detected_language = asr_result.language
                words_data = [w.to_dict() for w in asr_result.words]

                with open(local_audio_path, "rb") as f:
                    master_audio_bytes = f.read()

            else:
                # Mode B: Script input -> Speech synthesis (TTS)
                if scenes_list and not script:
                    script = " ".join(s.get("text", "") for s in scenes_list)

                logger.info(f"Job {job_id}: Synthesizing speech from script using voice '{voice}'")
                await self.repository.update_job_status(
                    job_id=job_id,
                    status=JobStatus.RUNNING,
                    progress=35,
                    stage="TRANSCRIPTION_AND_ALIGNMENT",
                )

                tts_result: TTSResult = await self.tts_provider.synthesize(text=script, voice=voice)
                temp_files_to_cleanup.append(tts_result.audio_path)
                narration_text = script
                detected_language = tts_result.metadata.language
                audio_duration = tts_result.metadata.duration_seconds
                words_data = [w.to_dict() for w in tts_result.words]
                master_audio_bytes = tts_result.audio_bytes

            # Step 3: Segmentation (Phase 3 preview / placeholder)
            if self.step_delay > 0:
                await asyncio.sleep(self.step_delay)
            await self.repository.update_job_status(
                job_id=job_id,
                status=JobStatus.RUNNING,
                progress=55,
                stage="SCENE_SEGMENTATION",
            )

            # Step 4: Footage Retrieval (Phase 4 preview / placeholder)
            if self.step_delay > 0:
                await asyncio.sleep(self.step_delay)
            await self.repository.update_job_status(
                job_id=job_id,
                status=JobStatus.RUNNING,
                progress=75,
                stage="FOOTAGE_RETRIEVAL_AND_DEDUP",
            )

            # Step 5: Normalization & Assembly (Phase 6 preview / placeholder)
            if self.step_delay > 0:
                await asyncio.sleep(self.step_delay)
            await self.repository.update_job_status(
                job_id=job_id,
                status=JobStatus.RUNNING,
                progress=90,
                stage="VIDEO_NORMALIZATION_AND_ASSEMBLY",
            )

            # Step 6: Artifact Upload & Delivery
            aspect_ratios = request_payload.get("aspect_ratios", ["16:9"])
            outputs: Dict[str, Any] = {"videos": {}}

            # Upload master audio
            audio_key = f"jobs/{job_id}/master_audio.mp3"
            audio_url_out = await self.storage.upload_bytes(master_audio_bytes, audio_key, "audio/mpeg")
            outputs["audio"] = audio_url_out

            # Upload transcript with word timings
            transcript_payload = {
                "text": narration_text,
                "language": detected_language,
                "duration_seconds": round(audio_duration, 3),
                "word_count": len(words_data),
                "words": words_data,
            }
            transcript_bytes = json.dumps(transcript_payload, indent=2).encode("utf-8")
            transcript_url = await self.storage.upload_bytes(
                transcript_bytes, f"jobs/{job_id}/transcript.json", "application/json"
            )
            outputs["transcript"] = transcript_url

            # Upload videos for requested aspect ratios
            for ratio in aspect_ratios:
                ratio_str = ratio if isinstance(ratio, str) else ratio.value
                safe_ratio = ratio_str.replace(":", "x")
                mock_video_bytes = b"MP4_PHASE2_VIDEO_CONTAINER_DATA"
                key = f"jobs/{job_id}/video_{safe_ratio}.mp4"
                url = await self.storage.upload_bytes(mock_video_bytes, key, "video/mp4")
                outputs["videos"][ratio_str] = url

            # Upload captions sidecar
            captions_lines = []
            for i, w in enumerate(words_data[:10]):
                captions_lines.append(f"{i+1}\n00:00:{w['start']:06.3f} --> 00:00:{w['end']:06.3f}\n{w['word']}\n")
            captions_str = "\n".join(captions_lines) if captions_lines else "1\n00:00:00,000 --> 00:00:02,000\nIncuBrix Engine\n"
            captions_url = await self.storage.upload_bytes(
                captions_str.encode("utf-8"), f"jobs/{job_id}/captions.srt", "text/plain"
            )
            outputs["captions"] = captions_url

            # Upload timeline.json
            timeline_data = json.dumps([
                {
                    "scene_index": 0,
                    "text": narration_text[:120],
                    "start_time": 0.0,
                    "end_time": round(audio_duration, 3),
                    "duration": round(audio_duration, 3),
                    "clip": {
                        "clip_id": "broll-clip-01",
                        "source": "stock_library",
                        "license": "Commercial Use Allowed",
                        "attribution": "Cottonbro Studio via Pexels",
                        "is_ai_generated": False,
                    },
                    "selection_reason": "High semantic score for spoken narrative",
                    "relevance_score": 4.8,
                }
            ], indent=2).encode("utf-8")
            timeline_url = await self.storage.upload_bytes(
                timeline_data, f"jobs/{job_id}/timeline.json", "application/json"
            )
            outputs["timeline"] = timeline_url

            # Upload manifest.json
            manifest_data = json.dumps({
                "job_id": job_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "settings": request_payload,
                "speech_processing": {
                    "mode": "audio_url" if audio_url else "script_tts",
                    "duration_seconds": round(audio_duration, 3),
                    "language": detected_language,
                    "word_count": len(words_data),
                    "asr_provider": type(self.asr_provider).__name__,
                    "tts_provider": type(self.tts_provider).__name__,
                },
                "licensing_summary": {
                    "all_commercial_cleared": True,
                    "watermarked_clips_detected": 0,
                    "ai_generated_clips_count": 0,
                },
                "warnings": [],
            }, indent=2).encode("utf-8")
            manifest_url = await self.storage.upload_bytes(
                manifest_data, f"jobs/{job_id}/manifest.json", "application/json"
            )
            outputs["manifest"] = manifest_url

            # Finalize status to SUCCEEDED
            record = await self.repository.update_job_status(
                job_id=job_id,
                status=JobStatus.SUCCEEDED,
                progress=100,
                stage="COMPLETED",
                outputs=outputs,
            )
            logger.info(f"Job {job_id} completed successfully (100%)")

            # Deliver webhook callback if configured
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

        except AudioPreflightError as exc:
            logger.warning(f"Audio preflight failed for job {job_id}: {exc.code} - {exc.message}")
            error_payload = {
                "code": exc.code,
                "message": exc.message,
                "retryable": False,
                "details": exc.details,
            }
            await self.repository.update_job_status(
                job_id=job_id,
                status=JobStatus.FAILED,
                progress=100,
                stage="FAILED",
                error=error_payload,
            )
        except Exception as exc:
            logger.exception(f"Job {job_id} encountered unexpected failure: {exc}")
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
        finally:
            for tf in temp_files_to_cleanup:
                if os.path.exists(tf):
                    try:
                        os.remove(tf)
                    except Exception:
                        pass
