"""Lot 2 — TenantExecutionContext binding and tool-call tenant hardening."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from starlette.requests import Request

from backend.app.ai.tools.base import AITool, ToolArguments
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.ai.tools.exceptions import ToolAuthorizationError
from backend.app.ai.tools.executor import ToolExecutor
from backend.app.ai.tools.registry import ToolRegistry
from backend.app.core.tenant_execution import (
    TenantExecutionContext,
    TenantExecutionError,
    bind_tenant_execution,
    client_tenant_override,
    current_tenant_execution,
    peek_tenant_execution,
    require_same_tenant,
    reset_tenant_execution,
    strip_client_tenant_arguments,
    tenant_execution_var,
)
from backend.app.dependencies.auth import get_current_identity
from backend.app.models.base import UserRole
from shared.ai_engine.contracts import TenantContext


@pytest.fixture(autouse=True)
def _isolate_tenant_execution():
    token = tenant_execution_var.set(None)
    try:
        yield
    finally:
        reset_tenant_execution(token)


def _execution(company_id=None, user_id=None) -> TenantExecutionContext:
    company_id = company_id or uuid4()
    user_id = user_id or uuid4()
    return TenantExecutionContext(
        tenant=TenantContext(company_id=company_id, user_id=user_id),
        user_id=user_id,
        permissions=frozenset({"ai:use"}),
        request_id="req-1",
        source="session",
    )


def test_require_same_tenant_rejects_foreign_company() -> None:
    context = _execution()
    token = bind_tenant_execution(context)
    try:
        assert require_same_tenant(context.company_id).company_id == context.company_id
        with pytest.raises(TenantExecutionError):
            require_same_tenant(uuid4())
    finally:
        reset_tenant_execution(token)
    with pytest.raises(TenantExecutionError):
        current_tenant_execution()


def test_strip_and_detect_client_tenant_selectors() -> None:
    raw = {
        "query": "top products",
        "company_id": str(uuid4()),
        "tenant_id": str(uuid4()),
        "limit": 5,
    }
    cleaned = strip_client_tenant_arguments(raw)
    assert cleaned == {"query": "top products", "limit": 5}
    assert client_tenant_override(headers={"X-Company-Id": str(uuid4())}) is not None
    assert client_tenant_override(query={"q": "hello"}) is None


def test_get_current_identity_binds_execution_context(monkeypatch) -> None:
    company_id = uuid4()
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        company_id=company_id,
        is_platform_admin=False,
        role=UserRole.OWNER,
    )
    monkeypatch.setattr(
        "backend.app.dependencies.auth.apply_tenant_rls",
        lambda session, cid, *, bypass=False: None,
    )
    request = Request({"type": "http", "method": "GET", "path": "/api/v1/ai/chat/conversations", "headers": []})
    get_current_identity(
        request,
        credentials=SimpleNamespace(scheme="Bearer", credentials="access-token"),
        service=SimpleNamespace(authenticate=lambda _token: (SimpleNamespace(), user)),
        db=object(),
    )
    bound = peek_tenant_execution()
    assert bound is not None
    assert bound.company_id == company_id
    assert bound.user_id == user_id
    assert bound.source == "session"
    assert "company:manage" in bound.permissions


class _EchoTool(AITool):
    name = "echo_query"
    description = "Echo"
    input_schema = ToolArguments
    required_permissions = ("ai:use",)
    read_only = True
    mutates = False
    agent_ids = frozenset({"retail"})

    async def run(self, context, arguments):
        return ToolResult(success=True, data={"tenant": str(context.tenant_id)})


class _AllowAll:
    def authorize(self, tool, context) -> None:
        return None


@pytest.mark.asyncio
async def test_tool_executor_strips_foreign_tenant_arguments_and_keeps_bound_tenant() -> None:
    company_a = uuid4()
    user_a = uuid4()
    execution = _execution(company_a, user_a)
    token = bind_tenant_execution(execution)
    registry = ToolRegistry()
    registry.register(_EchoTool())
    executor = ToolExecutor(registry, _AllowAll())
    tool_context = ToolExecutionContext(
        tenant=execution.tenant,
        user_id=user_a,
        permissions=frozenset({"ai:use"}),
        request_id="req-1",
        selected_agent_id="retail",
    )
    try:
        result = await executor.execute(
            "echo_query",
            tool_context,
            {"company_id": str(uuid4()), "tenant_id": str(uuid4())},
        )
        assert result.success is True
        assert result.data["tenant"] == str(company_a)
    finally:
        reset_tenant_execution(token)


@pytest.mark.asyncio
async def test_tool_executor_rejects_mismatched_bound_tenant() -> None:
    company_a = uuid4()
    company_b = uuid4()
    token = bind_tenant_execution(_execution(company_a))
    registry = ToolRegistry()
    registry.register(_EchoTool())
    executor = ToolExecutor(registry, _AllowAll())
    foreign = ToolExecutionContext(
        tenant=TenantContext(company_id=company_b),
        user_id=uuid4(),
        permissions=frozenset({"ai:use"}),
        request_id="req-1",
        selected_agent_id="retail",
    )
    try:
        with pytest.raises(ToolAuthorizationError, match="bound tenant"):
            await executor.execute("echo_query", foreign, {})
    finally:
        reset_tenant_execution(token)


def test_tool_context_from_execution_ignores_client_company() -> None:
    execution = _execution()
    client_company = uuid4()
    context = ToolExecutionContext.from_execution(execution, selected_agent_id="central")
    assert context.tenant_id == execution.company_id
    assert context.tenant_id != client_company
