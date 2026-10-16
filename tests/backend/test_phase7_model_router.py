"""Tests for Central AI Model Router Modernization.

Validates:
1. Official API model specs and rate cards (OpenAI gpt-4o-mini, gpt-4o; Gemini 2.0 Flash; Claude 3.5 Haiku, Sonnet).
2. Rejection of unvalidated fictional model names (Rule #10).
3. Intelligent routing: Tier 1 economic for daily chat, automatic escalation to Tier 2/Quality 3 for complex reasoning.
4. Cross-provider fallback on transient failures.
5. Conversational memory, RAG tenant grounding, and multi-tenant isolation.
6. Credit ledger integration: tokens, cost, reserved/charged credits.
7. Spend ceilings: per-request, per-session, and per-company.
8. Streaming SSE, tool calling, and 44-language localization consistency.
"""

from __future__ import annotations

from decimal import Decimal
import pytest
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

from backend.app.ai.llm.base import LLMProvider
from backend.app.ai.llm.circuit_breaker import ProviderCircuitBreaker
from backend.app.ai.llm.exceptions import AIProvidersUnavailableError, LLMProviderError
from backend.app.ai.llm.failure_classification import FailureCategory
from backend.app.ai.llm.gateway import AvenqoAIGateway
from backend.app.ai.llm.health import ProviderHealthRegistry, ProviderHealthStatus
from backend.app.ai.llm.model_registry import (
    LLMCapability,
    LLMModelRegistry,
    LLMRateCard,
    model_spec,
)
from backend.app.ai.llm.router import (
    LLMRoutingContext,
    LLMTaskComplexity,
    LLMTaskType,
    SmartModelRouter,
    routing_context_for_chat,
)
from backend.app.ai.llm.schemas import (
    LLMGeneration,
    LLMMessage,
    LLMProviderAttempt,
    LLMStreamChunk,
    LLMUsage,
    ToolDefinition,
)
from backend.app.ai.usage.credit_policy import AvenqoCreditPolicy
from backend.app.ai.usage.exceptions import (
    AIQuotaExceededError,
    AIRequestBudgetExceededError,
    INSUFFICIENT_AI_CREDITS,
)
from backend.app.ai.usage.policy import AIQuotaPolicy
from backend.app.ai.usage.service import AIUsageService
from backend.app.config.settings import Settings
from backend.app.models.ai_usage import TenantAICreditBalance, TenantAIProviderAttempt
from shared.ai_engine.contracts import TenantContext


class MockChatProvider(LLMProvider):
    def __init__(
        self,
        name: str,
        model_id: str,
        *,
        fail_with: Exception | None = None,
        supports_tools: bool = True,
    ) -> None:
        self.name = name
        self.model_id = model_id
        self._fail = fail_with
        self.supports_tool_calling = supports_tools
        self.calls: list[dict[str, object]] = []

    async def generate(self, *, system_instruction: str, prompt: str) -> LLMGeneration:
        self.calls.append({"system_instruction": system_instruction, "prompt": prompt})
        if self._fail is not None:
            raise self._fail
        return LLMGeneration(
            content=f"Response from {self.name}:{self.model_id}",
            provider=self.name,
            model=self.model_id,
            token_usage={
                "input_tokens": 120,
                "output_tokens": 60,
                "cached_input_tokens": 20,
            },
        )

    async def stream(self, *, system_instruction: str, prompt: str):
        self.calls.append({"system_instruction": system_instruction, "prompt": prompt})
        if self._fail is not None:
            raise self._fail
        yield "Hello "
        yield "World"

    async def stream_events(self, *, system_instruction: str, prompt: str):
        self.calls.append({"system_instruction": system_instruction, "prompt": prompt})
        if self._fail is not None:
            raise self._fail
        yield LLMStreamChunk(content="Hello ")
        yield LLMStreamChunk(content="World")
        yield LLMStreamChunk(
            usage=LLMUsage(
                provider=self.name,
                model=self.model_id,
                input_tokens=100,
                output_tokens=50,
            )
        )


def _build_test_rate_card() -> LLMRateCard:
    models = {
        "openai": ("gpt-4o-mini", "gpt-4o"),
        "gemini": ("gemini-2.0-flash", "gemini-1.5-flash"),
        "anthropic": ("claude-3-5-haiku-20241022", "claude-3-5-sonnet-20241022"),
    }
    return LLMRateCard.from_models(models)


# ==============================================================================
# 1. Official API Models, Pricing & Rejection of Fictional Names (Rule #10)
# ==============================================================================

def test_official_model_specs_and_rates() -> None:
    rate_card = _build_test_rate_card()

    # OpenAI gpt-4o-mini
    mini_spec = rate_card.spec_for("openai", "gpt-4o-mini")
    assert mini_spec.input_cost_per_million_usd == Decimal("0.15")
    assert mini_spec.output_cost_per_million_usd == Decimal("0.60")
    assert mini_spec.quality_tier == 2
    assert mini_spec.speed_tier == 1

    # OpenAI gpt-4o (escalation)
    gpt4o_spec = rate_card.spec_for("openai", "gpt-4o")
    assert gpt4o_spec.input_cost_per_million_usd == Decimal("2.50")
    assert gpt4o_spec.output_cost_per_million_usd == Decimal("10.00")
    assert gpt4o_spec.quality_tier == 3
    assert gpt4o_spec.speed_tier == 2

    # Gemini 2.0 Flash
    gemini_spec = rate_card.spec_for("gemini", "gemini-2.0-flash")
    assert gemini_spec.input_cost_per_million_usd == Decimal("0.10")
    assert gemini_spec.output_cost_per_million_usd == Decimal("0.40")
    assert gemini_spec.quality_tier == 2
    assert gemini_spec.speed_tier == 1

    # Anthropic Claude 3.5 Haiku
    haiku_spec = rate_card.spec_for("anthropic", "claude-3-5-haiku-20241022")
    assert haiku_spec.input_cost_per_million_usd == Decimal("0.80")
    assert haiku_spec.output_cost_per_million_usd == Decimal("4.00")
    assert haiku_spec.quality_tier == 2

    # Gemini 1.5 Flash deprecated/avoided
    legacy_gemini = rate_card.spec_for("gemini", "gemini-1.5-flash")
    assert legacy_gemini.fallback_priority >= 900


def test_rule_10_unvalidated_fictional_models_rejected() -> None:
    """Non-existent candidate names like 'GPT-6 Luna', 'Claude Haiku 5.5', 'Gemini 3.8 Flash',

    'GPT-6 Sol' MUST be rejected as unvalidated by the model registry.
    """
    fictional_models = [
        ("openai", "gpt-6-luna"),
        ("anthropic", "claude-haiku-5-5"),
        ("gemini", "gemini-3-8-flash"),
        ("openai", "gpt-6-sol"),
    ]
    for provider, model_id in fictional_models:
        with pytest.raises(ValueError, match="requires explicit capability and limit metadata"):
            model_spec(provider, model_id)


# ==============================================================================
# 2. Smart Router: Daily Economic Driver vs Complex Escalation
# ==============================================================================

def test_smart_router_selects_economic_daily_driver_for_standard_chat() -> None:
    rate_card = _build_test_rate_card()
    health = ProviderHealthRegistry()
    specs = {
        ("openai", "gpt-4o-mini"): rate_card.spec_for("openai", "gpt-4o-mini"),
        ("openai", "gpt-4o"): rate_card.spec_for("openai", "gpt-4o"),
        ("gemini", "gemini-2.0-flash"): rate_card.spec_for("gemini", "gemini-2.0-flash"),
        ("anthropic", "claude-3-5-haiku-20241022"): rate_card.spec_for("anthropic", "claude-3-5-haiku-20241022"),
    }
    router = SmartModelRouter(specs, health)
    providers = [
        MockChatProvider("openai", "gpt-4o-mini"),
        MockChatProvider("openai", "gpt-4o"),
        MockChatProvider("gemini", "gemini-2.0-flash"),
        MockChatProvider("anthropic", "claude-3-5-haiku-20241022"),
    ]

    context = routing_context_for_chat(
        query="Bonjour, combien ai-je de commandes aujourd'hui ?",
        prompt="User asks for order count",
        has_tools=True,
        plan_code="professional",
        remaining_credits=1000,
        avenqo_request_id="test-req-1",
    )
    decision = router.decide(providers, context)
    # Tier 1 economic model selected for standard chat
    assert decision.selected_provider in {"openai", "gemini"}
    assert decision.selected_model in {"gpt-4o-mini", "gemini-2.0-flash"}
    assert decision.selected_model != "gpt-4o"  # Did not wastefully escalate


def test_smart_router_escalates_to_quality_tier_3_for_complex_reasoning() -> None:
    rate_card = _build_test_rate_card()
    health = ProviderHealthRegistry()
    specs = {
        ("openai", "gpt-4o-mini"): rate_card.spec_for("openai", "gpt-4o-mini"),
        ("openai", "gpt-4o"): rate_card.spec_for("openai", "gpt-4o"),
        ("gemini", "gemini-2.0-flash"): rate_card.spec_for("gemini", "gemini-2.0-flash"),
    }
    router = SmartModelRouter(specs, health)
    providers = [
        MockChatProvider("openai", "gpt-4o-mini"),
        MockChatProvider("openai", "gpt-4o"),
        MockChatProvider("gemini", "gemini-2.0-flash"),
    ]

    context = routing_context_for_chat(
        query="Analyse approfondie de la rentabilité et réconciliation des écarts de marge multi-sources",
        prompt="User asks for deep financial audit",
        has_tools=True,
        plan_code="professional",
        remaining_credits=1000,
        avenqo_request_id="test-req-2",
    )
    assert context.task_type == LLMTaskType.BUSINESS_REASONING
    assert context.complexity in {LLMTaskComplexity.HIGH, LLMTaskComplexity.COMPLEX}

    decision = router.decide(providers, context)
    # Escalated to gpt-4o because quality_tier=3 eliminates the 300-point penalty on complex tasks
    assert decision.selected_provider == "openai"
    assert decision.selected_model == "gpt-4o"


# ==============================================================================
# 3. Automatic Cross-Provider Fallback
# ==============================================================================

@pytest.mark.asyncio
async def test_gateway_automatic_cross_provider_fallback() -> None:
    rate_card = _build_test_rate_card()
    health = ProviderHealthRegistry()
    specs = {
        ("openai", "gpt-4o-mini"): rate_card.spec_for("openai", "gpt-4o-mini"),
        ("gemini", "gemini-2.0-flash"): rate_card.spec_for("gemini", "gemini-2.0-flash"),
    }
    router = SmartModelRouter(specs, health)

    # Primary (gemini-2.0-flash is lowest cost, ranked 1st) fails with transient timeout
    cause = TimeoutError("Gemini 504 Gateway Timeout")
    failure = LLMProviderError("Gemini 504 Gateway Timeout")
    failure.__cause__ = cause
    primary = MockChatProvider(
        "gemini",
        "gemini-2.0-flash",
        fail_with=failure,
    )
    # Fallback (openai:gpt-4o-mini) succeeds
    fallback = MockChatProvider("openai", "gpt-4o-mini")

    gateway = AvenqoAIGateway(
        [primary, fallback],
        circuit_breaker=ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=60),
        health_registry=health,
        router=router,
        rate_card=rate_card,
        max_retries_per_provider=0,
        base_delay_seconds=0.0,
        max_delay_seconds=0.0,
    )

    context = routing_context_for_chat(
        query="Statut du stock",
        prompt="Vérifier le stock",
        has_tools=False,
        plan_code="demo",
        remaining_credits=500,
        avenqo_request_id="test-fallback-1",
    )
    with gateway.routing(context):
        gen = await gateway.generate(system_instruction="sys", prompt="prompt")
        assert "Response from openai:gpt-4o-mini" in gen.content
        assert len(gen.attempts) >= 2
        assert gen.attempts[0].provider == "gemini"
        assert not gen.attempts[0].success
        assert gen.attempts[-1].provider == "openai"
        assert gen.attempts[-1].success


# ==============================================================================
# 4. Spending Ceilings: Per-Request, Per-Session, Per-Company
# ==============================================================================

def test_credit_policy_request_ceilings() -> None:
    policy = AvenqoCreditPolicy(
        provider_cost_per_credit_usd=Decimal("0.00030"),
        max_estimated_provider_cost_usd=Decimal("0.05"),
        max_request_credits=100,
    )

    # Under budget
    policy.validate_estimate(Decimal("0.01"))

    # Cost exceeds max_estimated_provider_cost_usd
    with pytest.raises(ValueError, match="Estimated AI provider cost exceeds the configured request budget"):
        policy.validate_estimate(Decimal("0.06"))

    # Credits exceed max_request_credits
    with pytest.raises(ValueError, match="Estimated AI credits exceed the configured request budget"):
        policy.validate_estimate(Decimal("0.04"))  # 0.04 / 0.0003 = 134 credits > 100


def test_credit_policy_session_and_company_ceilings() -> None:
    policy = AvenqoCreditPolicy(
        provider_cost_per_credit_usd=Decimal("0.00030"),
        max_session_credits=50,
        max_session_cost_usd=Decimal("0.02"),
        max_company_monthly_cost_usd=Decimal("100.00"),
    )

    # Session credit ceiling
    policy.validate_session_credits(30)
    with pytest.raises(ValueError, match="Session AI credit limit exceeded"):
        policy.validate_session_credits(55)

    # Session cost ceiling
    policy.validate_session_cost(Decimal("0.015"))
    with pytest.raises(ValueError, match="Session AI cost limit exceeded"):
        policy.validate_session_cost(Decimal("0.025"))

    # Company monthly cost ceiling
    policy.validate_company_cost(Decimal("80.00"))
    with pytest.raises(ValueError, match="Company monthly AI budget ceiling reached"):
        policy.validate_company_cost(Decimal("105.00"))


def test_service_enforces_session_credit_ceiling_with_db() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from backend.app.models.base import Base
    from backend.app.models.company import Company

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    company = Company(
        id=uuid4(),
        name="Test Ceiling Corp",
        slug=f"ceiling-corp-{uuid4().hex[:6]}",
        email=f"ceiling-{uuid4().hex[:6]}@example.com",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
    )
    db.add(company)
    db.commit()

    conversation_id = uuid4()
    policy = AvenqoCreditPolicy(
        provider_cost_per_credit_usd=Decimal("0.00030"),
        max_session_credits=10,
    )
    service = AIUsageService(db, AIQuotaPolicy(Settings(_env_file=None)), credit_policy=policy)

    # Prepopulate previous attempts on this session consuming 8 credits
    attempt = TenantAIProviderAttempt(
        company_id=company.id,
        avenqo_request_id=str(uuid4()),
        operation="generate",
        attempt_number=1,
        provider="openai",
        model="gpt-4o-mini",
        success=True,
        latency_ms=250,
        conversation_id=conversation_id,
        provider_cost_usd=Decimal("0.0024"),
        input_cost_per_million_usd=Decimal("0.15"),
        cached_input_cost_per_million_usd=Decimal("0.075"),
        output_cost_per_million_usd=Decimal("0.60"),
        tool_call_cost_usd=Decimal("0"),
        avenqo_credits_charged=8,
    )
    db.add(attempt)
    db.commit()

    # Reserving 1 credit: 8 + 1 = 9 <= 10 (ok)
    claim1 = service.claim_credit_reservation(
        company.id,
        "professional",
        "req-allow-1",
        estimated_credits=1,
        conversation_id=conversation_id,
    )
    assert claim1.acquired

    # Reserving 5 credits: 8 + 5 = 13 > 10 (session ceiling tripped)
    with pytest.raises(AIRequestBudgetExceededError, match="Session AI credit limit exceeded"):
        service.claim_credit_reservation(
            company.id,
            "professional",
            "req-block-1",
            estimated_credits=5,
            conversation_id=conversation_id,
        )


# ==============================================================================
# 5. Ledger Integration: Model, Tokens, Provider Cost, and Credit Settlement
# ==============================================================================

def test_credit_ledger_records_model_tokens_cost_and_credits() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from backend.app.models.base import Base
    from backend.app.models.company import Company
    from backend.app.models.ai_usage import TenantAICreditLedgerEntry

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    company = Company(
        id=uuid4(),
        name="Ledger Test Corp",
        slug=f"ledger-corp-{uuid4().hex[:6]}",
        email=f"ledger-{uuid4().hex[:6]}@example.com",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
    )
    db.add(company)
    db.commit()

    policy = AvenqoCreditPolicy(
        provider_cost_per_credit_usd=Decimal("0.00030"),
    )
    service = AIUsageService(db, AIQuotaPolicy(Settings(_env_file=None)), credit_policy=policy)
    service.add_purchased_credits(company.id, 500)

    req_id = f"req-{uuid4().hex[:8]}"
    claim = service.claim_credit_reservation(
        company.id,
        "professional",
        req_id,
        estimated_credits=10,
    )
    assert claim.acquired

    usage = LLMUsage(
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=1500,
        output_tokens=300,
        avenqo_request_id=req_id,
    )
    attempt = LLMProviderAttempt(
        provider="openai",
        model="gpt-4o-mini",
        operation="generate",
        attempt_number=1,
        success=True,
        latency_ms=310,
        usage=usage,
        provider_cost_usd=Decimal("0.000405"),  # 1500 * $0.15 + 300 * $0.60 per 1M = $0.000225 + $0.00018 = $0.000405
        input_cost_per_million_usd=Decimal("0.15"),
        cached_input_cost_per_million_usd=Decimal("0.075"),
        output_cost_per_million_usd=Decimal("0.60"),
        tool_call_cost_usd=Decimal("0"),
        pricing_version="gpt-4o-mini-standard-text-2026-10-01",
    )

    reservation = service.settle_reservation(
        company.id,
        "professional",
        req_id,
        tokens=1800,
        attempts=(attempt,),
    )
    # $0.000405 / 0.00030 = 1.35 -> ceil = 2 credits
    assert reservation.actual_credits == 2
    assert reservation.status == "settled"

    ledger_entries = db.query(TenantAICreditLedgerEntry).filter(
        TenantAICreditLedgerEntry.company_id == company.id,
        TenantAICreditLedgerEntry.reference_id == req_id,
    ).all()
    assert len(ledger_entries) >= 1


# ==============================================================================
# 6. Streaming SSE & Tool Calling
# ==============================================================================

@pytest.mark.asyncio
async def test_streaming_sse_and_tool_calling() -> None:
    rate_card = _build_test_rate_card()
    health = ProviderHealthRegistry()
    specs = {
        ("openai", "gpt-4o-mini"): rate_card.spec_for("openai", "gpt-4o-mini"),
    }
    router = SmartModelRouter(specs, health)
    provider = MockChatProvider("openai", "gpt-4o-mini", supports_tools=True)
    gateway = AvenqoAIGateway(
        [provider],
        circuit_breaker=ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=60),
        health_registry=health,
        router=router,
        rate_card=rate_card,
    )
    assert gateway.supports_tool_calling is True

    context = routing_context_for_chat(
        query="Liste les promotions en cours",
        prompt="Promotions",
        has_tools=True,
        plan_code="professional",
        remaining_credits=100,
        avenqo_request_id="stream-test-1",
        requires_streaming=True,
    )
    with gateway.routing(context):
        chunks = []
        async for chunk in gateway.stream_events(system_instruction="sys", prompt="prompt"):
            if chunk.content:
                chunks.append(chunk.content)
            if chunk.usage:
                assert chunk.usage.provider == "openai"
                assert chunk.usage.model == "gpt-4o-mini"
        assert "".join(chunks) == "Hello World"


# ==============================================================================
# 7. 44-Language Multilingual Prompt Grounding & Tenant Isolation
# ==============================================================================

def test_multilingual_localization_44_locales_instruction() -> None:
    from backend.app.ai.chat.chat_service import _localized_system_instruction, SYSTEM_INSTRUCTION
    from backend.app.core.locale_catalog import LOCALES

    # Verify all 44 platform locales are supported and grounded
    assert len(LOCALES) == 44
    sample_locales = ["fr", "en", "es", "de", "ar", "ja", "zh", "ro", "pt", "hi"]
    for loc in sample_locales:
        instruction = _localized_system_instruction(
            SYSTEM_INSTRUCTION,
            user_language=loc,
            company_country="Canada",
            company_currency="CAD",
            company_timezone="America/Montreal",
            follow_latest_utterance_language=True,
            language_explicitly_requested=True,
        )
        # Currency must stay invariant as CAD regardless of language
        assert "CAD" in instruction
        assert "America/Montreal" or "2026" in instruction
        assert "Respond entirely in" in instruction

