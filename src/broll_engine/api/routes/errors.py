from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from broll_engine.api.schemas.error import ErrorDetail, ErrorResponse
from broll_engine.logging import get_logger

logger = get_logger(__name__)


class APIError(Exception):
    """Base API exception that renders into standard structured JSON."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        retryable: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.details = details or {}
        super().__init__(message)


def sanitize_validation_errors(raw_errors: list) -> list:
    """Sanitizes Pydantic error details, converting any exceptions in 'ctx' to strings."""
    clean_errors = []
    for err in raw_errors:
        clean_err = dict(err)
        if "ctx" in clean_err and isinstance(clean_err["ctx"], dict):
            clean_err["ctx"] = {k: str(v) for k, v in clean_err["ctx"].items()}
        clean_errors.append(clean_err)
    return clean_errors


def register_error_handlers(app: FastAPI) -> None:
    """Registers standard structured JSON exception handlers."""

    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
        logger.warning(f"APIError: {exc.code} - {exc.message} on {request.url.path}")
        payload = ErrorResponse(
            error=ErrorDetail(
                code=exc.code,
                message=exc.message,
                retryable=exc.retryable,
                details=exc.details,
            )
        )
        return JSONResponse(status_code=exc.status_code, content=jsonable_encoder(payload.model_dump()))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        sanitized_errors = sanitize_validation_errors(exc.errors())
        logger.warning(f"Validation error on {request.url.path}: {sanitized_errors}")
        payload = ErrorResponse(
            error=ErrorDetail(
                code="VALIDATION_ERROR",
                message="Request failed input validation checks.",
                retryable=False,
                details={"errors": sanitized_errors},
            )
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=jsonable_encoder(payload.model_dump()),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        logger.warning(f"HTTPException {exc.status_code}: {exc.detail} on {request.url.path}")
        code_map = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            409: "CONFLICT",
            422: "UNPROCESSABLE_ENTITY",
            429: "RATE_LIMITED",
            500: "INTERNAL_SERVER_ERROR",
            502: "BAD_GATEWAY",
            503: "SERVICE_UNAVAILABLE",
            504: "GATEWAY_TIMEOUT",
        }
        code = code_map.get(exc.status_code, "HTTP_ERROR")
        payload = ErrorResponse(
            error=ErrorDetail(
                code=code,
                message=str(exc.detail),
                retryable=exc.status_code in (429, 502, 503, 504),
                details=None,
            )
        )
        return JSONResponse(status_code=exc.status_code, content=jsonable_encoder(payload.model_dump()))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(f"Unhandled server error on {request.url.path}: {exc}")
        payload = ErrorResponse(
            error=ErrorDetail(
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected internal server error occurred.",
                retryable=True,
                details={"exception_type": type(exc).__name__},
            )
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=jsonable_encoder(payload.model_dump()),
        )
