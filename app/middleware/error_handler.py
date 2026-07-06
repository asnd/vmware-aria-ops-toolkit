"""Global error handling middleware."""

import logging
from datetime import datetime

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.models.errors import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with standard error format."""
    request_id = getattr(request.state, "request_id", None)

    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.__class__.__name__,
            detail=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            request_id=request_id,
            timestamp=datetime.utcnow(),
        ).model_dump(mode="json"),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with detailed field information."""
    request_id = getattr(request.state, "request_id", None)

    # Convert Pydantic validation errors to our format
    error_details = [
        ErrorDetail(
            loc=err["loc"],
            msg=err["msg"],
            type=err["type"],
        )
        for err in exc.errors()
    ]

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            error="ValidationError",
            detail=[detail.model_dump(mode="json") for detail in error_details],
            request_id=request_id,
            timestamp=datetime.utcnow(),
        ).model_dump(mode="json"),
    )


async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    request_id = getattr(request.state, "request_id", None)

    # Log the exception
    logger.exception(f"Unhandled exception (request_id: {request_id})")

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="InternalServerError",
            detail="An unexpected error occurred. Please contact support.",
            request_id=request_id,
            timestamp=datetime.utcnow(),
        ).model_dump(mode="json"),
    )
