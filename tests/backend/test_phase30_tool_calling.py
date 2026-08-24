"""Phase 30 — LLM Tool Calling (Business Copilot).

Couvre : contrats/sécurité de `ToolExecutionContext`, filtrage du
`ToolRegistry` (permissions/plan/capacité), pipeline du `ToolExecutor`
(validation, autorisation, timeout, erreurs, troncature), outils métier réels
(ventes/clients, calculés sur `PreparedCompanyDataset`, jamais de données
fictives), l'outil inventaire volontairement toujours indisponible,
l'orchestrateur de tool calling borné (`ToolOrchestrator`), et l'intégration
bout-en-bout dans `ChatService` (avec repli sans tool calling en rétro-
compatibilité, sources persistées, et isolation multi-tenant).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.ai.chat.chat_service import ChatService
from backend.app.ai.chat.conversation_service import ConversationService
from backend.app.ai.chat.orchestrator import MAX_TOOL_ITERATIONS, OrchestrationResult, ToolOrchestrator
from backend.app.ai.chat.retrieval_service import RetrievalService
from backend.app.ai.llm.base import LLMProvider
from backend.app.ai.llm.exceptions import ToolCallingUnsupportedError
from backend.app.ai.llm.schemas import LLMGeneration, LLMMessage, LLMToolResponse
from backend.app.ai.tools.base import AITool, ToolArguments
from backend.app.ai.tools.business import customer_tools, sales_tools
from backend.app.ai.tools.business.analytics import compute_business_overview
from backend.app.ai.tools.business.customer_tools import GetCustomerSegmentsTool, GetCustomerSummaryTool
from backend.app.ai.tools.business.dataset_access import latest_ready_dataset, load_latest_prepared_dataset
from backend.app.ai.tools.business.inventory_tools import GetInventorySummaryTool
from backend.app.ai.tools.business.registry_factory import build_business_tool_registry, resolve_tenant_capabilities
from backend.app.ai.tools.business.sales_tools import (
    GetBusinessOverviewTool,
    GetSalesComparisonTool,
    GetSalesSummaryTool,
    GetSalesTrendTool,
    GetTopProductsTool,
)
from backend.app.ai.tools.contracts import ToolCall, ToolExecutionContext, ToolResult
from backend.app.ai.tools.exceptions import (
    ToolAuthorizationError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolTimeoutError,
    ToolUnavailableError,
    ToolValidationError,
)
from backend.app.ai.tools.executor import MAX_TOOL_RESULT_CHARS, ToolExecutor
from backend.app.ai.tools.plans import plan_meets_minimum
from backend.app.ai.tools.registry import ToolRegistry
from backend.app.core.permissions import permissions_for
from backend.app.models import Base, Company, Dataset, DatasetStatus, User, UserRole
from backend.app.services.portfolio_decision_service import PortfolioAnalysisUnavailable
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_ingestion.cleaning import CompanyDatasetCleaner
from shared.ai_engine.dataset_ingestion.prepared_dataset import PreparedCompanyDataset
from shared.ai_engine.dataset_ingestion.profiling import DatasetProfiler
from shared.ai_engine.dataset_ingestion.quality import assess_quality
from shared.ai_engine.dataset_ingestion.readiness import assess_capability_readiness

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


CANONICAL_COLUMNS = {
    "customer_id": "customer_id",
    "order_id": "order_id",
    "product_id": "product_id",
    "order_timestamp": "order_timestamp",
    "quantity": "quantity",
    "total_amount": "total_amount",
}


def _rows(count: int = 6) -> list[dict[str, object]]:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        {
            "customer_id": f"cust-{i % 3}",
            "order_id": f"order-{i}",
            "product_id": f"prod-{i % 2}",
            "order_timestamp": (base + timedelta(days=i)).isoformat(),
            "quantity": i + 1,
            "total_amount": 10.0 * (i + 1),
        }
        for i in range(count)
    ]


def _prepared_dataset(company_id=None, dataset_id=None) -> PreparedCompanyDataset:
    rows = _rows()
    cleaner = CompanyDatasetCleaner()
    cleaned_rows, cleaning_report = cleaner.clean(rows, CANONICAL_COLUMNS)
    profile = DatasetProfiler().profile(cleaned_rows, tuple(CANONICAL_COLUMNS))
    quality = assess_quality(cleaning_report)
    readiness = assess_capability_readiness(set(CANONICAL_COLUMNS.values()))
    return PreparedCompanyDataset(
        company_id=company_id or uuid4(),
        dataset_id=dataset_id or uuid4(),
        version=1,
        canonical_columns=CANONICAL_COLUMNS,
        rows=tuple(cleaned_rows),
        profile=profile,
        mapping=(),
        cleaning_report=cleaning_report,
        quality=quality,
        capability_readiness=readiness,
    )


class FakeIngestionService:
    """Double minimal : renvoie un `PreparedCompanyDataset` déterministe sans DB/stockage réel."""

    def __init__(self, prepared: PreparedCompanyDataset) -> None:
        self._prepared = prepared

    def get_prepared_dataset(self, tenant: TenantContext, dataset_id) -> PreparedCompanyDataset:
        return self._prepared


class EmptyIngestionService:
    def get_prepared_dataset(self, tenant: TenantContext, dataset_id) -> PreparedCompanyDataset:
        raise AssertionError("should not be called when no ready dataset exists")


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'phase30.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.fixture
def tenant_with_ready_dataset(db_session):
    company = Company(
        name="Company A", slug="company-a", email="a@example.com", country="CA",
        timezone="America/Toronto", industry="Retail", subscription_plan="demo",
    )
    db_session.add(company); db_session.flush()
    user = User(company_id=company.id, first_name="Ana", last_name="Lyst", email="analyst@example.com", password_hash="hash", role=UserRole.ANALYST)
    db_session.add(user); db_session.flush()
    dataset = Dataset(company_id=company.id, name="Sales", type="csv", source="sales.csv", rows_count=6, columns_count=6, status=DatasetStatus.READY)
    db_session.add(dataset); db_session.commit()

    tenant = TenantContext(company_id=company.id)
    prepared = _prepared_dataset(company_id=company.id, dataset_id=dataset.id)
    ingestion = FakeIngestionService(prepared)
    context = ToolExecutionContext(tenant=tenant, user_id=user.id, permissions=frozenset(permissions_for(UserRole.ANALYST)), request_id="req-1")
    return db_session, company, user, dataset, tenant, ingestion, context


class FakeLLMProvider(LLMProvider):
    name = "fake"
    supports_tool_calling = True

    def __init__(self, tool_responses: list[LLMToolResponse] | None = None, plain_content: str = "plain answer"):
        self._tool_responses = list(tool_responses or [])
        self._plain_content = plain_content
        self.generate_calls = 0
        self.generate_with_tools_calls = 0

    async def generate(self, *, system_instruction: str, prompt: str) -> LLMGeneration:
        self.generate_calls += 1
        return LLMGeneration(content=self._plain_content, provider=self.name, model="fake-model")

    async def stream(self, *, system_instruction: str, prompt: str):
        yield self._plain_content

    async def generate_with_tools(self, *, system_instruction, messages, tools) -> LLMToolResponse:
        self.generate_with_tools_calls += 1
        if self._tool_responses:
            return self._tool_responses.pop(0)
        return LLMToolResponse(content=self._plain_content, tool_calls=(), provider=self.name, model="fake-model")


class UnsupportedLLMProvider(LLMProvider):
    name = "no-tools"
    supports_tool_calling = False

    async def generate(self, *, system_instruction: str, prompt: str) -> LLMGeneration:
        return LLMGeneration(content="fallback answer", provider=self.name, model="fake-model")

    async def stream(self, *, system_instruction: str, prompt: str):
        yield "fallback answer"


# ---------------------------------------------------------------------------
# 1. Contracts & security invariants
# ---------------------------------------------------------------------------


async def test_tool_execution_context_tenant_id_derives_from_tenant_context() -> None:
    tenant = TenantContext(company_id=uuid4())
    context = ToolExecutionContext(tenant=tenant, user_id=uuid4(), permissions=frozenset({"ai:use"}), request_id="r1")

    assert context.tenant_id == tenant.company_id


async def test_tool_result_defaults_are_empty_and_safe() -> None:
    result = ToolResult(success=True)

    assert result.data == {}
    assert result.source_refs == ()
    assert result.error is None


# ---------------------------------------------------------------------------
# 2. ToolRegistry filtering
# ---------------------------------------------------------------------------


class _DummyArgs(ToolArguments):
    pass


class _DummyTool(AITool):
    name = "dummy_tool"
    description = "A dummy tool."
    input_schema = _DummyArgs
    required_permissions = ("ai:use", "data:read")
    minimum_plan = "professional"
    requires_capability = "segmentation"

    async def run(self, context, arguments) -> ToolResult:
        return ToolResult(success=True, data={"ok": True})


def test_registry_available_for_filters_by_permission_plan_and_capability() -> None:
    registry = ToolRegistry()
    registry.register(_DummyTool())

    assert registry.available_for(permissions=frozenset({"ai:use"}), plan_code="professional", capabilities=frozenset({"segmentation"})) == ()
    assert registry.available_for(permissions=frozenset({"ai:use", "data:read"}), plan_code="demo", capabilities=frozenset({"segmentation"})) == ()
    assert registry.available_for(permissions=frozenset({"ai:use", "data:read"}), plan_code="professional", capabilities=frozenset()) == ()

    available = registry.available_for(permissions=frozenset({"ai:use", "data:read"}), plan_code="professional", capabilities=frozenset({"segmentation"}))
    assert [tool.name for tool in available] == ["dummy_tool"]


def test_plan_meets_minimum_rank_semantics() -> None:
    assert plan_meets_minimum(None, None) is True
    assert plan_meets_minimum("demo", None) is True
    assert plan_meets_minimum("demo", "professional") is False
    assert plan_meets_minimum("enterprise", "professional") is True
    assert plan_meets_minimum("custom_enterprise", "enterprise") is True
    assert plan_meets_minimum(None, "demo") is True
    assert plan_meets_minimum(None, "professional") is False


# ---------------------------------------------------------------------------
# 3. ToolExecutor pipeline
# ---------------------------------------------------------------------------


def _executor_context(permissions: frozenset[str] = frozenset({"ai:use"})) -> ToolExecutionContext:
    return ToolExecutionContext(tenant=TenantContext(company_id=uuid4()), user_id=uuid4(), permissions=permissions, request_id="req-x")


async def test_executor_raises_not_found_for_unknown_tool() -> None:
    executor = ToolExecutor(ToolRegistry())

    with pytest.raises(ToolNotFoundError):
        await executor.execute("does_not_exist", _executor_context(), {})


async def test_executor_raises_authorization_error_when_permission_missing() -> None:
    registry = ToolRegistry()
    registry.register(_DummyTool())
    executor = ToolExecutor(registry)

    with pytest.raises(ToolAuthorizationError):
        await executor.execute("dummy_tool", _executor_context(permissions=frozenset({"ai:use"})), {})


async def test_executor_raises_validation_error_for_unknown_argument() -> None:
    class StrictArgs(ToolArguments):
        value: int

    class StrictTool(AITool):
        name = "strict_tool"
        description = "d"
        input_schema = StrictArgs
        required_permissions = ("ai:use",)

        async def run(self, context, arguments) -> ToolResult:
            return ToolResult(success=True, data={"value": arguments.value})

    registry = ToolRegistry()
    registry.register(StrictTool())
    executor = ToolExecutor(registry)

    with pytest.raises(ToolValidationError):
        await executor.execute("strict_tool", _executor_context(), {"value": 1, "unexpected": "x"})
    with pytest.raises(ToolValidationError):
        await executor.execute("strict_tool", _executor_context(), {"value": "not-an-int"})


async def test_executor_wraps_unexpected_exceptions_as_execution_error() -> None:
    class BrokenTool(AITool):
        name = "broken_tool"
        description = "d"
        required_permissions = ("ai:use",)

        async def run(self, context, arguments) -> ToolResult:
            raise RuntimeError("boom")

    registry = ToolRegistry()
    registry.register(BrokenTool())
    executor = ToolExecutor(registry)

    with pytest.raises(ToolExecutionError):
        await executor.execute("broken_tool", _executor_context(), {})


async def test_executor_raises_timeout_error() -> None:
    import asyncio

    class SlowTool(AITool):
        name = "slow_tool"
        description = "d"
        required_permissions = ("ai:use",)
        timeout_seconds = 0.01

        async def run(self, context, arguments) -> ToolResult:
            await asyncio.sleep(0.2)
            return ToolResult(success=True)

    registry = ToolRegistry()
    registry.register(SlowTool())
    executor = ToolExecutor(registry)

    with pytest.raises(ToolTimeoutError):
        await executor.execute("slow_tool", _executor_context(), {})


async def test_executor_propagates_tool_unavailable_error() -> None:
    class UnavailableTool(AITool):
        name = "unavailable_tool"
        description = "d"
        required_permissions = ("ai:use",)

        async def run(self, context, arguments) -> ToolResult:
            raise ToolUnavailableError("no data")

    registry = ToolRegistry()
    registry.register(UnavailableTool())
    executor = ToolExecutor(registry)

    with pytest.raises(ToolUnavailableError):
        await executor.execute("unavailable_tool", _executor_context(), {})


async def test_executor_truncates_oversized_results() -> None:
    class HugeTool(AITool):
        name = "huge_tool"
        description = "d"
        required_permissions = ("ai:use",)

        async def run(self, context, arguments) -> ToolResult:
            return ToolResult(success=True, data={"blob": "x" * (MAX_TOOL_RESULT_CHARS + 500)})

    registry = ToolRegistry()
    registry.register(HugeTool())
    executor = ToolExecutor(registry)

    result = await executor.execute("huge_tool", _executor_context(), {})

    assert result.metadata.get("truncated") is True
    assert "preview" in result.data


# ---------------------------------------------------------------------------
# 4. Business tools — real computation, no fabricated data
# ---------------------------------------------------------------------------


async def test_get_business_overview_uses_real_dataset(tenant_with_ready_dataset) -> None:
    session, _, _, _, _, ingestion, context = tenant_with_ready_dataset
    tool = GetBusinessOverviewTool(session=session, ingestion=ingestion)

    result = await tool.run(context, sales_tools.BusinessOverviewArgs())

    assert result.success is True
    assert result.data["orders"] == 6
    assert result.data["customers"] == 3
    assert result.source_refs


async def test_get_sales_summary_flags_unsupported_filters(tenant_with_ready_dataset) -> None:
    session, _, _, _, _, ingestion, context = tenant_with_ready_dataset
    tool = GetSalesSummaryTool(session=session, ingestion=ingestion)
    args = sales_tools.SalesSummaryArgs(location="Paris", category="Shoes")

    result = await tool.run(context, args)

    assert result.success is True
    assert sorted(result.metadata["unsupported_filters"]) == ["category", "location"]


async def test_get_sales_trend_returns_monthly_points(tenant_with_ready_dataset) -> None:
    session, _, _, _, _, ingestion, context = tenant_with_ready_dataset
    tool = GetSalesTrendTool(session=session, ingestion=ingestion)

    result = await tool.run(context, sales_tools.SalesTrendArgs())

    assert result.data["granularity"] == "month"
    assert len(result.data["points"]) >= 1


async def test_get_top_products_rejects_unsupported_metric(tenant_with_ready_dataset) -> None:
    session, _, _, _, _, ingestion, context = tenant_with_ready_dataset
    tool = GetTopProductsTool(session=session, ingestion=ingestion)

    result = await tool.run(context, sales_tools.TopProductsArgs(metric="profit"))

    assert result.success is False
    assert "profit" in result.error


async def test_get_top_products_ranks_by_revenue(tenant_with_ready_dataset) -> None:
    session, _, _, _, _, ingestion, context = tenant_with_ready_dataset
    tool = GetTopProductsTool(session=session, ingestion=ingestion)

    result = await tool.run(context, sales_tools.TopProductsArgs(top_n=1, metric="revenue"))

    assert len(result.data["products"]) == 1


async def test_get_customer_summary_counts_returning_customers(tenant_with_ready_dataset) -> None:
    session, _, _, _, _, ingestion, context = tenant_with_ready_dataset
    tool = GetCustomerSummaryTool(session=session, ingestion=ingestion)

    result = await tool.run(context, customer_tools.CustomerSummaryArgs())

    assert result.data["total_customers"] == 3
    assert result.data["returning_customers"] == 3  # 6 orders / 3 customers => each has 2


async def test_tool_raises_unavailable_when_no_ready_dataset_exists(db_session) -> None:
    company = Company(name="Empty Co", slug="empty-co", email="empty@example.com", country="CA", timezone="America/Toronto", industry="Retail", subscription_plan="demo")
    db_session.add(company); db_session.commit()
    tenant = TenantContext(company_id=company.id)
    context = ToolExecutionContext(tenant=tenant, user_id=uuid4(), permissions=frozenset({"ai:use"}), request_id="r")
    tool = GetBusinessOverviewTool(session=db_session, ingestion=EmptyIngestionService())

    with pytest.raises(ToolUnavailableError):
        await tool.run(context, sales_tools.BusinessOverviewArgs())


async def test_latest_ready_dataset_is_tenant_scoped(db_session) -> None:
    company_a = Company(name="A", slug="a", email="a2@example.com", country="CA", timezone="America/Toronto", industry="Retail", subscription_plan="demo")
    company_b = Company(name="B", slug="b", email="b2@example.com", country="CA", timezone="America/Toronto", industry="Retail", subscription_plan="demo")
    db_session.add_all([company_a, company_b]); db_session.flush()
    dataset_b = Dataset(company_id=company_b.id, name="B data", type="csv", source="b.csv", rows_count=1, columns_count=1, status=DatasetStatus.READY)
    db_session.add(dataset_b); db_session.commit()

    found = latest_ready_dataset(db_session, TenantContext(company_id=company_a.id))

    assert found is None


# ---------------------------------------------------------------------------
# 5. Inventory tool — prepared but permanently unavailable (no fake data)
# ---------------------------------------------------------------------------


async def test_inventory_tool_always_raises_unavailable() -> None:
    tool = GetInventorySummaryTool()
    context = ToolExecutionContext(tenant=TenantContext(company_id=uuid4()), user_id=uuid4(), permissions=frozenset({"ai:use"}), request_id="r")

    with pytest.raises(ToolUnavailableError):
        await tool.run(context, sales_tools.BusinessOverviewArgs() if False else GetInventorySummaryTool.input_schema())


def test_inventory_tool_requires_inventory_capability_never_available_by_default() -> None:
    registry = ToolRegistry()
    registry.register(GetInventorySummaryTool())

    available = registry.available_for(permissions=frozenset({"ai:use"}), plan_code="enterprise", capabilities=frozenset())

    assert available == ()


# ---------------------------------------------------------------------------
# 6. Customer segmentation tool — reuses trained model, never retrains
# ---------------------------------------------------------------------------


async def test_get_customer_segments_raises_unavailable_without_trained_model(db_session, monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise PortfolioAnalysisUnavailable("No segmentation model trained yet.")

    monkeypatch.setattr(customer_tools, "build_segmentation_signal", _raise)
    tool = GetCustomerSegmentsTool(session=db_session, prediction_service=object())
    context = ToolExecutionContext(tenant=TenantContext(company_id=uuid4()), user_id=uuid4(), permissions=frozenset({"ai:use"}), request_id="r")

    with pytest.raises(ToolUnavailableError):
        await tool.run(context, customer_tools.CustomerSegmentsArgs())


async def test_get_customer_segments_returns_real_signal_when_model_exists(db_session, monkeypatch) -> None:
    class FakeSignal:
        entity = "High-value repeat buyers"
        value = 0.42
        metric = "share_of_customers"

    monkeypatch.setattr(customer_tools, "build_segmentation_signal", lambda *a, **k: FakeSignal())
    tool = GetCustomerSegmentsTool(session=db_session, prediction_service=object())
    context = ToolExecutionContext(tenant=TenantContext(company_id=uuid4()), user_id=uuid4(), permissions=frozenset({"ai:use"}), request_id="r")

    result = await tool.run(context, customer_tools.CustomerSegmentsArgs())

    assert result.success is True
    assert result.data["dominant_segment"] == "High-value repeat buyers"


def test_resolve_tenant_capabilities_never_includes_inventory(db_session, monkeypatch) -> None:
    import backend.app.ai.tools.business.registry_factory as registry_factory

    monkeypatch.setattr(registry_factory, "resolve_active_model_type", lambda *a, **k: "segmentation")
    capabilities = resolve_tenant_capabilities(db_session, TenantContext(company_id=uuid4()), prediction_service=object())

    assert capabilities == frozenset({"segmentation", "churn", "demand_forecast", "sales_forecast", "anomaly_detection"})
    assert "inventory" not in capabilities


def test_build_business_tool_registry_registers_all_fourteen_tools(db_session) -> None:
    registry = build_business_tool_registry(db_session, EmptyIngestionService(), prediction_service=object())

    names = {tool.name for tool in registry.list_tools()}
    assert names == {
        "get_business_overview", "get_sales_summary", "get_sales_trend", "get_sales_comparison",
        "get_top_products", "get_customer_summary", "get_customer_segments", "get_inventory_summary",
        "get_churn_risk", "get_segment_insights", "get_demand_forecast", "get_sales_forecast",
        "get_anomalies", "get_prediction_summary",
    }


# ---------------------------------------------------------------------------
# 7. ToolOrchestrator — bounded tool calling loop
# ---------------------------------------------------------------------------


async def test_orchestrator_falls_back_to_plain_generate_when_no_tools_available() -> None:
    provider = FakeLLMProvider(plain_content="hello")
    executor = ToolExecutor(ToolRegistry())
    orchestrator = ToolOrchestrator(provider, executor)
    context = _executor_context()

    result = await orchestrator.run(system_instruction="sys", user_query="hi", context=context, available_tools=())

    assert result.content == "hello"
    assert provider.generate_calls == 1
    assert provider.generate_with_tools_calls == 0


async def test_orchestrator_falls_back_when_provider_does_not_support_tool_calling() -> None:
    provider = UnsupportedLLMProvider()
    registry = ToolRegistry()
    registry.register(_DummyTool())
    executor = ToolExecutor(registry)
    orchestrator = ToolOrchestrator(provider, executor)
    context = _executor_context(permissions=frozenset({"ai:use", "data:read"}))

    result = await orchestrator.run(
        system_instruction="sys", user_query="hi", context=context,
        available_tools=(_DummyTool(),),
    )

    assert result.content == "fallback answer"


async def test_orchestrator_executes_a_tool_call_and_returns_final_answer(tenant_with_ready_dataset) -> None:
    session, _, _, _, tenant, ingestion, context = tenant_with_ready_dataset
    registry = ToolRegistry()
    registry.register(GetBusinessOverviewTool(session=session, ingestion=ingestion))
    executor = ToolExecutor(registry)
    call = ToolCall(id="call-1", name="get_business_overview", arguments={})
    responses = [
        LLMToolResponse(content=None, tool_calls=(call,), provider="fake", model="fake-model"),
        LLMToolResponse(content="Your revenue is strong.", tool_calls=(), provider="fake", model="fake-model"),
    ]
    provider = FakeLLMProvider(tool_responses=responses)
    orchestrator = ToolOrchestrator(provider, executor)

    result = await orchestrator.run(
        system_instruction="sys", user_query="How is my business doing?", context=context,
        available_tools=tuple(registry.list_tools()),
    )

    assert result.content == "Your revenue is strong."
    assert len(result.tool_call_results) == 1
    assert result.tool_call_results[0].result.success is True
    assert result.status_events == ("Analyzing your business data...",)


async def test_orchestrator_stops_at_max_iterations_without_infinite_loop() -> None:
    registry = ToolRegistry()
    registry.register(_DummyTool())
    executor = ToolExecutor(registry)
    call = ToolCall(id="call-x", name="dummy_tool", arguments={})
    always_more_tools = [
        LLMToolResponse(content=None, tool_calls=(call,), provider="fake", model="fake-model")
        for _ in range(MAX_TOOL_ITERATIONS + 2)
    ]
    provider = FakeLLMProvider(tool_responses=always_more_tools)
    orchestrator = ToolOrchestrator(provider, executor)
    context = _executor_context(permissions=frozenset({"ai:use", "data:read"}))

    result = await orchestrator.run(
        system_instruction="sys", user_query="loop please", context=context,
        available_tools=(_DummyTool(),),
    )

    assert provider.generate_with_tools_calls == MAX_TOOL_ITERATIONS
    assert "allowed number of steps" in result.content


async def test_orchestrator_records_failed_tool_call_without_crashing() -> None:
    class FailingArgs(ToolArguments):
        pass

    class FailingTool(AITool):
        name = "failing_tool"
        description = "d"
        required_permissions = ("ai:use",)
        input_schema = FailingArgs

        async def run(self, context, arguments) -> ToolResult:
            raise ToolUnavailableError("no data connected")

    registry = ToolRegistry()
    registry.register(FailingTool())
    executor = ToolExecutor(registry)
    call = ToolCall(id="call-1", name="failing_tool", arguments={})
    responses = [
        LLMToolResponse(content=None, tool_calls=(call,), provider="fake", model="fake-model"),
        LLMToolResponse(content="I don't have that data yet.", tool_calls=(), provider="fake", model="fake-model"),
    ]
    provider = FakeLLMProvider(tool_responses=responses)
    orchestrator = ToolOrchestrator(provider, executor)
    context = _executor_context()

    result = await orchestrator.run(
        system_instruction="sys", user_query="q", context=context, available_tools=(FailingTool(),)
    )

    assert result.content == "I don't have that data yet."
    assert result.tool_call_results[0].result.success is False


# ---------------------------------------------------------------------------
# 8. ChatService integration — backward compatibility + real tool wiring
# ---------------------------------------------------------------------------


async def test_chat_service_send_without_permissions_never_calls_tools(tenant_with_ready_dataset) -> None:
    session, company, user, dataset, tenant, ingestion, _ = tenant_with_ready_dataset
    conversations = ConversationService(session)
    retrieval = RetrievalService(session)
    provider = FakeLLMProvider(plain_content="plain reply")
    registry = build_business_tool_registry(session, ingestion, prediction_service=object())
    executor = ToolExecutor(registry)
    service = ChatService(conversations, retrieval, provider, tool_registry=registry, tool_executor=executor)
    conversation = conversations.create(company.id, user.id, "Chat")

    message, sources = await service.send(company.id, user.id, conversation.id, "How is business?")

    assert message.content == "plain reply"
    assert provider.generate_with_tools_calls == 0


async def test_chat_service_send_with_permissions_uses_tools_and_persists_source(tenant_with_ready_dataset) -> None:
    session, company, user, dataset, tenant, ingestion, _ = tenant_with_ready_dataset
    conversations = ConversationService(session)
    retrieval = RetrievalService(session)
    call = ToolCall(id="c1", name="get_business_overview", arguments={})
    responses = [
        LLMToolResponse(content=None, tool_calls=(call,), provider="fake", model="fake-model"),
        LLMToolResponse(content="Revenue is $210.", tool_calls=(), provider="fake", model="fake-model"),
    ]
    provider = FakeLLMProvider(tool_responses=responses)
    registry = build_business_tool_registry(session, ingestion, prediction_service=object())
    executor = ToolExecutor(registry)
    service = ChatService(conversations, retrieval, provider, tool_registry=registry, tool_executor=executor)
    conversation = conversations.create(company.id, user.id, "Chat")

    message, sources = await service.send(
        company.id, user.id, conversation.id, "How is business?",
        permissions=frozenset(permissions_for(UserRole.ANALYST)), plan_code="demo", request_id="r1",
    )

    assert message.content == "Revenue is $210."
    assert any(source.metadata.get("tool") == "get_business_overview" for source in sources)


async def test_chat_service_backward_compatible_without_tool_wiring(tenant_with_ready_dataset) -> None:
    session, company, user, dataset, tenant, ingestion, _ = tenant_with_ready_dataset
    conversations = ConversationService(session)
    retrieval = RetrievalService(session)
    provider = FakeLLMProvider(plain_content="old behavior")
    service = ChatService(conversations, retrieval, provider)
    conversation = conversations.create(company.id, user.id, "Chat")

    message, _ = await service.send(company.id, user.id, conversation.id, "hi")

    assert message.content == "old behavior"


def test_settings_expose_tool_calling_bounds() -> None:
    from backend.app.config.settings import Settings

    settings = Settings()

    assert settings.ai_max_tool_iterations >= 1
    assert settings.ai_max_tools_per_request >= 1
    assert settings.ai_max_tool_result_chars >= 500
