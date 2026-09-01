from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.ai.central.routing import CentralAIIntentRouter
from backend.app.ai.central.service import CentralAIService
from backend.app.ai.chat.chat_service import ChatService
from backend.app.ai.chat.conversation_service import ConversationService
from backend.app.ai.chat.exceptions import AIServiceUnavailableError, ConversationNotFoundError
from backend.app.ai.chat.retrieval_service import RetrievalService
from backend.app.ai.llm.base import LLMProvider
from backend.app.ai.llm.exceptions import LLMProviderError
from backend.app.ai.llm.schemas import LLMGeneration
from backend.app.ai.usage.policy import AIQuotaPolicy, MONTHLY_AI_REQUESTS
from backend.app.ai.usage.service import AIUsageService
from backend.app.assistants.registry import build_default_assistant_registry
from backend.app.config.settings import Settings
from backend.app.models import Base, Company, User, UserRole
from modules.entitlements import InMemoryModuleEntitlements, ModuleAccessService
from shared.ai_engine.contracts import TenantContext

pytestmark = pytest.mark.asyncio


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'central-ai.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


class StubProvider(LLMProvider):
    name = "provider-neutral-stub"
    supports_tool_calling = False

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def generate(self, *, system_instruction: str, prompt: str) -> LLMGeneration:
        self.calls += 1
        if self.fail:
            raise LLMProviderError("provider failed")
        return LLMGeneration(
            content="Retail answer",
            provider=self.name,
            model="stub-model",
            token_usage={"input_tokens": 4, "output_tokens": 2},
        )

    async def stream(self, *, system_instruction: str, prompt: str):
        yield "Retail answer"


def make_company(session, slug: str = "tenant-a", plan: str = "demo"):
    company = Company(
        name=slug,
        slug=slug,
        email=f"{slug}@example.ca",
        country="CA",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan=plan,
    )
    session.add(company)
    session.flush()
    user = User(
        company_id=company.id,
        first_name="Ari",
        last_name="Analyst",
        email=f"user-{slug}@example.ca",
        password_hash="hash",
        role=UserRole.ANALYST,
    )
    session.add(user)
    session.flush()
    return company, user


def make_service(session, company, provider, *, limit: int, retail_entitled: bool = True):
    usage = AIUsageService(
        session,
        AIQuotaPolicy(
            Settings(
                AUTH_JWT_SECRET="a" * 32,
                AI_QUOTA_LIMITS={company.subscription_plan: {MONTHLY_AI_REQUESTS: limit}},
            )
        ),
    )
    conversations = ConversationService(session)
    chat = ChatService(conversations, RetrievalService(session), provider, usage_service=usage)
    tenant = TenantContext(company_id=company.id)
    entitlements = InMemoryModuleEntitlements()
    if retail_entitled:
        entitlements.activate(tenant, "retail")
    central = CentralAIService(
        build_default_assistant_registry(),
        chat,
        usage,
        ModuleAccessService(entitlements),
    )
    return central, conversations, usage, tenant


async def execute(central, tenant, user, conversation, query):
    return await central.execute(
        tenant,
        user.id,
        conversation.id,
        query,
        permissions=frozenset(),
        plan_code=user.company.subscription_plan,
        capabilities=frozenset(),
        request_id="request-id",
        user_language="fr",
        company_country="CA",
        company_currency="CAD",
        company_timezone="America/Toronto",
    )


@pytest.mark.parametrize(
    "query",
    [
        "Show sales trends",
        "Quels clients nécessitent mon attention?",
        "Top produits et recommandations",
        "Detect KPI anomalies",
    ],
)
async def test_retail_intents_route_to_retail_intelligence(db_session, query) -> None:
    company, user = make_company(db_session)
    provider = StubProvider()
    central, conversations, _, tenant = make_service(db_session, company, provider, limit=5)
    conversation = conversations.create(company.id, user.id, "Retail")

    result = await execute(central, tenant, user, conversation, query)

    assert result.selected_agent == "retail"
    assert result.status == "success"
    assert result.answer == "Retail answer"
    assert provider.calls == 1


async def test_coming_soon_and_unknown_intents_never_call_provider_or_consume_credit(db_session) -> None:
    company, user = make_company(db_session)
    provider = StubProvider()
    central, conversations, usage, tenant = make_service(db_session, company, provider, limit=3)
    conversation = conversations.create(company.id, user.id, "Routing")

    crm = await execute(central, tenant, user, conversation, "Prioritize my CRM leads")
    unrelated = await execute(central, tenant, user, conversation, "Draft a birthday poem")

    assert (crm.selected_agent, crm.status, crm.agent_availability) == (
        "crm", "agent_unavailable", "coming_soon"
    )
    assert unrelated.status == "unsupported_intent"
    assert provider.calls == 0
    assert usage.get_credit_balance(company.id, "demo")["monthly_used"] == 0


async def test_non_entitled_retail_request_never_calls_provider_or_consumes_credit(db_session) -> None:
    company, user = make_company(db_session, "not-entitled")
    provider = StubProvider()
    central, conversations, usage, tenant = make_service(
        db_session, company, provider, limit=3, retail_entitled=False
    )
    conversation = conversations.create(company.id, user.id, "Retail")

    result = await execute(central, tenant, user, conversation, "Show sales trends")

    assert (result.selected_agent, result.status, result.agent_availability) == (
        "retail", "not_entitled", "not_entitled"
    )
    assert provider.calls == 0
    assert usage.get_credit_balance(company.id, "demo")["monthly_used"] == 0


async def test_other_tenant_conversation_is_rejected_before_provider_call(db_session) -> None:
    first_company, first_user = make_company(db_session, "tenant-a")
    second_company, second_user = make_company(db_session, "tenant-b")
    provider = StubProvider()
    central, conversations, _, first_tenant = make_service(
        db_session, first_company, provider, limit=2
    )
    other_conversation = conversations.create(second_company.id, second_user.id, "Private")

    with pytest.raises(ConversationNotFoundError):
        await execute(
            central, first_tenant, first_user, other_conversation, "Show sales"
        )
    assert provider.calls == 0


async def test_zero_credits_blocks_and_success_consumes_one_credit(db_session) -> None:
    blocked_company, blocked_user = make_company(db_session, "blocked")
    blocked_provider = StubProvider()
    blocked, conversations, blocked_usage, blocked_tenant = make_service(
        db_session, blocked_company, blocked_provider, limit=0
    )
    blocked_conversation = conversations.create(blocked_company.id, blocked_user.id, "Blocked")

    result = await execute(
        blocked, blocked_tenant, blocked_user, blocked_conversation, "Show sales"
    )
    assert result.status == "credits_exhausted"
    assert result.remaining_ai_credits == 0
    assert blocked_provider.calls == 0
    assert blocked_usage.get_credit_balance(blocked_company.id, "demo")["monthly_used"] == 0

    active_company, active_user = make_company(db_session, "active")
    active_provider = StubProvider()
    active, active_conversations, active_usage, active_tenant = make_service(
        db_session, active_company, active_provider, limit=2
    )
    active_conversation = active_conversations.create(active_company.id, active_user.id, "Active")
    success = await execute(
        active, active_tenant, active_user, active_conversation, "Show sales"
    )
    assert success.status == "success"
    assert success.remaining_ai_credits == 1
    assert active_usage.get_credit_balance(active_company.id, "demo")["monthly_used"] == 1


async def test_provider_failure_does_not_consume_purchased_credit(db_session) -> None:
    company, user = make_company(db_session, "provider-failure")
    provider = StubProvider(fail=True)
    central, conversations, usage, tenant = make_service(db_session, company, provider, limit=0)
    usage.add_purchased_credits(company.id, 1)
    conversation = conversations.create(company.id, user.id, "Failure")

    with pytest.raises(AIServiceUnavailableError):
        await execute(central, tenant, user, conversation, "Show sales")

    assert provider.calls == 1
    balance = usage.get_credit_balance(company.id, "demo")
    assert balance["purchased_remaining"] == 1
    assert balance["monthly_used"] == 0


async def test_intent_router_does_not_silently_send_unrelated_work_to_retail() -> None:
    router = CentralAIIntentRouter(build_default_assistant_registry())

    assert router.select("Write an employment policy") is None