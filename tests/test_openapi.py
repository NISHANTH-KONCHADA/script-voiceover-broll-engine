from pathlib import Path
import yaml
import pytest


def test_openapi_yaml_exists_and_valid():
    """Verifies openapi.yaml is valid YAML and declares OpenAPI 3.1."""
    root_dir = Path(__file__).parent.parent
    openapi_file = root_dir / "openapi.yaml"
    assert openapi_file.exists(), "openapi.yaml must exist in repository root"

    with open(openapi_file, "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    assert spec.get("openapi") == "3.1.0", "OpenAPI version must be 3.1.0"
    assert "info" in spec
    assert spec["info"]["title"] == "IncuBrix B-roll Video Engine API"

    paths = spec.get("paths", {})
    assert "/health" in paths
    assert "/ready" in paths
    assert "/api/v1/broll/jobs" in paths
    assert "/api/v1/jobs/{job_id}" in paths
    assert "/api/v1/jobs" in paths

    # Verify POST /api/v1/broll/jobs has Idempotency-Key header documented
    post_op = paths["/api/v1/broll/jobs"]["post"]
    params = post_op.get("parameters", [])
    has_idempotency_header = any(
        p.get("name") == "Idempotency-Key" and p.get("in") == "header" for p in params
    )
    assert has_idempotency_header, "Idempotency-Key header must be documented in OpenAPI"
