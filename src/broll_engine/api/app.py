from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from broll_engine.api.middleware import CorrelationIdMiddleware, RateLimitMiddleware
from broll_engine.api.routes.errors import register_error_handlers
from broll_engine.api.routes.health import get_repository, get_storage, router as health_router
from broll_engine.api.routes.jobs import get_job_service, router as jobs_router
from broll_engine.config import settings
from broll_engine.logging import get_logger, setup_logging
from broll_engine.repositories.base import JobRepository
from broll_engine.repositories.sql import SQLJobRepository
from broll_engine.services.job_service import JobService
from broll_engine.storage.base import StorageAdapter
from broll_engine.storage.memory import InMemoryStorageAdapter
from broll_engine.storage.s3 import S3StorageAdapter
from broll_engine.worker.execution import JobExecutionWorker

logger = get_logger(__name__)


class ApplicationState:
    """Container for stateful application dependencies."""
    repository: Optional[JobRepository] = None
    storage: Optional[StorageAdapter] = None
    worker: Optional[JobExecutionWorker] = None
    job_service: Optional[JobService] = None


state = ApplicationState()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manages application startup and graceful shutdown."""
    setup_logging(settings.log_level)
    logger.info("Initializing IncuBrix B-roll Video Engine...")

    # Initialize SQL Job Repository
    state.repository = SQLJobRepository(settings.database_url)
    await state.repository.initialize()

    # Initialize Object Storage Adapter
    if settings.app_env == "test":
        state.storage = InMemoryStorageAdapter()
    else:
        state.storage = S3StorageAdapter()
        # Fire-and-forget bucket initialization
        try:
            await state.storage.ensure_bucket()
        except Exception as e:
            logger.warning(f"Storage bucket init warning: {e}")

    # Initialize Worker & Job Service
    state.worker = JobExecutionWorker(repository=state.repository, storage=state.storage)
    state.job_service = JobService(repository=state.repository, worker=state.worker)

    # Wire Dependency Overrides
    app.dependency_overrides[get_repository] = lambda: state.repository
    app.dependency_overrides[get_storage] = lambda: state.storage
    app.dependency_overrides[get_job_service] = lambda: state.job_service

    logger.info("IncuBrix B-roll Video Engine startup complete. Ready for jobs.")
    yield

    logger.info("Shutting down IncuBrix B-roll Video Engine...")


def create_app() -> FastAPI:
    """FastAPI application factory configuring OpenAPI 3.1, middleware, and routers."""
    app = FastAPI(
        title="IncuBrix B-roll Video Engine API",
        version="0.1.0",
        description="Automated Script and Voiceover to B-roll Video Engine (IncuBrix Assessment 3 / PS3)",
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Cross-Origin Resource Sharing (wildcard origins cannot carry credentials)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiting for expensive job submissions (disabled when limit <= 0)
    app.add_middleware(
        RateLimitMiddleware,
        max_per_minute=settings.api_rate_limit_per_minute,
    )

    # Correlation ID & structured logging middleware
    app.add_middleware(CorrelationIdMiddleware)

    # Structured error handlers
    register_error_handlers(app)

    # Root path redirects to the Swagger UI (the API has no homepage)
    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    # Include routers
    app.include_router(health_router)
    app.include_router(jobs_router)

    return app


# Root application instance
app = create_app()
