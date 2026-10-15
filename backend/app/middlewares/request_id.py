from __future__ import annotations

import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.app.core.request_context import request_id_var
from backend.app.core.tenant_execution import reset_tenant_execution, tenant_execution_var


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Ajoute un identifiant de requête au contexte et aux en-têtes de réponse."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        tenant_token = tenant_execution_var.set(None)
        try:
            response = await call_next(request)
        finally:
            reset_tenant_execution(tenant_token)
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response
