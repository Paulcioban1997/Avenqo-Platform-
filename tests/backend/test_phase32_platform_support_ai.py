"""Phase 32 — Avenqo Platform Support AI.

Couvre : isolation stricte des données métier (tables séparées, RAG
scopé à la documentation produit uniquement), les outils sûrs en lecture
seule (plan, capacités, connexion, statut IA générique), et le registre
d'outils Support qui ne contient jamais d'outil métier/prédictif.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.ai.support.conversation_service import SupportConversationService
from backend.app.ai.support.error_codes import explain_error_code
from backend.app.ai.support.retrieval_service import PlatformKnowledgeRetrievalService
from backend.app.ai.chat.exceptions import ConversationNotFoundError
from backend.app.ai.llm.health import ProviderHealthRegistry
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.ai.tools.support.registry_factory import build_support_tool_registry
from backend.app.models import Base, Company, Dataset, User
from shared.ai_engine.contracts import TenantContext


KNOWLEDGE_ROOT = "platform_knowledge"


@pytest.fixture
def support_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'support.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        company = Company(name="Company A", slug="company-a", email="a@example.com", country="CA", timezone="America/Toronto", industry="Retail", subscription_plan="professional")
        session.add(company); session.flush()
        user = User(company_id=company.id, first_name="User", last_name="A", email="user-a@example.com", password_hash="hash")
        session.add(user)
        session.add(Dataset(company_id=company.id, name="Secret Sales", type="csv", source="secret.csv", rows_count=10, columns_count=2))
        session.commit()
        yield session, company, user


def test_support_conversations_are_isolated_from_business_conversations(support_session) -> None:
    session, company, user = support_session
    service = SupportConversationService(session)
    conversation = service.create(company.id, user.id, "How do I import a CSV?")

    fetched = service.get(company.id, user.id, conversation.id)
    assert fetched.id == conversation.id

    other_company_id = company.id  # sanity: wrong user id must fail lookup
    with pytest.raises(ConversationNotFoundError):
        service.get(company.id, user.id.__class__(int=user.id.int ^ 1), conversation.id)


def test_platform_knowledge_retrieval_never_touches_tenant_data() -> None:
    retrieval = PlatformKnowledgeRetrievalService(KNOWLEDGE_ROOT)

    sources = retrieval.retrieve_context("How do I import a csv file?")

    assert sources, "expected at least one matching platform document"
    assert all(source.source_type == "platform_doc" for source in sources)
    assert any("import" in source.name.lower() for source in sources)
    # Aucune méthode de cette classe n'accepte tenant_id/company_id : par
    # construction, elle ne peut interroger aucune table métier.
    assert not hasattr(retrieval, "tenant_id")


def test_support_tool_registry_never_contains_business_tools(support_session) -> None:
    session, company, _ = support_session

    class _FakePredictionService:
        pass

    from backend.app.ai.usage.policy import AIQuotaPolicy
    from backend.app.ai.usage.service import AIUsageService
    from backend.app.config.settings import Settings

    support_registry = build_support_tool_registry(
        session,
        prediction_service=_FakePredictionService(),
        knowledge_root=KNOWLEDGE_ROOT,
        health_registry=ProviderHealthRegistry(),
        usage_service=AIUsageService(session, AIQuotaPolicy(Settings(AUTH_JWT_SECRET="a" * 32))),
    )
    support_tool_names = {tool.name for tool in support_registry.list_tools()}

    assert support_tool_names == {
        "search_avenqo_docs",
        "get_current_plan",
        "get_available_features",
        "get_connection_status",
        "get_ai_capability_status",
        "get_billing_status",
    }
    business_tool_names = {"get_churn_risk", "get_sales_summary", "get_demand_forecast"}
    assert support_tool_names.isdisjoint(business_tool_names)


@pytest.mark.asyncio
async def test_get_current_plan_tool_returns_only_own_company_plan(support_session) -> None:
    session, company, user = support_session
    from backend.app.ai.tools.support.support_tools import GetCurrentPlanTool
    from backend.app.ai.tools.base import ToolArguments

    tool = GetCurrentPlanTool(session)
    context = ToolExecutionContext(tenant=TenantContext(company_id=company.id), user_id=user.id, permissions=frozenset({"ai:use"}), request_id="req-1")

    result = await tool.run(context, ToolArguments())

    assert result.success is True
    assert result.data["plan_code"] == "professional"


@pytest.mark.asyncio
async def test_get_connection_status_tool_never_leaks_dataset_content(support_session) -> None:
    session, company, user = support_session
    from backend.app.ai.tools.support.support_tools import GetConnectionStatusTool
    from backend.app.ai.tools.base import ToolArguments

    tool = GetConnectionStatusTool(session)
    context = ToolExecutionContext(tenant=TenantContext(company_id=company.id), user_id=user.id, permissions=frozenset({"ai:use"}), request_id="req-1")

    result = await tool.run(context, ToolArguments())

    assert result.data == {"has_connected_data_source": True}
    assert "Secret Sales" not in str(result.data)


def test_explain_error_code_returns_plain_language_message() -> None:
    assert "couldn't import" in explain_error_code("data_import_failed").lower()
    assert explain_error_code("unknown_code") is None
