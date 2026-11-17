import os
import tempfile
import pytest
from broll_engine.api.schemas.job import JobStatus
from broll_engine.repositories.sql import SQLJobRepository


@pytest.mark.asyncio
async def test_job_persistence_survives_restart():
    """
    Verifies that jobs written to SQLite persist across database
    connections and process restarts.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
        db_path = tmp_db.name

    db_url = f"sqlite+aiosqlite:///{db_path}"

    try:
        # Step 1: First application session creates a job
        repo1 = SQLJobRepository(database_url=db_url)
        await repo1.initialize()

        job_id = "broll_recoverable_12345"
        payload = {"script": "Persistent narration script across restarts."}
        record1 = await repo1.create_job(
            job_id=job_id,
            idempotency_key="restart-test-key-1",
            request_payload=payload,
        )
        assert record1.job_id == job_id
        assert record1.status == JobStatus.QUEUED

        # Update progress and stage
        await repo1.update_job_status(
            job_id=job_id,
            status=JobStatus.RUNNING,
            progress=45,
            stage="TRANSCRIPTION",
        )

        # Simulate shutdown
        await repo1.engine.dispose()

        # Step 2: Second application session restarts against same SQLite file
        repo2 = SQLJobRepository(database_url=db_url)
        await repo2.initialize()

        recovered_record = await repo2.get_job(job_id)
        assert recovered_record is not None
        assert recovered_record.job_id == job_id
        assert recovered_record.status == JobStatus.RUNNING
        assert recovered_record.progress == 45
        assert recovered_record.stage == "TRANSCRIPTION"
        assert recovered_record.request_payload == payload
        assert recovered_record.idempotency_key == "restart-test-key-1"

        # Verify idempotency query works on recovered DB
        idempotent_match = await repo2.get_job_by_idempotency_key("restart-test-key-1")
        assert idempotent_match is not None
        assert idempotent_match.job_id == job_id

        await repo2.engine.dispose()

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
