from pathlib import Path
import importlib.util
from io import StringIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.ai.chat.orchestrator import ToolOrchestrator
from backend.app.ai.llm.base import LLMProvider
from backend.app.ai.llm.schemas import LLMGeneration, LLMToolResponse
from backend.app.ai.tools.authorization import ToolAuthorizationPolicy
from backend.app.ai.tools.base import AITool, ToolArguments
from backend.app.ai.tools.contracts import ToolCall, ToolExecutionContext, ToolResult
from backend.app.ai.tools.contracts import ToolCall, ToolExecutionContext, ToolResult
from backend.app.ai.tools.exceptions import ToolAuthorizationError
from backend.app.ai.tools.executor import ToolExecutor
from backend.app.ai.tools.idempotency import AIToolExecutionIdempotencyStore
from backend.app.ai.tools.registry import ToolRegistry
from backend.app.ai.request_identity import reconcile_idempotency_keys, resolve_ai_request_id
from backend.app.assistants.registry import build_default_assistant_registry
from backend.app.dependencies.ai_authorization import get_active_ai_membership
from backend.app.assistants.contracts import AssistantDefinition, AssistantStatus
from backend.app.assistants.registry import AssistantRegistry
from backend.app.models import AIToolExecutionRecord, Base, Company, CompanyMembership, User, UserRole
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.routers.ai_chat import _authorized_agent
from shared.ai_engine.contracts import TenantContext


class ReadArgs(ToolArguments):
    pass


class MutationArgs(ToolArguments):
    confirmed: bool = False


class RetailReadTool(AITool):
    name = "retail_read"
    description = "Read-only test tool"
    input_schema = ReadArgs
    read_only = True
    mutates = False

    def __init__(self) -> None:
        self.calls = 0

    async def run(self, context, arguments) -> ToolResult:
        self.calls += 1
        return ToolResult(success=True, data={"tenant_id": str(context.tenant_id)})


class MutatingTool(AITool):
    name = "retail_write"
    description = "Mutating test tool"
    input_schema = MutationArgs
    read_only = False
    mutates = True
    mutation_capabilities = frozenset({"retail.write"})
    confirmation_policy = "explicit_user_confirmation"

    def __init__(self) -> None:
        self.calls = 0

    async def run(self, context, arguments) -> ToolResult:
        self.calls += 1
        return ToolResult(success=True, data={"written": True})


class UnsafeMutatingTool(AITool):
    name = "unsafe_write"
    description = "Mutating test tool without confirmation policy"
    read_only = False
    mutates = True
    mutation_capabilities = frozenset({"retail.write"})

    async def run(self, context, arguments) -> ToolResult:
        return ToolResult(success=True)


@pytest.fixture
def security_context(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ai-execution-security.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        company = Company(
            name="Tenant A", slug="tenant-a", email="a@example.ca",
            country="CA", timezone="America/Toronto", industry="Retail",
            subscription_plan="base",
        )
        db.add(company)
        db.flush()
        user = User(
            company_id=company.id, first_name="A", last_name="User",
            email="user@example.ca", password_hash="hash", role=UserRole.OWNER,
            is_active=True,
        )
        db.add(user)
        db.flush()
        membership = CompanyMembership(
            user_id=user.id, company_id=company.id, role=UserRole.OWNER, is_active=True,
        )
        db.add(membership)
        db.flush()
        ModuleEntitlementService(db).activate_module(TenantContext(company.id), "retail")

        agents = AssistantRegistry()
        agents.register(AssistantDefinition(
            slug="retail", name_key="agent.retail.name",
            description_key="agent.retail.description",
            status=AssistantStatus.AVAILABLE, category="commerce",
            module_code="retail", allowed_tool_names=frozenset({"retail_read"}),
        ))
        agents.register(AssistantDefinition(
            slug="other", name_key="agent.other.name",
            description_key="agent.other.description",
            status=AssistantStatus.AVAILABLE, category="other",
            module_code="retail", allowed_tool_names=frozenset({"other_tool"}),
        ))
        agents.register(AssistantDefinition(
            slug="retail_writer", name_key="agent.retail_writer.name",
            description_key="agent.retail_writer.description",
            status=AssistantStatus.AVAILABLE, category="commerce",
            module_code="retail", allowed_tool_names=frozenset({"retail_write"}),
            mutation_capabilities=frozenset({"retail.write"}),
            supported_operations=frozenset({"retail.write"}),
            confirmation_policy="explicit_user_confirmation",
        ))
        agents.register(AssistantDefinition(
            slug="crm", name_key="agent.crm.name",
            description_key="agent.crm.description",
            status=AssistantStatus.AVAILABLE, category="customer",
            module_code="crm", allowed_tool_names=frozenset({"retail_read"}),
        ))
        tool = RetailReadTool()
        mutating_tool = MutatingTool()
        tools = ToolRegistry()
        tools.register(tool)
        tools.register(mutating_tool)
        executor = ToolExecutor(
            tools,
            ToolAuthorizationPolicy(db, agents),
            AIToolExecutionIdempotencyStore(db),
        )

        def context(*, tenant_id=None, agent_id="retail"):
            return ToolExecutionContext(
                tenant=TenantContext(tenant_id or company.id),
                user_id=user.id,
                permissions=frozenset({"ai:use"}),
                request_id=str(uuid4()),
                selected_agent_id=agent_id,
            )

        yield db, company, user, membership, tool, mutating_tool, executor, context


@pytest.mark.asyncio
async def test_authorized_read_only_tool_succeeds(security_context) -> None:
    db, company, _, _, tool, _, executor, context = security_context

    result = await executor.execute("retail_read", context(), {})

    assert result.success is True
    assert result.data["tenant_id"] == str(company.id)
    assert tool.calls == 1


@pytest.mark.asyncio
async def test_inactive_membership_is_denied_at_execution(security_context) -> None:
    db, _, _, membership, tool, _, executor, context = security_context
    membership.is_active = False
    db.flush()

    with pytest.raises(ToolAuthorizationError):
        await executor.execute("retail_read", context(), {})
    assert tool.calls == 0


def test_ai_route_requires_active_company_membership(security_context) -> None:
    db, _, user, membership, _, _, _, _ = security_context
    identity = SimpleNamespace(user=user)

    assert get_active_ai_membership(identity, db) is membership
    membership.is_active = False
    db.flush()
    with pytest.raises(HTTPException) as error:
        get_active_ai_membership(identity, db)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_wrong_tenant_is_denied_at_execution(security_context) -> None:
    db, _, _, _, tool, _, executor, context = security_context
    other = Company(
        name="Tenant B", slug="tenant-b", email="b@example.ca",
        country="CA", timezone="America/Toronto", industry="Retail",
        subscription_plan="base",
    )
    db.add(other)
    db.flush()

    with pytest.raises(ToolAuthorizationError):
        await executor.execute("retail_read", context(tenant_id=other.id), {})
    assert tool.calls == 0


@pytest.mark.asyncio
async def test_wrong_agent_cannot_use_another_agents_tool(security_context) -> None:
    _, _, _, _, tool, _, executor, context = security_context

    with pytest.raises(ToolAuthorizationError):
        await executor.execute("retail_read", context(agent_id="other"), {})
    assert tool.calls == 0


@pytest.mark.asyncio
async def test_wrong_module_is_denied_even_when_tool_is_in_agent_allowlist(security_context) -> None:
    _, _, _, _, tool, _, executor, context = security_context

    with pytest.raises(ToolAuthorizationError):
        await executor.execute("retail_read", context(agent_id="crm"), {})
    assert tool.calls == 0


def test_legacy_chat_routes_only_to_registered_entitled_agent(security_context) -> None:
    db, company, _, _, _, _, _, _ = security_context
    tenant = TenantContext(company_id=company.id)
    registry = build_default_assistant_registry()

    assert _authorized_agent("Write a poem", None, tenant, db, registry) is None
    assert _authorized_agent("Show sales trends", None, tenant, db, registry).slug == "retail"
    with pytest.raises(HTTPException) as error:
        _authorized_agent("Prioritize CRM leads", None, tenant, db, registry)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_membership_role_not_user_role_controls_tool_permission(security_context) -> None:
    db, _, _, membership, tool, _, executor, context = security_context
    membership.role = UserRole.VIEWER
    db.flush()
    tool.required_permissions = ("ai:use",)
    
    with pytest.raises(ToolAuthorizationError):
        await executor.execute("retail_read", context(), {})
    assert tool.calls == 0


@pytest.mark.asyncio
async def test_mutation_requires_registered_capability_and_explicit_user_confirmation(security_context) -> None:
    _, _, _, _, _, tool, executor, context = security_context

    unconfirmed_context = context(agent_id="retail_writer")
    unconfirmed_context = ToolExecutionContext(
        tenant=unconfirmed_context.tenant,
        user_id=unconfirmed_context.user_id,
        permissions=unconfirmed_context.permissions,
        request_id=unconfirmed_context.request_id,
        selected_agent_id=unconfirmed_context.selected_agent_id,
        user_message="Please do this",
    )
    denied = await executor.execute(
        "retail_write",
        unconfirmed_context,
        {"confirmed": True},
    )
    assert denied.data["confirmation_required"] is True
    assert tool.calls == 0

    confirmed_context = context(agent_id="retail_writer")
    confirmed_context = ToolExecutionContext(
        tenant=confirmed_context.tenant,
        user_id=confirmed_context.user_id,
        permissions=confirmed_context.permissions,
        request_id=confirmed_context.request_id,
        selected_agent_id=confirmed_context.selected_agent_id,
        user_message="Yes, I confirm",
    )
    result = await executor.execute("retail_write", confirmed_context, {"confirmed": True})
    assert result.success is True
    assert tool.calls == 1


def test_registry_rejects_mutating_tool_without_confirmation_policy() -> None:
    with pytest.raises(ValueError, match="explicit user confirmation"):
        ToolRegistry().register(UnsafeMutatingTool())


@pytest.mark.asyncio
async def test_confirmed_mutation_retry_returns_receipt_without_second_execution(security_context) -> None:
    db, _, _, _, _, tool, executor, context = security_context
    base = context(agent_id="retail_writer")
    confirmed_context = ToolExecutionContext(
        tenant=base.tenant,
        user_id=base.user_id,
        permissions=base.permissions,
        request_id="same-request",
        conversation_id=base.conversation_id,
        selected_agent_id=base.selected_agent_id,
        user_message="Yes, I confirm",
    )

    first = await executor.execute(
        "retail_write", confirmed_context, {"confirmed": True}
    )
    replay = await executor.execute(
        "retail_write", confirmed_context, {"confirmed": True}
    )

    assert first == replay
    assert tool.calls == 1
    assert db.query(AIToolExecutionRecord).count() == 1


@pytest.mark.asyncio
async def test_revoked_membership_blocks_replay_of_completed_mutation(security_context) -> None:
    db, _, _, membership, _, tool, executor, context = security_context
    base = context(agent_id="retail_writer")
    confirmed_context = ToolExecutionContext(
        tenant=base.tenant,
        user_id=base.user_id,
        permissions=base.permissions,
        request_id="revocation-request",
        conversation_id=base.conversation_id,
        selected_agent_id=base.selected_agent_id,
        user_message="Yes, I confirm",
    )
    await executor.execute("retail_write", confirmed_context, {"confirmed": True})
    membership.is_active = False
    db.flush()

    with pytest.raises(ToolAuthorizationError):
        await executor.execute("retail_write", confirmed_context, {"confirmed": True})
    assert tool.calls == 1


@pytest.mark.asyncio
async def test_repeated_provider_tool_call_does_not_repeat_mutation(security_context) -> None:
    _, _, _, _, _, tool, executor, context = security_context
    base = context(agent_id="retail_writer")
    confirmed_context = ToolExecutionContext(
        tenant=base.tenant,
        user_id=base.user_id,
        permissions=base.permissions,
        request_id="provider-retry-request",
        selected_agent_id=base.selected_agent_id,
        user_message="Yes, I confirm",
    )

    class RepeatingToolProvider(LLMProvider):
        name = "repeating-test-provider"
        supports_tool_calling = True

        def __init__(self) -> None:
            self.calls = 0

        async def generate(self, *, system_instruction: str, prompt: str) -> LLMGeneration:
            return LLMGeneration("done", self.name, "test-model")

        async def stream(self, *, system_instruction: str, prompt: str):
            yield "done"

        async def generate_with_tools(self, *, system_instruction, messages, tools) -> LLMToolResponse:
            self.calls += 1
            if self.calls <= 2:
                return LLMToolResponse(
                    content=None,
                    tool_calls=(ToolCall(id=f"call-{self.calls}", name="retail_write", arguments={"confirmed": True}),),
                    provider=self.name,
                    model="test-model",
                )
            return LLMToolResponse(content="Done", tool_calls=(), provider=self.name, model="test-model")

    provider = RepeatingToolProvider()
    result = await ToolOrchestrator(provider, executor).run(
        system_instruction="test",
        user_query="Yes, I confirm",
        context=confirmed_context,
        available_tools=(tool,),
    )

    assert result.content == "Done"
    assert len(result.tool_call_results) == 2
    assert all(item.result.success for item in result.tool_call_results)
    assert tool.calls == 1


def test_request_id_is_stable_and_scoped_to_tenant_user_and_conversation() -> None:
    tenant_id, user_id, conversation_id = uuid4(), uuid4(), uuid4()
    request_id = resolve_ai_request_id(
        "client-request-1", tenant_id=tenant_id, user_id=user_id,
        conversation_id=conversation_id,
    )
    assert request_id == resolve_ai_request_id(
        "client-request-1", tenant_id=tenant_id, user_id=user_id,
        conversation_id=conversation_id,
    )
    assert request_id != resolve_ai_request_id(
        "client-request-1", tenant_id=tenant_id, user_id=uuid4(),
        conversation_id=conversation_id,
    )
    assert reconcile_idempotency_keys("same", "same") == "same"
    with pytest.raises(ValueError):
        reconcile_idempotency_keys("header", "body")


def test_idempotency_migration_creates_additive_receipt_table(monkeypatch) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    migration_path = (
        Path(__file__).resolve().parents[2]
        / "alembic" / "versions" / "0028_ai_tool_execution_idempotency.py"
    )
    spec = importlib.util.spec_from_file_location("ai_tool_execution_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(migration)

    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    monkeypatch.setattr(migration, "op", Operations(context))
    migration.upgrade()
    sql = output.getvalue()

    assert migration.down_revision == "0027_crm_recipient_safety"
    assert migration.revision == "0028_ai_tool_execution_idempotency"
    assert "CREATE TABLE ai_tool_execution_records" in sql
    assert "uq_ai_tool_execution_request_tool" in sql
    assert "CREATE INDEX ix_ai_tool_execution_records_company_id" in sql
    assert "CREATE INDEX ix_ai_tool_execution_records_user_id" in sql
    assert "CREATE INDEX ix_ai_tool_execution_records_conversation_id" in sql