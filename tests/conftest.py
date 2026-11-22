import os
from typing import AsyncGenerator
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set test environment before imports
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
# Pin offline providers so tests never hit external APIs or download models
# even when a developer's local .env configures live providers.
os.environ["ASR_PROVIDER"] = "mock"
os.environ["TTS_PROVIDER"] = "mock"
os.environ["VAD_PROVIDER"] = "energy"
os.environ["RETRIEVAL_PROVIDER_MODE"] = "mock"
os.environ["API_RATE_LIMIT_PER_MINUTE"] = "0"

from broll_engine.api.app import app, state
from broll_engine.api.routes.health import get_repository, get_storage
from broll_engine.api.routes.jobs import get_job_service
from broll_engine.repositories.sql import SQLJobRepository
from broll_engine.services.job_service import JobService
from broll_engine.storage.memory import InMemoryStorageAdapter
from broll_engine.worker.execution import JobExecutionWorker


@pytest_asyncio.fixture(scope="function")
async def test_repo() -> AsyncGenerator[SQLJobRepository, None]:
    """Provides a fresh, isolated in-memory SQLite repository per test."""
    repo = SQLJobRepository("sqlite+aiosqlite:///:memory:")
    await repo.initialize()
    yield repo
    await repo.engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_storage() -> InMemoryStorageAdapter:
    """Provides an isolated in-memory storage adapter per test."""
    return InMemoryStorageAdapter(base_url="http://mock-storage.test/bucket")


@pytest_asyncio.fixture(scope="function")
async def test_worker(test_repo: SQLJobRepository, test_storage: InMemoryStorageAdapter) -> JobExecutionWorker:
    """Provides a fast worker with 0 delay for instant unit test execution."""
    return JobExecutionWorker(repository=test_repo, storage=test_storage, step_delay_seconds=0.01)


@pytest_asyncio.fixture(scope="function")
async def test_service(test_repo: SQLJobRepository, test_worker: JobExecutionWorker) -> JobService:
    return JobService(repository=test_repo, worker=test_worker)


@pytest_asyncio.fixture(scope="function")
async def client(
    test_repo: SQLJobRepository,
    test_storage: InMemoryStorageAdapter,
    test_service: JobService,
) -> AsyncGenerator[AsyncClient, None]:
    """Provides an asynchronous HTTP test client with injected test fixtures."""
    # Override FastAPI app dependencies with test fixtures
    app.dependency_overrides[get_repository] = lambda: test_repo
    app.dependency_overrides[get_storage] = lambda: test_storage
    app.dependency_overrides[get_job_service] = lambda: test_service

    # Update global state as well
    state.repository = test_repo
    state.storage = test_storage
    state.job_service = test_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
