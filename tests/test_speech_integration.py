import asyncio
import os
import tempfile
import numpy as np
import pytest
import scipy.io.wavfile as wavfile
from httpx import AsyncClient


def create_audio_fixture(duration_sec: float, silent: bool = False, sample_rate: int = 16000) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    path = tmp.name
    tmp.close()

    total_samples = int(duration_sec * sample_rate)
    if silent:
        data = np.zeros(total_samples, dtype=np.int16)
    else:
        t = np.linspace(0, duration_sec, total_samples, endpoint=False)
        signal = 0.5 * np.sin(2 * np.pi * 320 * t)
        data = (signal * 32767).astype(np.int16)

    wavfile.write(path, sample_rate, data)
    return path


@pytest.mark.asyncio
async def test_job_execution_with_script_en(client: AsyncClient):
    """Verifies end-to-end speech synthesis, alignment, and manifest for English script."""
    payload = {
        "script": "Building automated B-roll videos with frame-accurate speech alignment.",
        "voice": "en-IN-female",
        "aspect_ratios": ["16:9"],
    }

    res = await client.post("/api/v1/broll/jobs", json=payload)
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    # Poll status
    for _ in range(30):
        detail_res = await client.get(f"/api/v1/jobs/{job_id}")
        assert detail_res.status_code == 200
        detail = detail_res.json()
        if detail["status"] in ("succeeded", "failed"):
            break
        await asyncio.sleep(0.05)

    assert detail["status"] == "succeeded"
    assert detail["progress"] == 100
    assert detail["stage"] == "COMPLETED"
    outputs = detail["outputs"]
    assert outputs["audio"] is not None
    assert outputs["transcript"] is not None
    assert outputs["manifest"] is not None


@pytest.mark.asyncio
async def test_job_execution_with_script_hindi(client: AsyncClient):
    """Verifies end-to-end Hindi speech synthesis and alignment (Outstanding level)."""
    payload = {
        "script": "तकनीक और नवाचार हमारे भविष्य को बदल रहे हैं।",
        "voice": "hi-IN-female",
        "aspect_ratios": ["9:16"],
    }

    res = await client.post("/api/v1/broll/jobs", json=payload)
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    for _ in range(30):
        detail = (await client.get(f"/api/v1/jobs/{job_id}")).json()
        if detail["status"] in ("succeeded", "failed"):
            break
        await asyncio.sleep(0.05)

    assert detail["status"] == "succeeded"
    assert detail["progress"] == 100


@pytest.mark.asyncio
async def test_job_execution_with_script_tamil(client: AsyncClient):
    """Verifies end-to-end Tamil speech synthesis and alignment (Outstanding level)."""
    payload = {
        "script": "செயற்கை நுண்ணறிவு புதிய வாய்ப்புகளை உருவாக்குகிறது.",
        "voice": "ta-IN-female",
        "aspect_ratios": ["1:1"],
    }

    res = await client.post("/api/v1/broll/jobs", json=payload)
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    for _ in range(30):
        detail = (await client.get(f"/api/v1/jobs/{job_id}")).json()
        if detail["status"] in ("succeeded", "failed"):
            break
        await asyncio.sleep(0.05)

    assert detail["status"] == "succeeded"
    assert detail["progress"] == 100


@pytest.mark.asyncio
async def test_job_execution_with_valid_audio_input(client: AsyncClient):
    """Verifies end-to-end processing of pre-recorded audio input."""
    audio_path = create_audio_fixture(duration_sec=3.5, silent=False)

    try:
        payload = {
            "audio_url": audio_path,
            "aspect_ratios": ["16:9"],
        }
        res = await client.post("/api/v1/broll/jobs", json=payload)
        assert res.status_code == 202
        job_id = res.json()["job_id"]

        for _ in range(30):
            detail = (await client.get(f"/api/v1/jobs/{job_id}")).json()
            if detail["status"] in ("succeeded", "failed"):
                break
            await asyncio.sleep(0.05)

        assert detail["status"] == "succeeded"
        assert detail["progress"] == 100
        assert detail["outputs"]["transcript"] is not None
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)


@pytest.mark.asyncio
async def test_job_fails_gracefully_on_silent_audio(client: AsyncClient):
    """Verifies silent audio causes the job to fail with NO_SPEECH_DETECTED."""
    silent_path = create_audio_fixture(duration_sec=3.0, silent=True)

    try:
        payload = {
            "audio_url": silent_path,
            "aspect_ratios": ["16:9"],
        }
        res = await client.post("/api/v1/broll/jobs", json=payload)
        assert res.status_code == 202
        job_id = res.json()["job_id"]

        for _ in range(30):
            detail = (await client.get(f"/api/v1/jobs/{job_id}")).json()
            if detail["status"] in ("succeeded", "failed"):
                break
            await asyncio.sleep(0.05)

        assert detail["status"] == "failed"
        assert detail["progress"] == 100
        assert detail["stage"] == "FAILED"
        assert detail["error"] is not None
        assert detail["error"]["code"] == "NO_SPEECH_DETECTED"
        assert detail["error"]["retryable"] is False
    finally:
        if os.path.exists(silent_path):
            os.remove(silent_path)


@pytest.mark.asyncio
async def test_job_fails_gracefully_on_corrupted_audio(client: AsyncClient):
    """Verifies unreadable audio causes job failure with CORRUPTED_AUDIO_FILE."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    corrupted_path = tmp.name
    tmp.write(b"NOT_A_VALID_WAV_HEADER_CORRUPTED_BYTES")
    tmp.close()

    try:
        payload = {
            "audio_url": corrupted_path,
            "aspect_ratios": ["16:9"],
        }
        res = await client.post("/api/v1/broll/jobs", json=payload)
        assert res.status_code == 202
        job_id = res.json()["job_id"]

        for _ in range(30):
            detail = (await client.get(f"/api/v1/jobs/{job_id}")).json()
            if detail["status"] in ("succeeded", "failed"):
                break
            await asyncio.sleep(0.05)

        assert detail["status"] == "failed"
        assert detail["stage"] == "FAILED"
        assert detail["error"]["code"] == "CORRUPTED_AUDIO_FILE"
    finally:
        if os.path.exists(corrupted_path):
            os.remove(corrupted_path)
