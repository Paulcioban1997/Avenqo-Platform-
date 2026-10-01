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
from backend.app.ai.tools.authorization import ToolAuthorizationPolicy
from backend.app.ai.tools.idempotency import AIToolExecutionIdempotencyStore
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
from backend.app.ai.tools.natural_confirmation import (
    confirmation_required_message,
    is_natural_confirmation,
)

logger = logging.getLogger("avenqo.tool_calling")

# Aucun résultat d'outil n'est envoyé tel quel au LLM au-delà de cette taille
# (sérialisé en JSON) : au-delà, il est tronqué pour éviter d'exploser les
# coûts et le contexte du provider (section 21/38).
MAX_TOOL_RESULT_CHARS = 8000


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        authorization_policy: ToolAuthorizationPolicy | None = None,
        idempotency_store: AIToolExecutionIdempotencyStore | None = None,
    ) -> None:
        self._registry = registry
        self._authorization_policy = authorization_policy
        self._idempotency_store = idempotency_store

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

            if self._authorization_policy is None:
                raise ToolAuthorizationError("Tool authorization is not configured.")
            self._authorization_policy.authorize(tool, context)

            try:
                arguments = tool.input_schema.model_validate(raw_arguments)
            except ValidationError as exc:
                raise ToolValidationError(f"Invalid arguments for '{name}'.") from exc

            if tool.mutates and tool.confirmation_policy != "explicit_user_confirmation":
                raise ToolAuthorizationError("The mutating tool has no supported confirmation policy.")
            if tool.mutates:
                confirmed = getattr(arguments, tool.confirmation_field, False) is True
                explicit_confirmation = (
                    confirmed and context.user_message.strip().casefold() == "/confirm"
                )
                natural_confirmation = False
                if (
                    not explicit_confirmation
                    and is_natural_confirmation(context.locale, context.user_message)
                ):
                    if self._idempotency_store is None:
                        raise ToolAuthorizationError("Mutation idempotency is not configured.")
                    natural_confirmation = self._idempotency_store.consume_confirmation_challenge(
                        context, tool, raw_arguments
                    )
                if not explicit_confirmation and not natural_confirmation:
                    if self._idempotency_store is None:
                        raise ToolAuthorizationError("Mutation idempotency is not configured.")
                    self._idempotency_store.create_confirmation_challenge(
                        context,
                        tool,
                        raw_arguments,
                        context.locale,
                    )
                    return ToolResult(
                        success=False,
                        data={"confirmation_required": True, "operation": name, "error_key": "confirmation_required"},
                        metadata={"error_key": "confirmation_required", "locale": context.locale},
                        error=confirmation_required_message(context.locale),
                    )

            try:
                async def run_tool() -> ToolResult:
                    return await asyncio.wait_for(
                        tool.run(context, arguments), timeout=tool.timeout_seconds
                    )

                if tool.mutates:
                    if self._idempotency_store is None:
                        raise ToolAuthorizationError("Mutation idempotency is not configured.")
                    result = await self._idempotency_store.run_once(
                        context, tool, raw_arguments, run_tool
                    )
                else:
                    result = await run_tool()
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
