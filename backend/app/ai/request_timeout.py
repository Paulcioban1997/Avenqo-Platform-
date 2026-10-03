"""A total AI deadline bounds classification, tools, retries and fallback."""
import asyncio
from functools import wraps
from inspect import signature
import logging

from backend.app.ai.chat.exceptions import AIServiceUnavailableError
from backend.app.config.settings import get_settings
from backend.app.core.request_context import request_id_var

logger = logging.getLogger("avenqo.ai.deadline")


def bounded_ai_request(operation):
    parameters = signature(operation)
    @wraps(operation)
    async def bounded(*args, **kwargs):
        try:
            async with asyncio.timeout(get_settings().ai_request_timeout_seconds):
                return await operation(*args, **kwargs)
        except TimeoutError as exc:
            arguments = parameters.bind(*args, **kwargs).arguments
            tenant = arguments.get("tenant", arguments.get("tenant_id"))
            logger.warning(
                "ai_request_timeout request_id=%s tenant_id=%s user_id=%s operation=%s category=request_deadline",
                request_id_var.get(), getattr(tenant, "company_id", tenant),
                arguments.get("user_id"), operation.__qualname__,
            )
            raise AIServiceUnavailableError("Avenqo AI est temporairement indisponible. Veuillez réessayer.") from exc
    return bounded
