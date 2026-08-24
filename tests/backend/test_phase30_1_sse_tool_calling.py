"""Phase 30.1 — Tool Calling en flux SSE (`ChatService.stream`).

Réutilise EXACTEMENT les composants Phase 30 (`ToolOrchestrator`,
`ToolRegistry`, `ToolExecutor`, `ToolExecutionContext`, outils métier) :
aucune deuxième implémentation de tool calling. Ces tests couvrent le
comportement propre au streaming : événements SSE sûrs (status/delta/
sources/done), isolation multi-tenant à travers un outil exécuté en
streaming, et annulation client sans persistance de réponse incomplète.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
from backend.app.ai.tools.business.registry_factory import build_business_tool_registry
from backend.app.ai.tools.contracts import ToolCall
from backend.app.ai.tools.executor import ToolExecutor
from backend.app.core.permissions import permissions_for
from backend.app.models import Base, Company, Dataset, DatasetStatus, User, UserRole
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_ingestion.cleaning import CompanyDatasetCleaner
from shared.ai_engine.dataset_ingestion.prepared_dataset import PreparedCompanyDataset
from shared.ai_engine.dataset_ingestion.profiling import DatasetProfiler
from shared.ai_engine.dataset_ingestion.quality import assess_quality
from shared.ai_engine.dataset_ingestion.readiness import assess_capability_readiness

pytestmark = pytest.mark.asyncio


CANONICAL_COLUMNS = {
    "customer_id": "customer_id",
    "order_id": "order_id",
    "product_id": "product_id",
    "order_timestamp": "order_timestamp",
    "quantity": "quantity",
    "total_amount": "total_amount",
}


def _rows(seed: int, count: int = 6) -> list[dict[str, object]]:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        {
            "customer_id": f"cust-{seed}-{i % 3}",
            "order_id": f"order-{seed}-{i}",
            "product_id": f"prod-{seed}-{i % 2}",
            "order_timestamp": (base + timedelta(days=i)).isoformat(),
            "quantity": i + 1,
            "total_amount": (100.0 * seed) + 10.0 * (i + 1),
        }
        for i in range(count)
    ]


def _prepared_dataset(seed: int, company_id, dataset_id) -> PreparedCompanyDataset:
    rows = _rows(seed)
    cleaner = CompanyDatasetCleaner()
    cleaned_rows, cleaning_report = cleaner.clean(rows, CANONICAL_COLUMNS)
    profile = DatasetProfiler().profile(cleaned_rows, tuple(CANONICAL_COLUMNS))
    quality = assess_quality(cleaning_report)
    readiness = assess_capability_readiness(set(CANONICAL_COLUMNS.values()))
    return PreparedCompanyDataset(
        company_id=company_id,
        dataset_id=dataset_id,
        version=1,
        canonical_columns=CANONICAL_COLUMNS,
        rows=tuple(cleaned_rows),
        profile=profile,
        mapping=(),
        cleaning_report=cleaning_report,
        quality=quality,
        capability_readiness=readiness,
    )


class MultiTenantIngestionService:
    """Route chaque appel vers le dataset préparé du tenant demandé (jamais un autre)."""

    def __init__(self) -> None:
        self._prepared: dict = {}

    def register(self, company_id, prepared: PreparedCompanyDataset) -> None:
        self._prepared[company_id] = prepared

    def get_prepared_dataset(self, tenant: TenantContext, dataset_id) -> PreparedCompanyDataset:
        prepared = self._prepared.get(tenant.company_id)
        assert prepared is not None, "cross-tenant leak: dataset requested for unregistered tenant"
        return prepared


class ScriptedToolCallingProvider(LLMProvider):
    """Simule un LLM qui décide d'appeler `get_sales_summary` puis conclut."""

    name = "fake-stream"
    supports_tool_calling = True

    def __init__(self, tool_name: str, final_content: str) -> None:
        self._tool_name = tool_name
        self._final_content = final_content
        self._call_count = 0

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


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'phase30_1.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


def _make_tenant(db_session, seed: int):
    company = Company(
        name=f"Company {seed}", slug=f"company-{seed}", email=f"c{seed}@example.com", country="CA",
        timezone="America/Toronto", industry="Retail", subscription_plan="demo",
    )
    db_session.add(company); db_session.flush()
    user = User(company_id=company.id, first_name="Ana", last_name="Lyst", email=f"analyst{seed}@example.com", password_hash="hash", role=UserRole.ANALYST)
    db_session.add(user); db_session.flush()
    dataset = Dataset(company_id=company.id, name="Sales", type="csv", source="sales.csv", rows_count=6, columns_count=6, status=DatasetStatus.READY)
    db_session.add(dataset); db_session.commit()
    return company, user, dataset


async def _drain(stream):
    return [event async for event in stream]


async def test_sse_happy_path_emits_status_delta_sources_done_and_persists_once(db_session) -> None:
    company, user, dataset = _make_tenant(db_session, 1)
    ingestion = MultiTenantIngestionService()
    ingestion.register(company.id, _prepared_dataset(1, company.id, dataset.id))

    conversations = ConversationService(db_session)
    retrieval = RetrievalService(db_session)
    provider = ScriptedToolCallingProvider("get_sales_summary", "Sales were strong this month.")
    registry = build_business_tool_registry(db_session, ingestion, prediction_service=object())
    executor = ToolExecutor(registry)
    service = ChatService(conversations, retrieval, provider, tool_registry=registry, tool_executor=executor)
    conversation = conversations.create(company.id, user.id, "Chat")
    permissions = frozenset(permissions_for(UserRole.ANALYST))

    events = await _drain(service.stream(
        company.id, user.id, conversation.id, "How were my sales this month?",
        permissions=permissions, plan_code="demo", request_id="req-sse-1",
    ))

    kinds = [event.kind for event in events]
    assert kinds.count("status") == 1
    assert kinds.count("delta") >= 1
    assert kinds[-2:] == ["sources", "done"]

    status_payloads = [event.payload for event in events if event.kind == "status"]
    for payload in status_payloads:
        assert "get_sales_summary" not in str(payload)
        assert str(company.id) not in str(payload)

    full_text = "".join(event.payload["chunk"] for event in events if event.kind == "delta")
    assert full_text == "Sales were strong this month."

    sources_event = next(event for event in events if event.kind == "sources")
    assert any(source["metadata"].get("tool") == "get_sales_summary" for source in sources_event.payload["sources"])

    messages = conversations.messages(company.id, conversation.id)
    assistant_messages = [message for message in messages if message.role.value == "assistant"]
    assert len(assistant_messages) == 1
    assert assistant_messages[0].content == "Sales were strong this month."


async def test_sse_cross_tenant_isolation_never_leaks_other_tenant_data(db_session) -> None:
    company_a, user_a, dataset_a = _make_tenant(db_session, 1)
    company_b, _user_b, dataset_b = _make_tenant(db_session, 2)
    ingestion = MultiTenantIngestionService()
    ingestion.register(company_a.id, _prepared_dataset(1, company_a.id, dataset_a.id))
    ingestion.register(company_b.id, _prepared_dataset(2, company_b.id, dataset_b.id))

    conversations = ConversationService(db_session)
    retrieval = RetrievalService(db_session)
    provider = ScriptedToolCallingProvider("get_sales_summary", "Tenant A summary.")
    registry = build_business_tool_registry(db_session, ingestion, prediction_service=object())
    executor = ToolExecutor(registry)
    service = ChatService(conversations, retrieval, provider, tool_registry=registry, tool_executor=executor)
    conversation = conversations.create(company_a.id, user_a.id, "Chat")
    permissions = frozenset(permissions_for(UserRole.ANALYST))

    events = await _drain(service.stream(
        company_a.id, user_a.id, conversation.id, "How were my sales this month?",
        permissions=permissions, plan_code="demo", request_id="req-sse-2",
    ))

    sources_event = next(event for event in events if event.kind == "sources")
    for source in sources_event.payload["sources"]:
        assert str(company_b.id) not in str(source)
    full_text = "".join(event.payload["chunk"] for event in events if event.kind == "delta")
    assert str(company_b.id) not in full_text


async def test_sse_cancellation_stops_and_does_not_persist(db_session) -> None:
    company, user, dataset = _make_tenant(db_session, 1)
    ingestion = MultiTenantIngestionService()
    ingestion.register(company.id, _prepared_dataset(1, company.id, dataset.id))

    conversations = ConversationService(db_session)
    retrieval = RetrievalService(db_session)
    provider = ScriptedToolCallingProvider("get_sales_summary", "Sales were strong this month.")
    registry = build_business_tool_registry(db_session, ingestion, prediction_service=object())
    executor = ToolExecutor(registry)
    service = ChatService(conversations, retrieval, provider, tool_registry=registry, tool_executor=executor)
    conversation = conversations.create(company.id, user.id, "Chat")
    permissions = frozenset(permissions_for(UserRole.ANALYST))

    seen_status = False

    async def is_cancelled() -> bool:
        nonlocal seen_status
        return seen_status

    async def collect():
        nonlocal seen_status
        collected = []
        async for event in service.stream(
            company.id, user.id, conversation.id, "How were my sales this month?",
            permissions=permissions, plan_code="demo", request_id="req-sse-3",
            is_cancelled=is_cancelled,
        ):
            collected.append(event)
            if event.kind == "status":
                seen_status = True
        return collected

    events = await collect()

    assert not any(event.kind in ("sources", "done") for event in events)
    messages = conversations.messages(company.id, conversation.id)
    assistant_messages = [message for message in messages if message.role.value == "assistant"]
    assert assistant_messages == []
