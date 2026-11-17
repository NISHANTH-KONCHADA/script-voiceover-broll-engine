import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_idempotent_job_submission(client: AsyncClient):
    """
    Verifies that sending two requests with the same Idempotency-Key
    returns the exact same job and does not duplicate records.
    """
    idempotency_key = "test-key-uuid-8899aabbcc"
    payload = {
        "script": "Idempotent job payload for testing safe retries.",
        "aspect_ratios": ["16:9"],
    }

    # First request
    res1 = await client.post(
        "/api/v1/broll/jobs",
        json=payload,
        headers={"Idempotency-Key": idempotency_key},
    )
    assert res1.status_code == 202
    data1 = res1.json()
    job_id1 = data1["job_id"]
    assert "X-Idempotent-Replay" not in res1.headers

    # Second request with identical key
    res2 = await client.post(
        "/api/v1/broll/jobs",
        json=payload,
        headers={"Idempotency-Key": idempotency_key},
    )
    assert res2.status_code == 202
    data2 = res2.json()
    job_id2 = data2["job_id"]

    # Must match original job ID exactly
    assert job_id1 == job_id2
    assert res2.headers.get("X-Idempotent-Replay") == "true"

    # Verify only ONE job exists in the repository
    list_res = await client.get("/api/v1/jobs")
    assert list_res.status_code == 200
    matching_jobs = [j for j in list_res.json() if j["job_id"] == job_id1]
    assert len(matching_jobs) == 1
