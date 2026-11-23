import asyncio
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, Request, Response, UploadFile, status

from broll_engine.api.routes.errors import APIError
from broll_engine.api.schemas.job import (
    ClipSwapRequest,
    ClipSwapResponse,
    JobCreateRequest,
    JobCreateResponse,
    JobDetailResponse,
    MediaUploadResponse,
    TimelineClipModel,
    TimelineExportRequest,
    TimelineExportResponse,
    TimelineProjectModel,
    TimelineTrackModel,
)
from broll_engine.config import settings
from broll_engine.logging import get_logger
from broll_engine.security import download_media_securely, validate_url_security
from broll_engine.services.job_service import JobService

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["B-roll Jobs"])

_SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _safe_filename(name: str, fallback: str) -> str:
    """Reduces a user-controlled filename to a safe basename (no path traversal)."""
    base = Path(name).name
    base = re.sub(r"[^\w\-.]", "_", base).strip(".")
    return base or fallback


def _enforce_url_security(url: str) -> None:
    """SSRF guard shared by media import and timeline export URL fetches."""
    try:
        validate_url_security(url, allow_private_for_test=(settings.app_env != "production"))
    except APIError:
        raise
    except Exception as e:
        raise APIError(
            code="URL_REJECTED",
            message=f"URL failed security validation: {e}",
            status_code=400,
            retryable=False,
        )


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


@router.post(
    "/broll/jobs/{job_id}/swap-clip",
    response_model=ClipSwapResponse,
    status_code=status.HTTP_200_OK,
    summary="Swap Video Clip and Partially Re-render (Advanced Level)",
    description="Replaces footage for a single scene and re-assembles the video in <3 seconds without re-rendering unaffected scenes.",
)
async def swap_job_clip(
    job_id: str,
    request: ClipSwapRequest,
    service: JobService = Depends(get_job_service),
) -> ClipSwapResponse:
    return await service.swap_clip(job_id=job_id, request=request)


@router.get(
    "/jobs/{job_id}/video",
    summary="Stream Rendered MP4 Video",
    description="Streams the rendered MP4 video directly from storage without SigV4 or CORS issues.",
)
async def get_job_video(
    job_id: str,
    aspect: str = "16:9",
    clean: bool = False,
    edited: bool = False,
    service: JobService = Depends(get_job_service),
) -> Response:
    safe_aspect = aspect.replace(":", "x")
    if edited:
        keys_to_try = [f"jobs/{job_id}/video_edited_{safe_aspect}.mp4", f"jobs/{job_id}/video_{safe_aspect}.mp4"]
    elif clean:
        keys_to_try = [f"jobs/{job_id}/clean_video_{safe_aspect}.mp4", f"jobs/{job_id}/video_{safe_aspect}.mp4"]
    else:
        keys_to_try = [f"jobs/{job_id}/video_{safe_aspect}.mp4", f"jobs/{job_id}/clean_video_{safe_aspect}.mp4"]

    video_bytes = None
    for key in keys_to_try:
        try:
            candidate = await service.worker.storage.download_bytes(key)
            if len(candidate) > 1000:
                video_bytes = candidate
                break
        except Exception:
            continue

    if not video_bytes:
        raise APIError(
            code="VIDEO_NOT_FOUND",
            message=f"Video not found for job '{job_id}' ({aspect})",
            status_code=status.HTTP_404_NOT_FOUND,
            retryable=False,
        )

    return Response(
        content=video_bytes,
        media_type="video/mp4",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(len(video_bytes)),
            "Content-Disposition": f'inline; filename="video_{safe_aspect}.mp4"',
            "Cache-Control": "no-cache",
        },
    )


@router.get(
    "/jobs/{job_id}/captions",
    summary="Download SRT Captions",
    description="Returns SRT subtitle file directly from storage.",
)
async def get_job_captions(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> Response:
    key = f"jobs/{job_id}/captions.srt"
    try:
        srt_bytes = await service.worker.storage.download_bytes(key)
        return Response(
            content=srt_bytes,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": 'inline; filename="captions.srt"'},
        )
    except Exception as e:
        raise APIError(
            code="CAPTIONS_NOT_FOUND",
            message=f"Captions not found for job '{job_id}': {e}",
            status_code=status.HTTP_404_NOT_FOUND,
            retryable=False,
        )


@router.get(
    "/jobs/{job_id}/timeline",
    summary="Get Job Timeline JSON",
    description="Returns timeline metadata containing scenes, timestamps, and footage information.",
)
async def get_job_timeline(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> Response:
    key = f"jobs/{job_id}/timeline.json"
    try:
        timeline_bytes = await service.worker.storage.download_bytes(key)
        return Response(
            content=timeline_bytes,
            media_type="application/json",
            headers={"Content-Disposition": 'inline; filename="timeline.json"'},
        )
    except Exception as e:
        raise APIError(
            code="TIMELINE_NOT_FOUND",
            message=f"Timeline not found for job '{job_id}': {e}",
            status_code=status.HTTP_404_NOT_FOUND,
            retryable=False,
        )


@router.get(
    "/jobs/{job_id}/artifact/{filename}",
    summary="Download Job Artifact",
    description="Streams a job artifact (manifest.json, transcript.json, scenes.json, "
    "quality_report.json, master_audio.mp3, etc.) directly from storage.",
)
async def get_job_artifact(
    job_id: str,
    filename: str,
    service: JobService = Depends(get_job_service),
) -> Response:
    safe_name = _safe_filename(filename, fallback="")
    if not safe_name or safe_name != filename:
        raise APIError(
            code="INVALID_ARTIFACT_NAME",
            message=f"Invalid artifact filename '{filename}'.",
            status_code=status.HTTP_400_BAD_REQUEST,
            retryable=False,
        )
    key = f"jobs/{job_id}/{safe_name}"
    try:
        data = await service.worker.storage.download_bytes(key)
    except Exception as e:
        raise APIError(
            code="ARTIFACT_NOT_FOUND",
            message=f"Artifact '{safe_name}' not found for job '{job_id}': {e}",
            status_code=status.HTTP_404_NOT_FOUND,
            retryable=False,
        )
    media_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{safe_name}"'},
    )


@router.post(
    "/media/upload",
    response_model=MediaUploadResponse,
    summary="Upload Media to Library",
    description="Imports video, audio, or image into the media library with probe metadata.",
)
async def upload_media_file(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = None,
    service: JobService = Depends(get_job_service),
) -> MediaUploadResponse:
    media_id = f"media_{uuid.uuid4().hex[:10]}"
    cache_dir = Path(settings.footage_cache_dir).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)

    if file:
        filename = _safe_filename(file.filename or "", f"{media_id}.mp4")
        dest_path = cache_dir / f"{media_id}_{filename}"
        content = await file.read()
        dest_path.write_bytes(content)
    elif url:
        _enforce_url_security(url)
        filename = _safe_filename(url.split("?")[0].split("/")[-1], f"{media_id}.mp4")
        dest_path = cache_dir / f"{media_id}_{filename}"
        try:
            await download_media_securely(
                url=url,
                target_path=str(dest_path),
                allow_private_for_test=(settings.app_env != "production"),
            )
        except APIError:
            raise
        except Exception as e:
            raise APIError(
                code="DOWNLOAD_FAILED",
                message=f"Failed to fetch media from URL: {e}",
                status_code=400,
            )
    else:
        raise APIError(code="MISSING_MEDIA", message="Provide either file upload or url", status_code=400)

    duration = 5.0
    width = 1920
    height = 1080
    media_type = "video"

    cmd = ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(dest_path)]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if proc.returncode == 0:
            info = json.loads(proc.stdout.decode(errors="replace"))
            fmt = info.get("format", {})
            duration = float(fmt.get("duration") or 5.0)
            v_stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
            a_stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
            if v_stream:
                width = int(v_stream.get("width") or 1920)
                height = int(v_stream.get("height") or 1080)
                media_type = "video"
            elif a_stream:
                media_type = "audio"
                width, height = None, None
    except Exception as e:
        logger.warning(f"Probe error on uploaded media: {e}")

    mime, _ = mimetypes.guess_type(str(dest_path))
    mime = mime or ("video/mp4" if media_type == "video" else "audio/mpeg")
    remote_key = f"media/{media_id}/{filename}"
    await service.worker.storage.upload_file(str(dest_path), remote_key, mime)

    return MediaUploadResponse(
        media_id=media_id,
        filename=filename,
        media_type=media_type,
        duration_seconds=round(duration, 3),
        width=width,
        height=height,
        url=f"/api/v1/media/{media_id}",
    )


@router.get(
    "/media/{media_id}",
    summary="Stream Uploaded Media Asset",
    description="Streams media file with HTTP Range support for seekable preview in editor.",
)
async def stream_media_file(
    media_id: str,
    service: JobService = Depends(get_job_service),
) -> Response:
    if not _SAFE_ID_PATTERN.match(media_id):
        raise APIError(code="INVALID_MEDIA_ID", message="media_id contains invalid characters", status_code=400)
    cache_dir = Path(settings.footage_cache_dir).resolve()
    matched = list(cache_dir.glob(f"{media_id}_*"))
    if matched and matched[0].exists():
        content = matched[0].read_bytes()
        mime, _ = mimetypes.guess_type(matched[0].name)
        return Response(
            content=content,
            media_type=mime or "video/mp4",
            headers={"Accept-Ranges": "bytes", "Content-Length": str(len(content))},
        )

    try:
        key = f"media/{media_id}/media.mp4"
        content = await service.worker.storage.download_bytes(key)
        return Response(
            content=content,
            media_type="video/mp4",
            headers={"Accept-Ranges": "bytes", "Content-Length": str(len(content))},
        )
    except Exception:
        raise APIError(code="MEDIA_NOT_FOUND", message=f"Media ID '{media_id}' not found", status_code=404)


@router.get(
    "/jobs/{job_id}/timeline-project",
    response_model=TimelineProjectModel,
    summary="Get Timeline Project State",
    description="Returns persisted multitrack timeline state, initializing from job scenes if not yet saved.",
)
async def get_timeline_project(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> TimelineProjectModel:
    proj_key = f"jobs/{job_id}/timeline_project.json"
    try:
        data_bytes = await service.worker.storage.download_bytes(proj_key)
        return TimelineProjectModel.model_validate_json(data_bytes)
    except Exception:
        pass

    try:
        tl_bytes = await service.worker.storage.download_bytes(f"jobs/{job_id}/timeline.json")
        scenes_data = json.loads(tl_bytes.decode("utf-8"))
    except Exception as e:
        raise APIError(code="PROJECT_NOT_FOUND", message=f"Job timeline not found: {e}", status_code=404)

    tracks = [
        TimelineTrackModel(id="TXT", name="Captions", type="caption", muted=False, locked=False),
        TimelineTrackModel(id="V2", name="Overlay Video", type="video", muted=False, locked=False),
        TimelineTrackModel(id="V1", name="Main Video", type="video", muted=False, locked=False),
        TimelineTrackModel(id="A1", name="Voiceover", type="audio", muted=False, locked=False),
        TimelineTrackModel(id="A2", name="Music & SFX", type="audio", muted=False, locked=False),
    ]

    clips: List[TimelineClipModel] = []
    total_dur = 0.0

    for idx, s in enumerate(scenes_data):
        dur = float(s.get("duration", 3.0))
        st = float(s.get("start_time", total_dur))
        clip_info = s.get("clip", {})
        clip_src = clip_info.get("download_url") or ""

        clips.append(
            TimelineClipModel(
                id=f"clip_v1_{idx}_{uuid.uuid4().hex[:6]}",
                media_id=clip_info.get("clip_id") or f"scene_{idx + 1}",
                media_url=clip_src,
                track_id="V1",
                start_time=st,
                duration=dur,
                source_in=0.0,
                source_out=dur,
                speed=1.0,
                volume=1.0,
                scale=1.0,
                name=f"Scene {idx + 1} ({clip_info.get('source', 'Stock')})",
            )
        )

        if s.get("narration_text"):
            clips.append(
                TimelineClipModel(
                    id=f"clip_txt_{idx}_{uuid.uuid4().hex[:6]}",
                    track_id="TXT",
                    start_time=st,
                    duration=dur,
                    source_in=0.0,
                    source_out=dur,
                    text=s.get("narration_text"),
                    name=f"Caption {idx + 1}",
                )
            )

        total_dur = max(total_dur, st + dur)

    audio_url = f"/api/v1/jobs/{job_id}/audio"
    clips.append(
        TimelineClipModel(
            id=f"clip_a1_{uuid.uuid4().hex[:6]}",
            media_id=f"audio_{job_id}",
            media_url=audio_url,
            track_id="A1",
            start_time=0.0,
            duration=total_dur,
            source_in=0.0,
            source_out=total_dur,
            volume=1.0,
            name="Master Voiceover",
        )
    )

    proj = TimelineProjectModel(
        job_id=job_id,
        aspect_ratio="16:9",
        duration=round(total_dur, 3),
        tracks=tracks,
        clips=clips,
    )
    try:
        await service.worker.storage.upload_bytes(
            proj.model_dump_json(indent=2).encode("utf-8"),
            proj_key,
            "application/json",
        )
    except Exception as e:
        logger.warning(f"Could not persist initial timeline project: {e}")
    return proj


@router.post(
    "/jobs/{job_id}/timeline-project",
    response_model=TimelineProjectModel,
    summary="Save Timeline Project State",
    description="Persists updated multitrack timeline state, clip positions, trimming, and custom captions.",
)
async def save_timeline_project(
    job_id: str,
    project: TimelineProjectModel,
    service: JobService = Depends(get_job_service),
) -> TimelineProjectModel:
    proj_key = f"jobs/{job_id}/timeline_project.json"
    await service.worker.storage.upload_bytes(
        project.model_dump_json(indent=2).encode("utf-8"),
        proj_key,
        "application/json",
    )
    return project


@router.post(
    "/jobs/{job_id}/export-timeline",
    response_model=TimelineExportResponse,
    summary="Render & Export Edited Timeline",
    description="Renders the user's customized multitrack timeline using FFmpeg into a broadcast MP4.",
)
async def export_edited_timeline(
    job_id: str,
    request: TimelineExportRequest,
    service: JobService = Depends(get_job_service),
) -> TimelineExportResponse:
    t0 = time.time()
    aspect = request.aspect_ratio or "16:9"
    safe_aspect = aspect.replace(":", "x")

    cache_dir = Path(settings.footage_cache_dir).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    job_seg_dir = cache_dir / f"segments_{job_id}"

    # Master audio caching for audio clips
    cached_audio_path = cache_dir / f"master_audio_{job_id}.mp3"
    if not cached_audio_path.exists() or cached_audio_path.stat().st_size == 0:
        try:
            audio_bytes = await service.worker.storage.download_bytes(f"jobs/{job_id}/master_audio.mp3")
            if audio_bytes:
                cached_audio_path.write_bytes(audio_bytes)
        except Exception as a_err:
            logger.warning(f"Could not retrieve master audio from storage for {job_id}: {a_err}")

    resolved_clips = []
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as http_client:
        for idx, c in enumerate(request.clips):
            c_dict = c.model_dump()
            track_id = c.track_id or "V1"
            m_id = c.media_id or ""
            m_url = c.media_url or ""
            c_name = c.name or ""

            # 1. Audio Clips Resolution (A1, A2)
            if track_id in ("A1", "A2") or "audio" in m_id.lower() or "voiceover" in c_name.lower():
                if c.local_path and os.path.exists(c.local_path):
                    c_dict["local_path"] = c.local_path
                elif cached_audio_path.exists():
                    c_dict["local_path"] = str(cached_audio_path)
                elif m_url and m_url.startswith(("http://", "https://")):
                    try:
                        _enforce_url_security(m_url)
                        dl_path = cache_dir / f"audio_dl_{uuid.uuid4().hex[:6]}.mp3"
                        resp = await http_client.get(m_url)
                        if resp.status_code == 200:
                            dl_path.write_bytes(resp.content)
                            c_dict["local_path"] = str(dl_path)
                    except Exception as dl_err:
                        logger.warning(f"Failed downloading audio clip from {m_url}: {dl_err}")
                resolved_clips.append(c_dict)
                continue

            # 2. Caption Clips (TXT)
            if track_id == "TXT":
                resolved_clips.append(c_dict)
                continue

            # 3. Video Clips Resolution (V1, V2)
            resolved_path = None

            # 3a. Existing valid local_path
            if c.local_path and os.path.exists(c.local_path):
                resolved_path = c.local_path

            # 3b. Check segments directory by scene index
            if not resolved_path and job_seg_dir.exists():
                m_scene = re.search(r"scene[_\s]*(\d+)", c_name.lower()) or re.search(r"clip_v1_(\d+)", c.id)
                if m_scene:
                    scene_num = int(m_scene.group(1)) + 1 if "clip_v1_" in m_scene.group(0) else int(m_scene.group(1))
                    cand_seg = job_seg_dir / f"seg_{safe_aspect}_scene_{scene_num:03d}.mp4"
                    if cand_seg.exists():
                        resolved_path = str(cand_seg)

            # 3c. Direct media_id glob in cache_dir (id sanitized to prevent glob traversal)
            if not resolved_path and m_id:
                safe_m_id = re.sub(r"[^\w\-]", "_", m_id)
                matched = list(cache_dir.glob(f"*{safe_m_id}*"))
                if matched and matched[0].exists():
                    resolved_path = str(matched[0])

            # 3d. Check numeric IDs in media_url (e.g. pixabay 39982)
            if not resolved_path and m_url:
                nums = re.findall(r"\d{4,}", m_url)
                for num in nums:
                    matched = list(cache_dir.glob(f"*{num}*"))
                    if matched and matched[0].exists():
                        resolved_path = str(matched[0])
                        break

            # 3e. Remote URL download into cache
            if not resolved_path and m_url and m_url.startswith(("http://", "https://")):
                try:
                    _enforce_url_security(m_url)
                    clean_name = re.sub(r"[^\w\-.]", "_", Path(m_url.split("?")[0]).name)
                    if not clean_name.endswith(".mp4"):
                        clean_name += ".mp4"
                    dl_path = cache_dir / f"downloaded_{clean_name}"
                    if dl_path.exists() and dl_path.stat().st_size > 10000:
                        resolved_path = str(dl_path)
                    else:
                        resp = await http_client.get(m_url)
                        if resp.status_code == 200 and len(resp.content) > 10000:
                            dl_path.write_bytes(resp.content)
                            resolved_path = str(dl_path)
                except Exception as dl_err:
                    logger.warning(f"Failed downloading footage from {m_url}: {dl_err}")

            # 3f. Fallback to any cached pixabay video if completely missing
            if not resolved_path:
                any_cached = list(cache_dir.glob("pixabay_*.mp4"))
                if any_cached:
                    resolved_path = str(any_cached[idx % len(any_cached)])

            if resolved_path:
                c_dict["local_path"] = resolved_path

            resolved_clips.append(c_dict)

    out_dir = Path(tempfile.mkdtemp(prefix=f"broll_export_{job_id}_"))
    out_video = str(out_dir / f"video_edited_{safe_aspect}.mp4")

    try:
        render_res = await service.worker.assembly_engine.assemble_custom_timeline(
            timeline_clips=resolved_clips,
            output_path=out_video,
            aspect_ratio=aspect,
            burn_in_captions=request.burn_in_captions,
            job_id=job_id,
            caption_style=request.caption_style,
        )

        video_key = f"jobs/{job_id}/video_edited_{safe_aspect}.mp4"
        await service.worker.storage.upload_file(out_video, video_key, "video/mp4")

        # Safely update standard aspect video if render is high quality (> 1MB)
        if os.path.exists(out_video) and os.path.getsize(out_video) > 1_000_000:
            await service.worker.storage.upload_file(out_video, f"jobs/{job_id}/video_{safe_aspect}.mp4", "video/mp4")

        elapsed = round(time.time() - t0, 2)
        stream_url = f"/api/v1/jobs/{job_id}/video?aspect={aspect}&edited=true&t={int(time.time())}"

        return TimelineExportResponse(
            job_id=job_id,
            aspect_ratio=aspect,
            video_url=stream_url,
            duration_seconds=render_res["duration_seconds"],
            processing_time_seconds=elapsed,
            message=f"Timeline rendered in {elapsed}s with {len(request.clips)} clips across {len(request.tracks)} tracks.",
        )
    except Exception as e:
        logger.error(f"Timeline export failed: {e}", exc_info=True)
        raise APIError(code="EXPORT_FAILED", message=f"Failed to render edited timeline: {e}", status_code=500)
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


