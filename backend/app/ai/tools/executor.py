"""`ToolExecutor` — validation, autorisation, timeout, observabilité (Phase 30).

Tous les arguments fournis par le LLM sont NON FIABLES : ils sont toujours
validés avec Pydantic (`extra="forbid"`) avant tout appel métier. Le nom de
l'outil ne suffit jamais à l'exécuter sans vérification des permissions.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from pydantic import ValidationError

from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.ai.tools.exceptions import (
    ToolAuthorizationError,
    ToolError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolTimeoutError,
    ToolUnavailableError,
    ToolValidationError,
)
from backend.app.ai.tools.registry import ToolRegistry

logger = logging.getLogger("avenqo.tool_calling")

# Aucun résultat d'outil n'est envoyé tel quel au LLM au-delà de cette taille
# (sérialisé en JSON) : au-delà, il est tronqué pour éviter d'exploser les
# coûts et le contexte du provider (section 21/38).
MAX_TOOL_RESULT_CHARS = 8000


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def execute(
        self,
        name: str,
        context: ToolExecutionContext,
        raw_arguments: dict[str, Any],
    ) -> ToolResult:
        started = time.monotonic()
        success = False
        try:
            tool = self._registry.get(name)
            if tool is None:
                raise ToolNotFoundError(f"Unknown tool: '{name}'.")

            if not set(tool.required_permissions).issubset(context.permissions):
                raise ToolAuthorizationError(f"Missing permissions to run '{name}'.")

            try:
                arguments = tool.input_schema.model_validate(raw_arguments)
            except ValidationError as exc:
                raise ToolValidationError(f"Invalid arguments for '{name}'.") from exc

            try:
                result = await asyncio.wait_for(
                    tool.run(context, arguments), timeout=tool.timeout_seconds
                )
            except TimeoutError as exc:
                raise ToolTimeoutError(f"Tool '{name}' timed out.") from exc
            except ToolUnavailableError:
                raise
            except ToolError:
                raise
            except Exception as exc:  # noqa: BLE001 - converti en erreur métier sûre
                raise ToolExecutionError(f"Tool '{name}' failed to execute.") from exc

            success = result.success
            return _truncate_result(result)
        finally:
            logger.info(
                "tool_call",
                extra={
                    "tool_name": name,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    "success": success,
                    "tenant_id": str(context.tenant_id),
                    "request_id": context.request_id,
                },
            )


def _truncate_result(result: ToolResult) -> ToolResult:
    """Limite la taille des données envoyées au LLM (jamais 50 000 lignes)."""

    import json

    serialized = json.dumps(result.data, default=str)
    if len(serialized) <= MAX_TOOL_RESULT_CHARS:
        return result
    return ToolResult(
        success=result.success,
        data={"truncated": True, "preview": serialized[:MAX_TOOL_RESULT_CHARS]},
        source_refs=result.source_refs,
        metadata={**result.metadata, "truncated": True},
        error=result.error,
    )
