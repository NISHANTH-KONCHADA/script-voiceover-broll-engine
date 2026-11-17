import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Context variables for request tracking
correlation_id_ctx: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)
job_id_ctx: ContextVar[Optional[str]] = ContextVar("job_id", default=None)


class JSONFormatter(logging.Formatter):
    """Custom logging formatter outputting single-line JSON with context fields."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Inject context variables
        corr_id = correlation_id_ctx.get()
        if corr_id:
            log_entry["correlation_id"] = corr_id

        j_id = job_id_ctx.get()
        if j_id:
            log_entry["job_id"] = j_id
        elif hasattr(record, "job_id") and record.job_id:
            log_entry["job_id"] = record.job_id

        # Include exception trace if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include custom extra kwargs if provided
        for key in ("stage", "details", "duration_ms", "status_code"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        return json.dumps(log_entry, default=str)


def setup_logging(level: str = "INFO") -> None:
    """Configures root logger with JSONFormatter."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Returns a named logger configured for structured output."""
    return logging.getLogger(name)
