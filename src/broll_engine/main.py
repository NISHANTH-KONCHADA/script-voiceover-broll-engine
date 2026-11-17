import uvicorn
from broll_engine.config import settings


def main() -> None:
    """CLI entry point to run the API server."""
    uvicorn.run(
        "broll_engine.api.app:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
        log_config=None,  # Handled by our JSON logging formatter
    )


if __name__ == "__main__":
    main()
