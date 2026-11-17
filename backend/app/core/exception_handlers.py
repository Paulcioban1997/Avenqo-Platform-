from __future__ import annotations

import logging

from typing import Any, cast

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.core.error_localization import (
    ERROR_MESSAGES,
    http_error_message,
    resolve_api_locale,
    validation_error_message,
    validation_summary,
)

logger = logging.getLogger("avenqo.errors")


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Renvoie une réponse JSON uniforme pour les erreurs HTTP."""
    accept_language = request.headers.get("accept-language")
    code = "HTTP_ERROR"
    details = None
    detail_data = exc.detail
    if isinstance(detail_data, dict):
        code_val = detail_data.get("code")
        if isinstance(code_val, str):
            code = code_val
        details = {k: v for k, v in detail_data.items() if k not in {"code", "message"}}

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": code,
                "message": http_error_message(exc.status_code, accept_language, exc.detail),
                "details": details,
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
    details = []
    first_custom_message = None
    for error in exc.errors():
        err_type = str(error.get("type", "validation_error"))
        cleaned_msg = _clean_error_message(str(error.get("msg", "")))
        is_custom_error = err_type == "value_error" and cleaned_msg and not cleaned_msg.startswith("Value error")
        if is_custom_error:
            localized_msg = http_error_message(status.HTTP_422_UNPROCESSABLE_ENTITY, accept_language, cleaned_msg)
            if localized_msg == ERROR_MESSAGES.get(resolve_api_locale(accept_language), {}).get("validation_failed"):
                localized_msg = cleaned_msg
            if not first_custom_message:
                first_custom_message = localized_msg
            msg_to_use = localized_msg
        else:
            msg_to_use = validation_error_message(err_type, accept_language)
        details.append({
            "type": err_type,
            "loc": list(error.get("loc", ())),
            "msg": msg_to_use,
        })
    summary_message = first_custom_message or validation_summary(accept_language)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        headers={"Content-Type": "application/json; charset=utf-8"},
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": summary_message,
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
    app.add_exception_handler(StarletteHTTPException, cast(Any, http_exception_handler))
    app.add_exception_handler(RequestValidationError, cast(Any, validation_exception_handler))
    app.add_exception_handler(Exception, cast(Any, internal_exception_handler))
