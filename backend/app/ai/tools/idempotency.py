"""Durable at-most-once execution receipts for mutating AI tools."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.ai.tools.base import AITool
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.ai.tools.exceptions import ToolAuthorizationError, ToolExecutionError
from backend.app.models import AIToolExecutionRecord


class AIToolExecutionIdempotencyStore:
    def __init__(self, db: Session) -> None:
        self._db = db

    async def run_once(
        self,
        context: ToolExecutionContext,
        tool: AITool,
        arguments: dict[str, Any],
        run: Callable[[], Awaitable[ToolResult]],
    ) -> ToolResult:
        serialized_arguments = json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)
        arguments_hash = hashlib.sha256(serialized_arguments.encode("utf-8")).hexdigest()
        key = f"ai-tool:{context.tenant_id}:{context.request_id}:{tool.name}"
        if self._db.get_bind().dialect.name == "postgresql":
            self._db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": key},
            )
        statement = (
            select(AIToolExecutionRecord)
            .where(
                AIToolExecutionRecord.company_id == context.tenant_id,
                AIToolExecutionRecord.request_id == context.request_id,
                AIToolExecutionRecord.tool_name == tool.name,
            )
            .with_for_update()
        )
        record = self._db.scalar(statement)
        if record is not None:
            if (
                record.user_id != context.user_id
                or record.conversation_id != context.conversation_id
                or record.agent_id != context.selected_agent_id
                or record.arguments_hash != arguments_hash
            ):
                raise ToolAuthorizationError("The idempotency key was already used for a different action.")
            if record.status == "completed" and record.result is not None:
                return _restore_result(record.result)
            raise ToolExecutionError("This action is already in progress and will not be replayed.")

        record = AIToolExecutionRecord(
            company_id=context.tenant_id,
            user_id=context.user_id,
            conversation_id=context.conversation_id,
            request_id=context.request_id,
            agent_id=context.selected_agent_id or "",
            tool_name=tool.name,
            arguments_hash=arguments_hash,
            status="in_progress",
        )
        self._db.add(record)
        try:
            self._db.commit()
        except IntegrityError:
            self._db.rollback()
            raise ToolExecutionError("This action is already in progress and will not be replayed.")

        result = await run()
        record = self._db.get(AIToolExecutionRecord, record.id)
        if record is None:
            raise ToolExecutionError("The action receipt was lost; replay is blocked.")
        record.status = "completed"
        record.result = _serialize_result(result)
        record.completed_at = datetime.now(timezone.utc)
        self._db.commit()
        return result


def _serialize_result(result: ToolResult) -> dict[str, Any]:
    return json.loads(json.dumps({
        "success": result.success,
        "data": result.data,
        "source_refs": result.source_refs,
        "metadata": result.metadata,
        "error": result.error,
    }, default=str))


def _restore_result(data: dict[str, Any]) -> ToolResult:
    return ToolResult(
        success=bool(data.get("success")),
        data=data.get("data") or {},
        source_refs=tuple(data.get("source_refs") or ()),
        metadata=data.get("metadata") or {},
        error=data.get("error"),
    )