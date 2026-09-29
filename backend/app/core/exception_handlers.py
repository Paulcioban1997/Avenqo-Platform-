from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.core.error_localization import (
    http_error_message,
    validation_error_message,
    validation_summary,
)

logger = logging.getLogger("avenqo.errors")


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Renvoie une réponse JSON uniforme pour les erreurs HTTP."""
    accept_language = request.headers.get("accept-language")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": "HTTP_ERROR",
                "message": http_error_message(exc.status_code, accept_language, exc.detail),
                "details": None,
            },
            "request_id": getattr(request.state, "request_id", None),
        },
    )


def _clean_error_message(msg: str) -> str:
    if not isinstance(msg, str):
        return str(msg)
    cleaned = msg
    for prefix in ("Value error, ", "Assertion failed, ", "Value error,"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    return cleaned


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Renvoie une réponse JSON uniforme pour les erreurs de validation."""
    accept_language = request.headers.get("accept-language")
    details = [
        {
            "type": error.get("type", "validation_error"),
            "loc": list(error.get("loc", ())),
            "msg": validation_error_message(
                str(error.get("type", "validation_error")), accept_language
            ),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        headers={"Content-Type": "application/json; charset=utf-8"},
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": validation_summary(accept_language),
                "details": details,
            },
            "request_id": getattr(request.state, "request_id", None),
        },
    )


async def internal_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Renvoie une réponse JSON uniforme pour les erreurs inattendues.

    La trace complète est journalisée côté serveur uniquement (jamais dans la
    réponse client) — voir docs/production-deployment.md § Observabilité.
    """
    request_id = getattr(request.state, "request_id", None)
    accept_language = request.headers.get("accept-language")
    logger.exception("Unhandled exception (request_id=%s)", request_id)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": http_error_message(status.HTTP_500_INTERNAL_SERVER_ERROR, accept_language),
                "details": None,
            },
            "request_id": request_id,
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, internal_exception_handler)
