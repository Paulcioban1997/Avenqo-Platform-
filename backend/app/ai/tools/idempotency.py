"""Durable at-most-once execution receipts for mutating AI tools."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.ai.tools.base import AITool
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.ai.tools.exceptions import ToolAuthorizationError, ToolExecutionError
from backend.app.models import AIToolConfirmationChallenge, AIToolExecutionRecord


def mutation_arguments_hash(arguments: dict[str, Any], confirmation_field: str = "confirmed") -> str:
    normalized = dict(arguments)
    normalized.pop(confirmation_field, None)
    serialized = json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class AIToolExecutionIdempotencyStore:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create_confirmation_challenge(
        self,
        context: ToolExecutionContext,
        tool: AITool,
        arguments: dict[str, Any],
        locale: str,
        *,
        ttl_seconds: int = 600,
    ) -> None:
        agent_id = context.authorized_tool_agents.get(tool.name, context.selected_agent_id) or ""
        issued_at = datetime.now(timezone.utc)
        challenge = AIToolConfirmationChallenge(
            company_id=context.tenant_id,
            user_id=context.user_id,
            conversation_id=context.conversation_id,
            request_id=context.request_id,
            agent_id=agent_id,
            tool_name=tool.name,
            arguments_hash=mutation_arguments_hash(arguments, tool.confirmation_field),
            locale=locale,
            created_at=issued_at,
            expires_at=issued_at + timedelta(seconds=ttl_seconds),
        )
        self._db.add(challenge)
        self._db.commit()

    def consume_confirmation_challenge(
        self,
        context: ToolExecutionContext,
        tool: AITool,
        arguments: dict[str, Any],
    ) -> bool:
        now = datetime.now(timezone.utc)
        agent_id = context.authorized_tool_agents.get(tool.name, context.selected_agent_id) or ""
        # Booking confirms only the latest exact proposal in Central and Voice.
        strict_proposal = context.voice_path or tool.name == "create_appointment"
        expected_hash = mutation_arguments_hash(arguments, tool.confirmation_field)
        statement = (
            select(AIToolConfirmationChallenge)
            .where(
                AIToolConfirmationChallenge.company_id == context.tenant_id,
                AIToolConfirmationChallenge.user_id == context.user_id,
                AIToolConfirmationChallenge.conversation_id == context.conversation_id,
                AIToolConfirmationChallenge.tool_name == tool.name,
                AIToolConfirmationChallenge.consumed_at.is_(None),
                AIToolConfirmationChallenge.expires_at > now,
            )
            .order_by(AIToolConfirmationChallenge.created_at.desc())
            .with_for_update()
        )
        if not strict_proposal:
            statement = statement.where(AIToolConfirmationChallenge.arguments_hash == expected_hash)
        challenge = self._db.scalar(statement)
        if strict_proposal and challenge is not None and challenge.arguments_hash != expected_hash:
            return False
        if challenge is None and not strict_proposal:
            # Fallback to active unconsumed challenge for the conversation and tool
            fallback_statement = (
                select(AIToolConfirmationChallenge)
                .where(
                    AIToolConfirmationChallenge.company_id == context.tenant_id,
                    AIToolConfirmationChallenge.user_id == context.user_id,
                    AIToolConfirmationChallenge.conversation_id == context.conversation_id,
                    AIToolConfirmationChallenge.tool_name == tool.name,
                    AIToolConfirmationChallenge.consumed_at.is_(None),
                    AIToolConfirmationChallenge.expires_at > now,
                )
                .order_by(AIToolConfirmationChallenge.created_at.desc())
                .with_for_update()
            )
            challenge = self._db.scalar(fallback_statement)
        if challenge is None:
            return False
        challenge.consumed_at = now
        self._db.commit()
        return True

    async def run_once(
        self,
        context: ToolExecutionContext,
        tool: AITool,
        arguments: dict[str, Any],
        run: Callable[[], Awaitable[ToolResult]],
    ) -> ToolResult:
        serialized_arguments = json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)
        arguments_hash = hashlib.sha256(serialized_arguments.encode("utf-8")).hexdigest()
        agent_id = context.authorized_tool_agents.get(
            tool.name,
            context.selected_agent_id,
        ) or ""
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
                or record.agent_id != agent_id
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
            agent_id=agent_id,
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
