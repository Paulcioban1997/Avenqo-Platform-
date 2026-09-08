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

from decimal import Decimal
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
from backend.app.ai.llm.schemas import LLMGeneration, LLMStreamChunk
from backend.app.ai.chat.exceptions import AIServiceUnavailableError
from backend.app.ai.usage.exceptions import (
    AI_REQUEST_ALREADY_PROCESSED,
    AIQuotaExceededError,
    AIRequestConflictError,
)
from backend.app.ai.usage.policy import (
    MAX_CONVERSATION_HISTORY,
    MONTHLY_AI_REQUESTS,
    MONTHLY_LLM_TOKENS,
    AIQuotaPolicy,
)
from backend.app.ai.usage.service import AIUsageService, credits_from_provider_cost, tokens_from_usage
from backend.app.config.settings import Settings
from backend.app.models import Base, Company, User, UserRole
from backend.app.models.ai_usage import TenantAICreditBalance, TenantAIProviderAttempt, TenantAIUsage
from backend.app.ai.llm.schemas import LLMProviderAttempt, LLMUsage

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


class MeteredStreamingProvider(StubLLMProvider):
    async def stream_events(self, *, system_instruction: str, prompt: str):
        usage = LLMUsage(
            provider=self.name,
            model="fake-model",
            input_tokens=10,
            output_tokens=5,
            provider_request_id="provider-stream",
            avenqo_request_id="avenqo-stream",
        )
        attempt = LLMProviderAttempt(
            provider=self.name,
            model="fake-model",
            operation="stream",
            attempt_number=1,
            success=True,
            latency_ms=10,
            usage=usage,
            provider_cost_usd=Decimal("0.00031"),
        )
        yield LLMStreamChunk(content=self._content)
        yield LLMStreamChunk(usage=usage, attempts=(attempt,))


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


def test_usage_service_tracks_usage_below_catalog_allowance_without_override(db_session) -> None:
    company = _company(db_session)
    service = AIUsageService(db_session, AIQuotaPolicy(_settings()))

    assert service.limit_for(company.id, "demo", MONTHLY_AI_REQUESTS) == 6_500
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


def test_demo_credits_consume_included_before_purchased_and_survive_renewal(
    db_session,
) -> None:
    company = _company(db_session, slug="credits")
    service = AIUsageService(
        db_session,
        AIQuotaPolicy(_settings({"demo": {MONTHLY_AI_REQUESTS: 6_500}})),
    )
    service.add_purchased_credits(company.id, 6_500)

    balance = db_session.get(TenantAICreditBalance, company.id)
    balance.monthly_used = 6_499
    service.record_usage(company.id, "demo")
    assert service.get_credit_balance(company.id, "demo")["purchased_remaining"] == 6_500

    service.record_usage(company.id, "demo")
    assert service.get_credit_balance(company.id, "demo")["purchased_remaining"] == 6_499

    service.reset_credits_for_renewal(company.id, "2025-02")
    reset = service.get_credit_balance(company.id, "demo")
    assert reset["monthly_used"] == 0
    assert reset["monthly_remaining"] == 6_500
    assert reset["purchased_remaining"] == 6_499
    assert reset["total_remaining"] == 12_999


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


def test_renewal_resets_only_included_credits_for_one_tenant(db_session) -> None:
    company_a = _company(db_session, slug="renewal-a")
    company_b = _company(db_session, slug="renewal-b")
    service = AIUsageService(
        db_session,
        AIQuotaPolicy(_settings({"demo": {MONTHLY_AI_REQUESTS: 100}})),
    )
    service.add_purchased_credits(company_a.id, 6499)
    service.add_purchased_credits(company_b.id, 321)
    service.record_usage(company_a.id, "demo")
    service.reset_credits_for_renewal(company_a.id, "2025-02")

    balance_a = service.get_credit_balance(company_a.id, "demo")
    balance_b = service.get_credit_balance(company_b.id, "demo")
    assert balance_a["monthly_used"] == 0
    assert balance_a["purchased_remaining"] == 6499
    assert balance_b["purchased_remaining"] == 321


def test_purchased_credits_never_become_negative(db_session) -> None:
    company = _company(db_session, slug="credits-floor")
    service = AIUsageService(
        db_session,
        AIQuotaPolicy(_settings({"demo": {MONTHLY_AI_REQUESTS: 0}})),
    )
    service.add_purchased_credits(company.id, 1)
    service.record_usage(company.id, "demo")
    with pytest.raises(AIQuotaExceededError):
        service.record_usage(company.id, "demo")
    assert service.get_credit_balance(company.id, "demo")["purchased_remaining"] == 0


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


def test_provider_cost_is_converted_to_credits_with_decimal_ceiling() -> None:
    assert credits_from_provider_cost(Decimal("0"), Decimal("0.00030")) == 0
    assert credits_from_provider_cost(Decimal("0.00030"), Decimal("0.00030")) == 1
    assert credits_from_provider_cost(Decimal("0.000300000001"), Decimal("0.00030")) == 2


def test_provider_attempt_ledger_is_tenant_scoped_and_idempotent(db_session) -> None:
    company_a = _company(db_session, slug="metering-a")
    company_b = _company(db_session, slug="metering-b")
    service = AIUsageService(
        db_session,
        AIQuotaPolicy(_settings({"demo": {MONTHLY_AI_REQUESTS: 1}})),
        Decimal("0.00030"),
    )
    service.add_purchased_credits(company_a.id, 5)
    attempts = (
        LLMProviderAttempt(
            provider="openai",
            model="gpt-4o-mini",
            operation="generate",
            attempt_number=1,
            success=False,
            failure_category="timeout",
            latency_ms=50,
            usage=LLMUsage(
                provider="openai",
                model="gpt-4o-mini",
                input_tokens=1_000,
                output_tokens=100,
                provider_request_id="provider-a",
                avenqo_request_id="avenqo-a",
            ),
            provider_cost_usd=Decimal("0.00031"),
            input_cost_per_million_usd=Decimal("0.15"),
            output_cost_per_million_usd=Decimal("0.60"),
        ),
        LLMProviderAttempt(
            provider="gemini",
            model="gemini-flash-latest",
            operation="generate",
            attempt_number=2,
            success=True,
            latency_ms=25,
            usage=LLMUsage(
                provider="gemini",
                model="gemini-flash-latest",
                input_tokens=1_000,
                output_tokens=100,
                provider_request_id="provider-b",
                avenqo_request_id="avenqo-a",
            ),
            provider_cost_usd=Decimal("0.00020"),
            input_cost_per_million_usd=Decimal("0.10"),
            output_cost_per_million_usd=Decimal("0.40"),
        ),
    )

    service.record_usage(company_a.id, "demo", tokens=2_200, attempts=attempts)
    service.record_usage(company_a.id, "demo", tokens=2_200, attempts=attempts)

    balance = service.get_credit_balance(company_a.id, "demo")
    assert balance["monthly_used"] == 1
    assert balance["purchased_remaining"] == 4
    rows = db_session.query(TenantAIProviderAttempt).order_by(TenantAIProviderAttempt.attempt_number).all()
    assert len(rows) == 2
    assert [row.provider for row in rows] == ["openai", "gemini"]
    assert [row.avenqo_credits for row in rows] == [0, 2]
    assert rows[0].provider_request_id == "provider-a"
    assert rows[0].input_cost_per_million_usd == Decimal("0.15000000")
    assert db_session.query(TenantAIProviderAttempt).filter_by(company_id=company_b.id).count() == 0
    assert service.get_usage(company_a.id, "demo").ai_requests_count == 1


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


async def test_chat_service_duplicate_request_id_never_reexecutes_provider(db_session) -> None:
    company = _company(db_session, slug="duplicate-request")
    user = _user(db_session, company)
    conversations = ConversationService(db_session)
    provider = StubLLMProvider()
    usage_service = AIUsageService(
        db_session,
        AIQuotaPolicy(_settings({"demo": {MONTHLY_AI_REQUESTS: 2}})),
    )
    service = ChatService(
        conversations,
        RetrievalService(db_session),
        provider,
        usage_service=usage_service,
    )
    conversation = conversations.create(company.id, user.id, "Chat")

    await service.send(
        company.id,
        user.id,
        conversation.id,
        "hi",
        plan_code="demo",
        request_id="stable-request-id",
    )

    with pytest.raises(
        AIRequestConflictError,
        match=f"^{AI_REQUEST_ALREADY_PROCESSED}$",
    ):
        await service.send(
            company.id,
            user.id,
            conversation.id,
            "hi again",
            plan_code="demo",
            request_id="stable-request-id",
        )

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


async def test_chat_service_stream_records_real_tokens_cost_and_attempt(db_session) -> None:
    company = _company(db_session, slug="metered-stream")
    user = _user(db_session, company)
    conversations = ConversationService(db_session)
    usage_service = AIUsageService(
        db_session,
        AIQuotaPolicy(_settings({"demo": {MONTHLY_AI_REQUESTS: 10}})),
        Decimal("0.00030"),
    )
    service = ChatService(
        conversations,
        RetrievalService(db_session),
        MeteredStreamingProvider(),
        usage_service=usage_service,
    )
    conversation = conversations.create(company.id, user.id, "Chat")

    events = [
        event async for event in service.stream(
            company.id,
            user.id,
            conversation.id,
            "hi",
            plan_code="demo",
            request_id="avenqo-stream",
        )
    ]

    assert [event.kind for event in events] == ["delta", "sources", "done"]
    assert usage_service.get_usage(company.id, "demo").llm_tokens_count == 15
    assert usage_service.get_credit_balance(company.id, "demo")["monthly_used"] == 2
    ledger = db_session.query(TenantAIProviderAttempt).one()
    assert ledger.provider_request_id == "provider-stream"
    assert ledger.avenqo_credits == 2


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
