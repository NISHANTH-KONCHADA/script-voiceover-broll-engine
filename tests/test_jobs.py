import asyncio
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_submit_job_with_script(client: AsyncClient):
    """Verifies POST /api/v1/broll/jobs returns 202 Accepted for script input."""
    payload = {
        "script": "Building an AI-driven video engine requires strong architecture and clean code.",
        "voice": "en-IN-female",
        "aspect_ratios": ["16:9", "9:16"],
        "style": "bright, modern",
        "captions": {"burn_in": True, "srt": True},
    }

    response = await client.post("/api/v1/broll/jobs", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["job_id"].startswith("broll_")
    assert data["status"] in ("queued", "running")
    assert data["progress"] >= 0
    assert "check_status_url" in data

    # Poll status until completion
    job_id = data["job_id"]
    for _ in range(30):
        status_res = await client.get(f"/api/v1/jobs/{job_id}")
        assert status_res.status_code == 200
        status_data = status_res.json()
        if status_data["status"] == "succeeded":
            break
        await asyncio.sleep(0.05)

    assert status_data["status"] == "succeeded"
    assert status_data["progress"] == 100
    assert status_data["stage"] == "COMPLETED"
    assert "outputs" in status_data
    assert "16:9" in status_data["outputs"]["videos"]
    assert "9:16" in status_data["outputs"]["videos"]
    assert status_data["outputs"]["captions"] is not None
    assert status_data["outputs"]["timeline"] is not None
    assert status_data["outputs"]["manifest"] is not None


@pytest.mark.asyncio
async def test_submit_job_with_audio_url(client: AsyncClient):
    """Verifies job submission with pre-recorded audio URL."""
    payload = {
        "audio_url": "https://storage.example.com/audio/voiceover.mp3",
        "aspect_ratios": ["16:9"],
    }
    response = await client.post("/api/v1/broll/jobs", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert data["job_id"].startswith("broll_")


@pytest.mark.asyncio
async def test_submit_job_with_scenes_hint_list(client: AsyncClient):
    """Verifies job submission with IncuBrix pre-segmented scenes list."""
    payload = {
        "scenes": [
            {"text": "First scene about innovation.", "visual_hint": "team brainstorming in glass office"},
            {"text": "Second scene about delivery.", "visual_hint": "rocket launch or speed train"},
        ],
        "aspect_ratios": ["1:1"],
    }
    response = await client.post("/api/v1/broll/jobs", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert data["job_id"].startswith("broll_")


@pytest.mark.asyncio
async def test_get_nonexistent_job_returns_404(client: AsyncClient):
    """Verifies GET /api/v1/jobs/unknown returns 404 with structured error."""
    response = await client.get("/api/v1/jobs/broll_nonexistent_99999")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "JOB_NOT_FOUND"
    assert "retryable" in data["error"]
    assert data["error"]["retryable"] is False


@pytest.mark.asyncio
async def test_list_recent_jobs(client: AsyncClient):
    """Verifies GET /api/v1/jobs returns paginated job list."""
    # Create two jobs
    await client.post("/api/v1/broll/jobs", json={"script": "Job one."})
    await client.post("/api/v1/broll/jobs", json={"script": "Job two."})

    response = await client.get("/api/v1/jobs?limit=10")
    assert response.status_code == 200
    jobs = response.json()
    assert isinstance(jobs, list)
    assert len(jobs) >= 2
    assert "job_id" in jobs[0]
    assert "status" in jobs[0]
