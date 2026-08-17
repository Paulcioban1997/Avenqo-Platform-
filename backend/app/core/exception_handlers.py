from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.core.logging import configure_logging


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Renvoie une réponse JSON uniforme pour les erreurs HTTP."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": "HTTP_ERROR",
                "message": str(exc.detail),
                "details": None,
            },
            "request_id": getattr(request.state, "request_id", None),
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Renvoie une réponse JSON uniforme pour les erreurs de validation."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": exc.errors(),
            },
            "request_id": getattr(request.state, "request_id", None),
        },
    )


async def internal_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Renvoie une réponse JSON uniforme pour les erreurs inattendues."""
    configure_logging()
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected internal error occurred",
                "details": None,
            },
            "request_id": getattr(request.state, "request_id", None),
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, internal_exception_handler)
