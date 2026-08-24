"""Phase 31 — Avenqo Predictive Intelligence (outils prédictifs).

Couvre : `PredictiveAITool` (conversion `PortfolioAnalysisUnavailable` ->
`PredictionUnavailableError`, jamais de donnée inventée), les six outils
prédictifs (`get_churn_risk`, `get_segment_insights`, `get_demand_forecast`,
`get_sales_forecast`, `get_anomalies`, `get_prediction_summary`), l'absence
totale de surface `model_id`/tenant exploitable par le LLM (isolation
tenant garantie par `ToolExecutionContext.tenant`, jamais par un argument),
le comportement "aucun modèle" (jamais de prédiction inventée), et
l'intégration SSE bout-en-bout (statuts génériques, annulation, aucune
donnée d'un autre tenant) en réutilisant EXACTEMENT le pipeline Phase 30.1.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.ai.chat.chat_service import ChatService
from backend.app.ai.chat.conversation_service import ConversationService
from backend.app.ai.chat.retrieval_service import RetrievalService
from backend.app.ai.llm.base import LLMProvider
from backend.app.ai.llm.schemas import LLMGeneration, LLMToolResponse
from backend.app.ai.tools.business import predictive_tools
from backend.app.ai.tools.business.predictive_tools import (
    AnomaliesArgs,
    ChurnRiskArgs,
    DemandForecastArgs,
    GetAnomaliesTool,
    GetChurnRiskTool,
    GetDemandForecastTool,
    GetPredictionSummaryTool,
    GetSalesForecastTool,
    GetSegmentInsightsTool,
    PredictionSummaryArgs,
    SalesForecastArgs,
    SegmentInsightsArgs,
)
from backend.app.ai.tools.business.registry_factory import build_business_tool_registry
from backend.app.ai.tools.contracts import ToolCall, ToolExecutionContext
from backend.app.ai.tools.exceptions import PredictionUnavailableError
from backend.app.ai.tools.executor import ToolExecutor
from backend.app.core.permissions import permissions_for
from backend.app.models import Base, Company, User, UserRole
from backend.app.services.portfolio_decision_service import PortfolioAnalysisUnavailable
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.decision_intelligence.contracts import BusinessSignal, SignalDirection

pytestmark = pytest.mark.asyncio


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'phase31_predictive.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


def _company(session, slug: str = "acme") -> Company:
    company = Company(
        name="Acme", slug=slug, email=f"{slug}@example.com", country="CA",
        timezone="America/Toronto", industry="Retail", subscription_plan="demo",
    )
    session.add(company)
    session.flush()
    return company


def _user(session, company: Company) -> User:
    user = User(
        company_id=company.id, first_name="Ana", last_name="Lyst",
        email=f"analyst-{company.slug}@example.com", password_hash="hash", role=UserRole.ANALYST,
    )
    session.add(user)
    session.flush()
    return user


def _context(company_id) -> ToolExecutionContext:
    return ToolExecutionContext(
        tenant=TenantContext(company_id=company_id), user_id=uuid4(),
        permissions=frozenset({"ai:use"}), request_id="r1",
    )


def _fake_signal(**overrides) -> BusinessSignal:
    defaults = dict(
        company_id=uuid4(), module_code="retail", task_code="churn", capability="classification",
        entity="3 clients a risque de depart", metric="at_risk_customers_count", value=3.0,
        direction=SignalDirection.RISK, confidence=0.7, metadata={},
    )
    defaults.update(overrides)
    return BusinessSignal(**defaults)


# ---------------------------------------------------------------------------
# 1. No argument surface for cross-tenant model selection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("args_cls", [ChurnRiskArgs, SegmentInsightsArgs, DemandForecastArgs, AnomaliesArgs, PredictionSummaryArgs])
def test_predictive_tool_args_reject_model_id_and_unknown_fields(args_cls) -> None:
    with pytest.raises(Exception):
        args_cls.model_validate({"model_id": "some-other-tenant-model"})


def test_sales_forecast_args_only_expose_horizon() -> None:
    assert set(SalesForecastArgs.model_fields.keys()) == {"horizon"}
    with pytest.raises(Exception):
        SalesForecastArgs.model_validate({"horizon": 2, "model_id": "other-tenant"})


# ---------------------------------------------------------------------------
# 2. Happy paths (tool layer, wrapping already-trained models)
# ---------------------------------------------------------------------------


async def test_get_churn_risk_happy_path(monkeypatch, db_session) -> None:
    company = _company(db_session)
    churn_signal = _fake_signal(value=5.0)
    monkeypatch.setattr(
        predictive_tools, "build_churn_segmentation_signals",
        lambda *a, **k: (churn_signal, _fake_signal(task_code="segmentation")),
    )
    tool = GetChurnRiskTool(session=db_session, prediction_service=object())

    result = await tool.run(_context(company.id), ChurnRiskArgs())

    assert result.success is True
    assert result.data["at_risk_customers_count"] == 5.0
    assert result.metadata["task_code"] == "churn"


async def test_get_segment_insights_happy_path(monkeypatch, db_session) -> None:
    company = _company(db_session)
    signal = _fake_signal(task_code="segmentation", entity="High-value repeat buyers", value=0.42, metric="share_of_customers")
    monkeypatch.setattr(predictive_tools, "build_segmentation_signal", lambda *a, **k: signal)
    tool = GetSegmentInsightsTool(session=db_session, prediction_service=object())

    result = await tool.run(_context(company.id), SegmentInsightsArgs())

    assert result.success is True
    assert result.data["dominant_segment"] == "High-value repeat buyers"
    assert result.data["segment_share"] == 0.42


async def test_get_demand_forecast_happy_path(monkeypatch, db_session) -> None:
    company = _company(db_session)
    signal = _fake_signal(task_code="demand", entity="120 produits", value=42.0, direction=SignalDirection.OPPORTUNITY)
    monkeypatch.setattr(predictive_tools, "build_demand_signal", lambda *a, **k: signal)
    tool = GetDemandForecastTool(session=db_session, prediction_service=object())

    result = await tool.run(_context(company.id), DemandForecastArgs())

    assert result.success is True
    assert result.data["demand_trend_value"] == 42.0
    assert result.data["direction"] == "opportunity"


async def test_get_sales_forecast_happy_path_with_horizon(monkeypatch, db_session) -> None:
    company = _company(db_session)
    captured_horizon: list[int | None] = []

    def _fake_builder(session, tenant, module_code, prediction_service, horizon=None):
        captured_horizon.append(horizon)
        return _fake_signal(
            task_code="weekly_forecast", value=300.0,
            metadata={"forecast_points": (100.0, 100.0, 100.0), "horizon": horizon or 2},
        )

    monkeypatch.setattr(predictive_tools, "build_sales_forecast_signal", _fake_builder)
    tool = GetSalesForecastTool(session=db_session, prediction_service=object())

    result = await tool.run(_context(company.id), SalesForecastArgs(horizon=3))

    assert result.success is True
    assert result.data["forecasted_total"] == 300.0
    assert result.data["horizon"] == 3
    assert captured_horizon == [3]


async def test_get_anomalies_happy_path(monkeypatch, db_session) -> None:
    company = _company(db_session)
    signal = _fake_signal(
        task_code="anomaly", value=4.0, direction=SignalDirection.RISK,
        metadata={"anomalous_record_ids": ("order-1", "order-2"), "total_records_scanned": 50},
    )
    monkeypatch.setattr(predictive_tools, "build_anomaly_signal", lambda *a, **k: signal)
    tool = GetAnomaliesTool(session=db_session, prediction_service=object())

    result = await tool.run(_context(company.id), AnomaliesArgs())

    assert result.success is True
    assert result.data["anomalies_count"] == 4.0
    assert result.data["total_records_scanned"] == 50


# ---------------------------------------------------------------------------
# 3. No model available -> controlled unavailable, never a fake prediction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_cls,args_cls,builder_name",
    [
        (GetChurnRiskTool, ChurnRiskArgs, "build_churn_segmentation_signals"),
        (GetSegmentInsightsTool, SegmentInsightsArgs, "build_segmentation_signal"),
        (GetDemandForecastTool, DemandForecastArgs, "build_demand_signal"),
        (GetSalesForecastTool, SalesForecastArgs, "build_sales_forecast_signal"),
        (GetAnomaliesTool, AnomaliesArgs, "build_anomaly_signal"),
    ],
)
async def test_predictive_tool_raises_controlled_error_when_no_model_exists(monkeypatch, db_session, tool_cls, args_cls, builder_name) -> None:
    company = _company(db_session)

    def _raise(*args, **kwargs):
        raise PortfolioAnalysisUnavailable("No active model for this company.")

    monkeypatch.setattr(predictive_tools, builder_name, _raise)
    tool = tool_cls(session=db_session, prediction_service=object())

    with pytest.raises(PredictionUnavailableError):
        await tool.run(_context(company.id), args_cls())


async def test_get_churn_risk_real_no_model_tenant_without_monkeypatch(db_session) -> None:
    """Sans aucune ligne `ModelRegistry` active, le vrai chemin DB doit refuser proprement."""

    company = _company(db_session)
    tool = GetChurnRiskTool(session=db_session, prediction_service=object())

    with pytest.raises(PredictionUnavailableError):
        await tool.run(_context(company.id), ChurnRiskArgs())


# ---------------------------------------------------------------------------
# 4. get_prediction_summary — read-only, never runs inference
# ---------------------------------------------------------------------------


async def test_prediction_summary_lists_availability_per_task(monkeypatch, db_session) -> None:
    company = _company(db_session)

    def _fake_resolve(session, tenant, module_code, task_code):
        return "classification" if task_code in ("churn", "segmentation") else None

    monkeypatch.setattr(predictive_tools, "resolve_active_model_type", _fake_resolve)
    tool = GetPredictionSummaryTool(session=db_session)

    result = await tool.run(_context(company.id), PredictionSummaryArgs())

    assert result.success is True
    available = result.data["available_predictions"]
    assert available["churn_risk"] is True
    assert available["segment_insights"] is True
    assert available["demand_forecast"] is False
    assert available["sales_forecast"] is False
    assert available["anomalies"] is False


# ---------------------------------------------------------------------------
# 5. SSE integration — reuses Phase 30.1 exactly
# ---------------------------------------------------------------------------


class ScriptedPredictiveProvider(LLMProvider):
    name = "fake-predictive"
    supports_tool_calling = True

    def __init__(self, tool_name: str, final_content: str) -> None:
        self._tool_name, self._final_content, self._call_count = tool_name, final_content, 0

    async def generate(self, *, system_instruction: str, prompt: str) -> LLMGeneration:
        return LLMGeneration(content=self._final_content, provider=self.name, model="fake-model")

    async def stream(self, *, system_instruction: str, prompt: str):
        yield self._final_content

    async def generate_with_tools(self, *, system_instruction, messages, tools) -> LLMToolResponse:
        self._call_count += 1
        if self._call_count == 1:
            call = ToolCall(id="call-1", name=self._tool_name, arguments={})
            return LLMToolResponse(content=None, tool_calls=(call,), provider=self.name, model="fake-model")
        return LLMToolResponse(content=self._final_content, tool_calls=(), provider=self.name, model="fake-model")


class _EmptyIngestion:
    def get_prepared_dataset(self, tenant, dataset_id):  # pragma: no cover - not used by predictive tools
        raise AssertionError("predictive tools must not need dataset ingestion directly")


async def test_sse_predictive_tool_calling_end_to_end(db_session, monkeypatch) -> None:
    company = _company(db_session)
    user = _user(db_session, company)
    churn_signal = _fake_signal(value=7.0)
    monkeypatch.setattr(
        predictive_tools, "build_churn_segmentation_signals",
        lambda *a, **k: (churn_signal, _fake_signal(task_code="segmentation")),
    )

    conversations = ConversationService(db_session)
    retrieval = RetrievalService(db_session)
    provider = ScriptedPredictiveProvider("get_churn_risk", "7 customers are at risk of churn.")
    registry = build_business_tool_registry(db_session, _EmptyIngestion(), prediction_service=object())
    executor = ToolExecutor(registry)
    service = ChatService(conversations, retrieval, provider, tool_registry=registry, tool_executor=executor)
    conversation = conversations.create(company.id, user.id, "Chat")
    permissions = frozenset(permissions_for(UserRole.ANALYST))

    events = [event async for event in service.stream(
        company.id, user.id, conversation.id, "Which customers are at risk of leaving?",
        permissions=permissions, plan_code="demo", capabilities=frozenset({"churn"}), request_id="req-pred-1",
    )]

    kinds = [event.kind for event in events]
    assert kinds[-2:] == ["sources", "done"]
    full_text = "".join(event.payload["chunk"] for event in events if event.kind == "delta")
    assert full_text == "7 customers are at risk of churn."

    status_payloads = [event.payload for event in events if event.kind == "status"]
    for payload in status_payloads:
        assert "get_churn_risk" not in str(payload)
        assert str(company.id) not in str(payload)

    sources_event = next(event for event in events if event.kind == "sources")
    assert any(source["metadata"].get("tool") == "get_churn_risk" for source in sources_event.payload["sources"]) or sources_event.payload["sources"] == []


async def test_sse_predictive_cancellation_does_not_persist(db_session, monkeypatch) -> None:
    company = _company(db_session)
    user = _user(db_session, company)
    monkeypatch.setattr(
        predictive_tools, "build_churn_segmentation_signals",
        lambda *a, **k: (_fake_signal(value=2.0), _fake_signal(task_code="segmentation")),
    )

    conversations = ConversationService(db_session)
    retrieval = RetrievalService(db_session)
    provider = ScriptedPredictiveProvider("get_churn_risk", "2 customers are at risk of churn.")
    registry = build_business_tool_registry(db_session, _EmptyIngestion(), prediction_service=object())
    executor = ToolExecutor(registry)
    service = ChatService(conversations, retrieval, provider, tool_registry=registry, tool_executor=executor)
    conversation = conversations.create(company.id, user.id, "Chat")
    permissions = frozenset(permissions_for(UserRole.ANALYST))

    seen_status = False

    async def is_cancelled() -> bool:
        nonlocal seen_status
        return seen_status

    collected = []
    async for event in service.stream(
        company.id, user.id, conversation.id, "Which customers are at risk of leaving?",
        permissions=permissions, plan_code="demo", capabilities=frozenset({"churn"}), request_id="req-pred-2",
        is_cancelled=is_cancelled,
    ):
        collected.append(event)
        if event.kind == "status":
            seen_status = True

    assert not any(event.kind in ("sources", "done") for event in collected)
    messages = conversations.messages(company.id, conversation.id)
    assert all(message.role.value == "user" for message in messages)
