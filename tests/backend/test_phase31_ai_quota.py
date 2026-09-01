"""Phase 31 (addendum) — Quotas d'usage IA Avenqo, indépendants du fournisseur LLM.

Couvre : résolution des limites par plan (`AIQuotaPolicy`, aucune valeur
commerciale par défaut), incrémentation/lecture de l'usage tenant
(`AIUsageService`, `TenantAIUsage`), isolation stricte entre tenants,
dépassement de quota contrôlé (`AIQuotaExceededError`, jamais l'erreur brute
d'un fournisseur), plans Demo/Professional/Enterprise reconnus (y compris
limites configurables par contrat pour Enterprise, pas d'illimité
automatique), et intégration bout-en-bout dans `ChatService.send()`/`stream()`
(vérification AVANT l'appel LLM/outil).
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
from backend.app.ai.llm.exceptions import LLMProviderError
from backend.app.ai.llm.schemas import LLMGeneration
from backend.app.ai.chat.exceptions import AIServiceUnavailableError
from backend.app.ai.usage.exceptions import AIQuotaExceededError
from backend.app.ai.usage.policy import (
    MAX_CONVERSATION_HISTORY,
    MONTHLY_AI_REQUESTS,
    MONTHLY_LLM_TOKENS,
    AIQuotaPolicy,
)
from backend.app.ai.usage.service import AIUsageService, tokens_from_usage
from backend.app.config.settings import Settings
from backend.app.models import Base, Company, User, UserRole
from backend.app.models.ai_usage import TenantAICreditBalance, TenantAIUsage

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'phase31_quota.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


def _company(session, *, plan: str = "demo", slug: str = "acme") -> Company:
    company = Company(
        name="Acme", slug=slug, email=f"{slug}@example.com", country="CA",
        timezone="America/Toronto", industry="Retail", subscription_plan=plan,
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


class StubLLMProvider(LLMProvider):
    name = "fake"
    supports_tool_calling = False

    def __init__(self, content: str = "reply") -> None:
        self._content = content
        self.generate_calls = 0

    async def generate(self, *, system_instruction: str, prompt: str) -> LLMGeneration:
        self.generate_calls += 1
        return LLMGeneration(
            content=self._content, provider=self.name, model="fake-model",
            token_usage={"input_tokens": 10, "output_tokens": 5},
        )

    async def stream(self, *, system_instruction: str, prompt: str):
        yield self._content


class FailingLLMProvider(StubLLMProvider):
    async def generate(self, *, system_instruction: str, prompt: str) -> LLMGeneration:
        self.generate_calls += 1
        raise LLMProviderError("provider failed")


def _settings(limits: dict[str, dict[str, int]] | None = None) -> Settings:
    return Settings(AUTH_JWT_SECRET="a" * 32, AI_QUOTA_LIMITS=limits or {})


# ---------------------------------------------------------------------------
# 1. AIQuotaPolicy — no invented commercial numbers by default
# ---------------------------------------------------------------------------


def test_policy_returns_none_when_no_limit_configured() -> None:
    policy = AIQuotaPolicy(_settings())

    assert policy.limit_for("demo", MONTHLY_AI_REQUESTS) is None
    assert policy.limit_for("professional", MONTHLY_LLM_TOKENS) is None
    assert policy.limit_for("enterprise", MAX_CONVERSATION_HISTORY) is None
    assert policy.limit_for(None, MONTHLY_AI_REQUESTS) is None


def test_policy_resolves_configured_limit_per_plan() -> None:
    policy = AIQuotaPolicy(_settings({"demo": {MONTHLY_AI_REQUESTS: 3}, "enterprise": {MONTHLY_AI_REQUESTS: 500}}))

    assert policy.limit_for("demo", MONTHLY_AI_REQUESTS) == 3
    assert policy.limit_for("enterprise", MONTHLY_AI_REQUESTS) == 500
    # Un plan sans configuration explicite reste non plafonné.
    assert policy.limit_for("professional", MONTHLY_AI_REQUESTS) is None


# ---------------------------------------------------------------------------
# 2. AIUsageService — increment / read / enforce
# ---------------------------------------------------------------------------


def test_usage_service_allows_unlimited_usage_when_no_limit_configured(db_session) -> None:
    company = _company(db_session)
    service = AIUsageService(db_session, AIQuotaPolicy(_settings()))

    for _ in range(50):
        service.ensure_quota_available(company.id, "demo")
        service.record_usage(company.id, "demo", tokens=100, tool_calls=2)

    usage = service.get_usage(company.id, "demo")
    assert usage.ai_requests_count == 50
    assert usage.llm_tokens_count == 5000
    assert usage.tool_calls_count == 100


def test_usage_service_raises_quota_exceeded_error_when_limit_reached(db_session) -> None:
    company = _company(db_session)
    service = AIUsageService(db_session, AIQuotaPolicy(_settings({"demo": {MONTHLY_AI_REQUESTS: 2}})))

    service.ensure_quota_available(company.id, "demo")
    service.record_usage(company.id, "demo")
    service.ensure_quota_available(company.id, "demo")
    service.record_usage(company.id, "demo")

    with pytest.raises(AIQuotaExceededError):
        service.ensure_quota_available(company.id, "demo")


def test_quota_exceeded_error_never_leaks_provider_details(db_session) -> None:
    company = _company(db_session)
    service = AIUsageService(db_session, AIQuotaPolicy(_settings({"demo": {MONTHLY_AI_REQUESTS: 1}})))
    service.ensure_quota_available(company.id, "demo")
    service.record_usage(company.id, "demo")

    with pytest.raises(AIQuotaExceededError) as exc_info:
        service.ensure_quota_available(company.id, "demo")

    message = str(exc_info.value)
    for forbidden in ("openai", "anthropic", "gemini", "api_key", "traceback"):
        assert forbidden not in message.lower()


def test_usage_service_tracks_tenant_quota_isolation(db_session) -> None:
    company_a = _company(db_session, slug="tenant-a")
    company_b = _company(db_session, slug="tenant-b")
    service = AIUsageService(db_session, AIQuotaPolicy(_settings({"demo": {MONTHLY_AI_REQUESTS: 1}})))

    service.ensure_quota_available(company_a.id, "demo")
    service.record_usage(company_a.id, "demo")

    with pytest.raises(AIQuotaExceededError):
        service.ensure_quota_available(company_a.id, "demo")

    # Le quota épuisé de tenant A ne doit jamais affecter tenant B.
    service.ensure_quota_available(company_b.id, "demo")
    service.record_usage(company_b.id, "demo")

    usage_a = service.get_usage(company_a.id, "demo")
    usage_b = service.get_usage(company_b.id, "demo")
    assert usage_a.ai_requests_count == 1
    assert usage_b.ai_requests_count == 1


def test_credits_consume_monthly_before_purchased_and_keep_topups_across_reset(
    db_session, monkeypatch
) -> None:
    company = _company(db_session, slug="credits")
    service = AIUsageService(
        db_session,
        AIQuotaPolicy(_settings({"demo": {MONTHLY_AI_REQUESTS: 2}})),
    )
    service.add_purchased_credits(company.id, 3)

    service.record_usage(company.id, "demo")
    service.record_usage(company.id, "demo")
    assert service.get_credit_balance(company.id, "demo")["purchased_remaining"] == 3

    service.record_usage(company.id, "demo")
    assert service.get_credit_balance(company.id, "demo")["purchased_remaining"] == 2

    balance = db_session.get(TenantAICreditBalance, company.id)
    balance.monthly_period = "2025-01"
    reset = service.get_credit_balance(company.id, "demo")
    assert reset["monthly_used"] == 0
    assert reset["monthly_remaining"] == 2
    assert reset["purchased_remaining"] == 2


def test_purchased_credits_are_strictly_tenant_scoped(db_session) -> None:
    company_a = _company(db_session, slug="credits-a")
    company_b = _company(db_session, slug="credits-b")
    service = AIUsageService(
        db_session,
        AIQuotaPolicy(_settings({"demo": {MONTHLY_AI_REQUESTS: 0}})),
    )
    service.add_purchased_credits(company_a.id, 1)
    service.ensure_quota_available(company_a.id, "demo")
    service.record_usage(company_a.id, "demo")

    with pytest.raises(AIQuotaExceededError):
        service.ensure_quota_available(company_a.id, "demo")
    with pytest.raises(AIQuotaExceededError):
        service.ensure_quota_available(company_b.id, "demo")


def test_usage_rows_are_scoped_by_company_and_billing_period(db_session) -> None:
    company = _company(db_session)
    service = AIUsageService(db_session, AIQuotaPolicy(_settings()))
    service.record_usage(company.id, "demo")

    rows = db_session.query(TenantAIUsage).filter(TenantAIUsage.company_id == company.id).all()
    assert len(rows) == 1
    assert rows[0].billing_period == service.current_billing_period()
    assert rows[0].subscription_plan == "demo"


# ---------------------------------------------------------------------------
# 3. Enterprise configurable limits — pas d'illimité automatique
# ---------------------------------------------------------------------------


def test_enterprise_plan_can_have_a_contractual_limit_configured(db_session) -> None:
    company = _company(db_session, plan="enterprise", slug="enterprise-co")
    service = AIUsageService(db_session, AIQuotaPolicy(_settings({"enterprise": {MONTHLY_AI_REQUESTS: 5}})))

    for _ in range(5):
        service.ensure_quota_available(company.id, "enterprise")
        service.record_usage(company.id, "enterprise")

    with pytest.raises(AIQuotaExceededError):
        service.ensure_quota_available(company.id, "enterprise")


def test_enterprise_plan_without_configured_limit_is_not_forced_unlimited_silently(db_session) -> None:
    """Sans limite configurée, Enterprise n'est pas plafonné — mais ce n'est pas
    une décision commerciale arbitraire du code : c'est simplement l'état
    "non configuré" par défaut, identique aux autres plans."""

    company = _company(db_session, plan="enterprise", slug="enterprise-default")
    policy = AIQuotaPolicy(_settings())
    service = AIUsageService(db_session, policy)

    assert policy.limit_for("enterprise", MONTHLY_AI_REQUESTS) is None
    for _ in range(10):
        service.ensure_quota_available(company.id, "enterprise")
        service.record_usage(company.id, "enterprise")


# ---------------------------------------------------------------------------
# 4. Provider-independent usage aggregation
# ---------------------------------------------------------------------------


def test_tokens_from_usage_sums_input_and_output_regardless_of_provider_shape() -> None:
    assert tokens_from_usage({"input_tokens": 12, "output_tokens": 8}) == 20
    assert tokens_from_usage({}) == 0
    assert tokens_from_usage({"input_tokens": 3}) == 3


def test_usage_aggregates_across_different_provider_shaped_calls(db_session) -> None:
    company = _company(db_session)
    service = AIUsageService(db_session, AIQuotaPolicy(_settings()))

    # Simule un appel OpenAI puis un appel Anthropic : un seul compteur "Avenqo AI".
    service.record_usage(company.id, "demo", tokens=tokens_from_usage({"input_tokens": 10, "output_tokens": 5}))
    service.record_usage(company.id, "demo", tokens=tokens_from_usage({"input_tokens": 7, "output_tokens": 2}))

    usage = service.get_usage(company.id, "demo")
    assert usage.ai_requests_count == 2
    assert usage.llm_tokens_count == 24


# ---------------------------------------------------------------------------
# 5. ChatService integration — gating BEFORE the LLM/provider call
# ---------------------------------------------------------------------------


async def test_chat_service_send_blocks_before_llm_call_when_quota_exceeded(db_session) -> None:
    company = _company(db_session)
    user = _user(db_session, company)
    conversations = ConversationService(db_session)
    retrieval = RetrievalService(db_session)
    provider = StubLLMProvider()
    usage_service = AIUsageService(db_session, AIQuotaPolicy(_settings({"demo": {MONTHLY_AI_REQUESTS: 1}})))
    service = ChatService(conversations, retrieval, provider, usage_service=usage_service)
    conversation = conversations.create(company.id, user.id, "Chat")

    message, _sources = await service.send(company.id, user.id, conversation.id, "hi", plan_code="demo")
    assert message.content == "reply"
    assert provider.generate_calls == 1

    with pytest.raises(AIQuotaExceededError):
        await service.send(company.id, user.id, conversation.id, "hi again", plan_code="demo")

    # Le provider ne doit JAMAIS être appelé une fois le quota dépassé.
    assert provider.generate_calls == 1


async def test_chat_service_records_usage_after_successful_send(db_session) -> None:
    company = _company(db_session)
    user = _user(db_session, company)
    conversations = ConversationService(db_session)
    retrieval = RetrievalService(db_session)
    provider = StubLLMProvider()
    usage_service = AIUsageService(db_session, AIQuotaPolicy(_settings()))
    service = ChatService(conversations, retrieval, provider, usage_service=usage_service)
    conversation = conversations.create(company.id, user.id, "Chat")

    await service.send(company.id, user.id, conversation.id, "hi", plan_code="demo")

    usage = usage_service.get_usage(company.id, "demo")
    assert usage.ai_requests_count == 1
    assert usage.llm_tokens_count == 15  # 10 input + 5 output (StubLLMProvider)


async def test_chat_service_does_not_consume_purchased_credit_on_provider_failure(db_session) -> None:
    company = _company(db_session, slug="failed-credit")
    user = _user(db_session, company)
    usage_service = AIUsageService(
        db_session,
        AIQuotaPolicy(_settings({"demo": {MONTHLY_AI_REQUESTS: 0}})),
    )
    usage_service.add_purchased_credits(company.id, 1)
    conversations = ConversationService(db_session)
    service = ChatService(
        conversations,
        RetrievalService(db_session),
        FailingLLMProvider(),
        usage_service=usage_service,
    )
    conversation = conversations.create(company.id, user.id, "Chat")

    with pytest.raises(AIServiceUnavailableError):
        await service.send(company.id, user.id, conversation.id, "hi", plan_code="demo")

    balance = usage_service.get_credit_balance(company.id, "demo")
    assert balance["purchased_remaining"] == 1
    assert usage_service.get_usage(company.id, "demo").ai_requests_count == 0


async def test_chat_service_stream_yields_safe_error_event_when_quota_exceeded(db_session) -> None:
    company = _company(db_session)
    user = _user(db_session, company)
    conversations = ConversationService(db_session)
    retrieval = RetrievalService(db_session)
    provider = StubLLMProvider()
    usage_service = AIUsageService(db_session, AIQuotaPolicy(_settings({"demo": {MONTHLY_AI_REQUESTS: 0}})))
    service = ChatService(conversations, retrieval, provider, usage_service=usage_service)
    conversation = conversations.create(company.id, user.id, "Chat")

    events = [event async for event in service.stream(company.id, user.id, conversation.id, "hi", plan_code="demo")]

    assert len(events) == 1
    assert events[0].kind == "error"
    detail = events[0].payload["detail"]
    for forbidden in ("openai", "anthropic", "gemini", "traceback"):
        assert forbidden not in detail.lower()
    # Rien n'a dû être persisté au-delà du message utilisateur initial.
    assert conversations.messages(company.id, conversation.id) == [] or all(
        message.role.value == "user" for message in conversations.messages(company.id, conversation.id)
    )


async def test_chat_service_without_usage_service_is_unaffected_backward_compatible(db_session) -> None:
    company = _company(db_session)
    user = _user(db_session, company)
    conversations = ConversationService(db_session)
    retrieval = RetrievalService(db_session)
    provider = StubLLMProvider()
    service = ChatService(conversations, retrieval, provider)
    conversation = conversations.create(company.id, user.id, "Chat")

    for _ in range(5):
        message, _ = await service.send(company.id, user.id, conversation.id, "hi", plan_code="demo")
        assert message.content == "reply"
