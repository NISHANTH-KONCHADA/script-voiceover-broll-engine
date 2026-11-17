import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_empty_request_body_returns_validation_error(client: AsyncClient):
    """Verifies empty request payload returns 422 with structured VALIDATION_ERROR."""
    response = await client.post("/api/v1/broll/jobs", json={})
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    err = data["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert "message" in err
    assert err["retryable"] is False
    assert err["details"] is not None


@pytest.mark.asyncio
async def test_invalid_aspect_ratio_returns_validation_error(client: AsyncClient):
    """Verifies unsupported aspect ratio returns 422 with structured error."""
    payload = {
        "script": "Test script.",
        "aspect_ratios": ["4:3", "21:9"],
    }
    response = await client.post("/api/v1/broll/jobs", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert data["error"]["retryable"] is False


@pytest.mark.asyncio
async def test_not_found_returns_structured_error(client: AsyncClient):
    """Verifies 404 returns structured error with UPPER_SNAKE_CASE code."""
    response = await client.get("/api/v1/jobs/unknown-id")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "JOB_NOT_FOUND"
    assert isinstance(data["error"]["message"], str)
    assert data["error"]["retryable"] is False
