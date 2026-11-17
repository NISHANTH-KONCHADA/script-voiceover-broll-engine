import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    event,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from broll_engine.api.schemas.job import JobStatus
from broll_engine.config import settings
from broll_engine.logging import get_logger
from broll_engine.repositories.base import JobRecord, JobRepository

logger = get_logger(__name__)

metadata = MetaData()

jobs_table = Table(
    "jobs",
    metadata,
    Column("job_id", String(64), primary_key=True),
    Column("idempotency_key", String(128), unique=True, index=True, nullable=True),
    Column("status", String(32), nullable=False, default=JobStatus.QUEUED.value),
    Column("progress", Integer, nullable=False, default=0),
    Column("stage", String(64), nullable=False, default="QUEUED"),
    Column("request_payload", Text, nullable=False),
    Column("outputs", Text, nullable=True),
    Column("error", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True), nullable=True),
)


class SQLJobRepository(JobRepository):
    """Production SQL job repository backed by SQLite (aiosqlite) or PostgreSQL."""

    def __init__(self, database_url: Optional[str] = None) -> None:
        self.database_url = database_url or settings.database_url

        # Ensure directory exists if using local SQLite file
        if "sqlite" in self.database_url:
            path_part = self.database_url.split("sqlite+aiosqlite:///")[-1]
            if path_part and not path_part.startswith(":memory:"):
                os.makedirs(os.path.dirname(os.path.abspath(path_part)), exist_ok=True)

        self.engine: AsyncEngine = create_async_engine(
            self.database_url,
            echo=False,
            future=True,
        )

        # Enable SQLite WAL mode for concurrency and crash-resilience
        if "sqlite" in self.database_url:
            @event.listens_for(self.engine.sync_engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.close()

    async def initialize(self) -> None:
        """Creates tables if they do not exist."""
        async with self.engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
        logger.info(f"Initialized job database schema at {self.database_url}")

    def _row_to_record(self, row: Any) -> JobRecord:
        request_dict = json.loads(row.request_payload) if row.request_payload else {}
        outputs_dict = json.loads(row.outputs) if row.outputs else None
        error_dict = json.loads(row.error) if row.error else None

        return JobRecord(
            job_id=row.job_id,
            idempotency_key=row.idempotency_key,
            status=JobStatus(row.status),
            progress=row.progress,
            stage=row.stage,
            request_payload=request_dict,
            outputs=outputs_dict,
            error=error_dict,
            created_at=row.created_at,
            updated_at=row.updated_at,
            completed_at=row.completed_at,
        )

    async def create_job(
        self,
        job_id: str,
        idempotency_key: Optional[str],
        request_payload: Dict[str, Any],
    ) -> JobRecord:
        now = datetime.now(timezone.utc)
        payload_json = json.dumps(request_payload, default=str)

        async with self.engine.begin() as conn:
            await conn.execute(
                jobs_table.insert().values(
                    job_id=job_id,
                    idempotency_key=idempotency_key,
                    status=JobStatus.QUEUED.value,
                    progress=0,
                    stage="QUEUED",
                    request_payload=payload_json,
                    outputs=None,
                    error=None,
                    created_at=now,
                    updated_at=now,
                    completed_at=None,
                )
            )

        return JobRecord(
            job_id=job_id,
            idempotency_key=idempotency_key,
            status=JobStatus.QUEUED,
            progress=0,
            stage="QUEUED",
            request_payload=request_payload,
            outputs=None,
            error=None,
            created_at=now,
            updated_at=now,
            completed_at=None,
        )

    async def get_job(self, job_id: str) -> Optional[JobRecord]:
        async with self.engine.connect() as conn:
            result = await conn.execute(
                select(jobs_table).where(jobs_table.c.job_id == job_id)
            )
            row = result.first()
            if not row:
                return None
            return self._row_to_record(row)

    async def get_job_by_idempotency_key(self, key: str) -> Optional[JobRecord]:
        if not key:
            return None
        async with self.engine.connect() as conn:
            result = await conn.execute(
                select(jobs_table).where(jobs_table.c.idempotency_key == key)
            )
            row = result.first()
            if not row:
                return None
            return self._row_to_record(row)

    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        progress: int,
        stage: str,
        outputs: Optional[Dict[str, Any]] = None,
        error: Optional[Dict[str, Any]] = None,
    ) -> Optional[JobRecord]:
        now = datetime.now(timezone.utc)
        values: Dict[str, Any] = {
            "status": status.value,
            "progress": progress,
            "stage": stage,
            "updated_at": now,
        }
        if outputs is not None:
            values["outputs"] = json.dumps(outputs, default=str)
        if error is not None:
            values["error"] = json.dumps(error, default=str)
        if status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
            values["completed_at"] = now

        async with self.engine.begin() as conn:
            result = await conn.execute(
                update(jobs_table)
                .where(jobs_table.c.job_id == job_id)
                .values(**values)
            )
            if result.rowcount == 0:
                return None

        return await self.get_job(job_id)

    async def list_jobs(self, limit: int = 50, offset: int = 0) -> List[JobRecord]:
        async with self.engine.connect() as conn:
            result = await conn.execute(
                select(jobs_table)
                .order_by(jobs_table.c.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = result.fetchall()
            return [self._row_to_record(r) for r in rows]

    async def health_check(self) -> bool:
        try:
            async with self.engine.connect() as conn:
                await conn.execute(select(1))
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
