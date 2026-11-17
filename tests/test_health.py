import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_liveness(client: AsyncClient):
    """Verifies GET /health returns 200 with status ok."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data
    assert data["version"] == "0.1.0"
    assert "X-Correlation-Id" in response.headers


@pytest.mark.asyncio
async def test_ready_readiness(client: AsyncClient):
    """Verifies GET /ready returns 200 with healthy dependencies."""
    response = await client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["dependencies"]["database"] is True
    assert data["dependencies"]["storage"] is True


@pytest.mark.asyncio
async def test_correlation_id_propagation(client: AsyncClient):
    """Verifies custom X-Correlation-Id is preserved in response header."""
    custom_id = "req_custom_trace_98765"
    response = await client.get("/health", headers={"X-Correlation-Id": custom_id})
    assert response.status_code == 200
    assert response.headers.get("X-Correlation-Id") == custom_id
    assert "X-Response-Time-Ms" in response.headers
