from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from typing import Any, AsyncIterator, cast

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.ai.chat.chat_service import ChatService
from backend.app.ai.llm.base import LLMProvider
from backend.app.ai.request_identity import resolve_ai_request_id
from backend.app.ai.llm.schemas import LLMGeneration, LLMProviderAttempt, LLMUsage
from backend.app.ai.usage.policy import AIQuotaPolicy
from backend.app.ai.usage.policy import MONTHLY_AI_REQUESTS
from backend.app.ai.usage.service import AIUsageService
from backend.app.config.settings import Settings
from backend.app.models import (
    Base,
    Company,
    TenantAICreditLedgerEntry,
    TenantAICreditReservation,
    TenantAIProviderAttempt,
)
from backend.app.voice.usage import VoiceUsageLedger, voice_pricing_catalog
from payments.plans import get_plan


def _company(db: Session, slug: str, plan: str) -> Company:
    company = Company(
        name=slug,
        slug=slug,
        email=f"{slug}@example.com",
        country="CA",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan=plan,
    )
    db.add(company)
    db.commit()
    return company


def _session(tmp_path, name: str):
    engine = create_engine(f"sqlite:///{tmp_path / name}")
    Base.metadata.create_all(engine)
    return engine, Session(engine, expire_on_commit=False)


def test_anonymous_voice_audio_persists_tenant_usage_without_fake_identity(tmp_path):
    engine, db = _session(tmp_path, "anonymous-voice-usage.db")
    try:
        company = _company(db, "anonymous-voice", "professional")
        anon_settings = Settings()
        anon_settings.auth_jwt_secret = "a" * 32
        usage_service = AIUsageService(db, AIQuotaPolicy(anon_settings))
        ledger = VoiceUsageLedger(usage_service, voice_pricing_catalog(), company_id=company.id,
            user_id=None, conversation_id=None, plan_code="professional", request_namespace=uuid4())
        event = SimpleNamespace(type="conversation.item.input_audio_transcription.completed", event_id="anonymous-stt",
            usage=SimpleNamespace(type="duration", seconds=1))
        assert ledger.record_transcription("public-turn", event, model="gpt-4o-mini-transcribe")
        assert ledger.settle("public-turn")
        rows = db.scalars(select(TenantAIProviderAttempt).where(TenantAIProviderAttempt.company_id == company.id)).all()
        assert len(rows) == 1
        assert rows[0].user_id is None and rows[0].conversation_id is None
        assert not ledger.settle("public-turn")
    finally:
        db.close(); engine.dispose()


def _response_event(event_id: str, response_id: str, status: str, *, audio_in: int, cached_audio_in: int, audio_out: int, text_in: int = 0, cached_text_in: int = 0, text_out: int = 0):
    return SimpleNamespace(
        event_id=event_id,
        response=SimpleNamespace(
            id=response_id,
            status=status,
            usage=SimpleNamespace(
                input_tokens=audio_in + text_in,
                output_tokens=audio_out + text_out,
                input_token_details=SimpleNamespace(
                    audio_tokens=audio_in,
                    text_tokens=text_in,
                    cached_tokens=cached_audio_in + cached_text_in,
                    cached_tokens_details=SimpleNamespace(
                        audio_tokens=cached_audio_in,
                        text_tokens=cached_text_in,
                    ),
                ),
                output_token_details=SimpleNamespace(
                    audio_tokens=audio_out,
                    text_tokens=text_out,
                ),
            ),
        ),
    )


def test_voice_turn_settles_actual_stt_and_realtime_usage_once_across_duplicates_and_reconnect(tmp_path) -> None:
    engine, db = _session(tmp_path, "voice-usage.db")
    try:
        company = _company(db, "voice-usage", "professional")
        user_id, conversation_id = uuid4(), uuid4()
        turn_settings = Settings()
        turn_settings.auth_jwt_secret = "a" * 32
        usage_service = AIUsageService(
            db,
            AIQuotaPolicy(turn_settings),
        )
        catalog = voice_pricing_catalog()
        ledger = VoiceUsageLedger(
            usage_service,
            catalog,
            company_id=company.id,
            user_id=user_id,
            conversation_id=conversation_id,
            plan_code="professional",
        )
        item_id = "voice-item-normal"
        assert ledger.reserve(item_id)
        transcription = SimpleNamespace(
            event_id="transcription-event-1",
            usage=SimpleNamespace(type="duration", seconds=30.0),
        )
        response = _response_event(
            "response-event-1",
            "response-normal",
            "completed",
            audio_in=600,
            cached_audio_in=100,
            audio_out=200,
            text_in=400,
            cached_text_in=100,
            text_out=100,
        )
        assert ledger.record_transcription(item_id, transcription, model="gpt-4o-mini-transcribe")
        assert not ledger.record_transcription(item_id, transcription, model="gpt-4o-mini-transcribe")
        assert ledger.record_realtime_response(item_id, response, model="gpt-realtime-2.1")
        assert not ledger.record_realtime_response(item_id, response, model="gpt-realtime-2.1")
        ledger.attribute(item_id, "retail", "retail")
        request_id = ledger.request_id_for(item_id)

        assert ledger.settle(item_id)
        assert not ledger.settle(item_id)
        reservation = db.scalar(select(TenantAICreditReservation).where(
            TenantAICreditReservation.company_id == company.id,
            TenantAICreditReservation.avenqo_request_id == request_id,
        ))
        attempts = db.scalars(select(TenantAIProviderAttempt).where(
            TenantAIProviderAttempt.company_id == company.id,
            TenantAIProviderAttempt.avenqo_request_id == request_id,
        ).order_by(TenantAIProviderAttempt.attempt_number)).all()
        settlements = db.scalars(select(TenantAICreditLedgerEntry).where(
            TenantAICreditLedgerEntry.company_id == company.id,
            TenantAICreditLedgerEntry.reference_id == request_id,
            TenantAICreditLedgerEntry.transaction_type == "ai_settlement",
        )).all()

        assert reservation is not None
        assert reservation.status == "settled"
        assert reservation.actual_credits == 114
        assert len(attempts) == 2
        assert [attempt.operation for attempt in attempts] == ["voice_stt", "voice_realtime_tts"]
        assert attempts[0].audio_input_seconds == Decimal("30")
        assert attempts[0].user_id == user_id
        assert attempts[0].conversation_id == conversation_id
        assert attempts[1].audio_input_units == Decimal("600")
        assert attempts[1].cached_audio_input_units == Decimal("100")
        assert attempts[1].audio_output_units == Decimal("200")
        assert attempts[1].agent_id == "retail" and attempts[1].module_id == "retail"
        assert attempts[1].pricing_version == "2026-10-01"
        assert len(settlements) == 1

        reconnected = VoiceUsageLedger(
            usage_service,
            catalog,
            company_id=company.id,
            user_id=user_id,
            conversation_id=conversation_id,
            plan_code="professional",
        )
        assert not reconnected.reserve(item_id)
        assert not reconnected.record_realtime_response(item_id, response, model="gpt-realtime-2.1")
        assert db.scalar(select(TenantAIProviderAttempt.id).where(
            TenantAIProviderAttempt.company_id == company.id,
            TenantAIProviderAttempt.avenqo_request_id == request_id,
        ).limit(2).offset(1)) is not None
        assert get_plan("base").monthly_ai_credits == 6_500
        assert get_plan("professional").monthly_ai_credits == 25_000
    finally:
        db.close()
        engine.dispose()


def test_voice_failure_retry_and_barge_in_record_only_reported_usage_once(tmp_path) -> None:
    engine, db = _session(tmp_path, "voice-retry-usage.db")
    try:
        company = _company(db, "voice-retry", "base")
        retry_settings = Settings()
        retry_settings.auth_jwt_secret = "b" * 32
        usage_service = AIUsageService(
            db,
            AIQuotaPolicy(retry_settings),
        )
        ledger = VoiceUsageLedger(
            usage_service,
            voice_pricing_catalog(),
            company_id=company.id,
            user_id=uuid4(),
            conversation_id=uuid4(),
            plan_code="base",
        )
        item_id = "voice-item-barge-in"
        assert ledger.reserve(item_id)
        assert ledger.record_provider_failure(
            item_id,
            model="gpt-realtime-2.1",
            operation="voice_realtime_connect",
            event_id="connect-timeout",
            failure_category="timeout",
        )
        cancelled = _response_event(
            "cancelled-response-event",
            "response-cancelled",
            "cancelled",
            audio_in=0,
            cached_audio_in=0,
            audio_out=40,
            text_out=5,
        )
        retry = _response_event(
            "retry-response-event",
            "response-retry",
            "completed",
            audio_in=0,
            cached_audio_in=0,
            audio_out=20,
            text_out=2,
        )
        assert ledger.record_realtime_response(item_id, cancelled, model="gpt-realtime-2.1")
        assert not ledger.record_realtime_response(item_id, cancelled, model="gpt-realtime-2.1")
        assert ledger.record_realtime_response(item_id, retry, model="gpt-realtime-2.1")
        request_id = ledger.request_id_for(item_id)

        assert ledger.settle(item_id)
        reservation = db.scalar(select(TenantAICreditReservation).where(
            TenantAICreditReservation.company_id == company.id,
            TenantAICreditReservation.avenqo_request_id == request_id,
        ))
        attempts = db.scalars(select(TenantAIProviderAttempt).where(
            TenantAIProviderAttempt.company_id == company.id,
            TenantAIProviderAttempt.avenqo_request_id == request_id,
        ).order_by(TenantAIProviderAttempt.attempt_number)).all()
        settlements = db.scalars(select(TenantAICreditLedgerEntry).where(
            TenantAICreditLedgerEntry.company_id == company.id,
            TenantAICreditLedgerEntry.reference_id == request_id,
            TenantAICreditLedgerEntry.transaction_type == "ai_settlement",
        )).all()

        assert reservation is not None
        assert reservation.status == "settled"
        assert reservation.actual_credits == 14
        assert len(attempts) == 3
        assert attempts[0].success is False and attempts[0].provider_cost_usd == 0
        assert attempts[1].request_status == "cancelled"
        assert attempts[1].audio_output_units == Decimal("40")
        assert attempts[1].provider_cost_usd == Decimal("0.00268")
        assert attempts[2].request_status == "completed"
        assert attempts[2].audio_output_units == Decimal("20")
        assert len(settlements) == 1
    finally:
        db.close()
        engine.dispose()


def test_central_chat_reuses_voice_reservation_and_voice_ledger_settles_all_providers_once(tmp_path) -> None:
    engine, db = _session(tmp_path, "voice-central-shared-usage.db")
    try:
        company = _company(db, "voice-central-shared", "professional")
        user_id, conversation_id = uuid4(), uuid4()
        request_id = "central-voice-turn-request"
        central_settings = Settings()
        central_settings.auth_jwt_secret = "d" * 32
        central_settings.ai_quota_limits = {"professional": {MONTHLY_AI_REQUESTS: 1}}
        usage_service = AIUsageService(
            db,
            AIQuotaPolicy(central_settings),
        )
        ledger = VoiceUsageLedger(
            usage_service,
            voice_pricing_catalog(),
            company_id=company.id,
            user_id=user_id,
            conversation_id=conversation_id,
            plan_code="professional",
        )
        item_id = "central-voice-turn"
        stable_request_id = ledger.request_id_for(item_id)
        assert stable_request_id == resolve_ai_request_id(
            item_id,
            tenant_id=company.id,
            user_id=user_id,
            conversation_id=conversation_id,
        )
        assert ledger.reserve(item_id)
        provider_usage = LLMUsage(
            provider="openai",
            model="gpt-4o-mini",
            input_tokens=1_000,
            output_tokens=100,
            avenqo_request_id=stable_request_id,
            tenant_id=str(company.id),
            user_id=str(user_id),
            conversation_id=str(conversation_id),
            agent_id="retail",
            module_id="retail",
            idempotency_key=stable_request_id,
        )
        provider_attempt = LLMProviderAttempt(
            provider="openai",
            model="gpt-4o-mini",
            operation="generate",
            attempt_number=1,
            success=True,
            latency_ms=3,
            usage=provider_usage,
            provider_cost_usd=Decimal("0.00021"),
            input_cost_per_million_usd=Decimal("0.15"),
            output_cost_per_million_usd=Decimal("0.60"),
            pricing_version="2026-10-01",
            pricing_source="openai-api-pricing",
            pricing_effective_from="2026-10-01",
        )

        class Provider(LLMProvider):
            name = "openai"

            async def generate(self, *, system_instruction: str, prompt: str) -> LLMGeneration:
                return LLMGeneration(
                    content="Central answer",
                    provider="openai",
                    model="gpt-4o-mini",
                    token_usage=provider_usage.as_token_usage(),
                    attempts=(provider_attempt,),
                )

            async def stream(self, *, system_instruction: str, prompt: str) -> AsyncIterator[str]:
                async def _gen():
                    yield "Central answer"
                return _gen()

        class Conversations:
            def ensure_locale(self, *_args, **_kwargs):
                return "fr"

            def messages(self, *_args, **_kwargs):
                return ()

            def add_message(self, _tenant_id, _conversation_id, role, content, *args):
                return SimpleNamespace(id=uuid4(), role=role, content=content)

            def add_sources(self, *_args, **_kwargs):
                return None

        class Retrieval:
            def retrieve_context(self, *_args, **_kwargs):
                return []

        chat = ChatService(
            cast(Any, Conversations()),
            cast(Any, Retrieval()),
            Provider(),
            usage_service=usage_service,
        )
        central_attempts: list[LLMProviderAttempt] = []
        classification = asyncio.run(chat.classify_intent(
            "Classify the request",
            "Summarize sales",
            tenant_id=company.id,
            plan_code="professional",
            request_id=stable_request_id,
            allow_existing_reservation=True,
            attempt_sink=central_attempts,
        ))
        assert classification == "Central answer"
        assert len(central_attempts) == 1
        assert not db.scalars(select(TenantAICreditLedgerEntry).where(
            TenantAICreditLedgerEntry.company_id == company.id,
            TenantAICreditLedgerEntry.reference_id == stable_request_id,
            TenantAICreditLedgerEntry.transaction_type == "ai_settlement",
        )).all()
        message, _ = asyncio.run(chat.send(
            company.id,
            user_id,
            conversation_id,
            "Summarize sales",
            plan_code="professional",
            request_id=stable_request_id,
            allowed_tool_names=frozenset(),
            retrieve_tenant_data=False,
            allow_existing_reservation=True,
            attempt_sink=central_attempts,
        ))
        assert message.content == "Central answer"
        assert len(central_attempts) == 2
        central_reservation = db.scalar(select(TenantAICreditReservation).where(
            TenantAICreditReservation.company_id == company.id,
            TenantAICreditReservation.avenqo_request_id == stable_request_id,
        ))
        assert central_reservation is not None and central_reservation.status == "reserved"
        assert not db.scalars(select(TenantAICreditLedgerEntry).where(
            TenantAICreditLedgerEntry.company_id == company.id,
            TenantAICreditLedgerEntry.reference_id == stable_request_id,
            TenantAICreditLedgerEntry.transaction_type == "ai_settlement",
        )).all()

        ledger.add_attempts(item_id, central_attempts)
        transcription = SimpleNamespace(
            event_id="central-stt-event",
            usage=SimpleNamespace(type="duration", seconds=30.0),
        )
        ledger.record_transcription(item_id, transcription, model="gpt-4o-mini-transcribe")
        response = _response_event(
            "central-realtime-event",
            "central-response",
            "completed",
            audio_in=600,
            cached_audio_in=100,
            audio_out=200,
            text_in=400,
            cached_text_in=100,
            text_out=100,
        )
        ledger.record_realtime_response(item_id, response, model="gpt-realtime-2.1")
        assert ledger.settle(item_id)

        attempts = db.scalars(select(TenantAIProviderAttempt).where(
            TenantAIProviderAttempt.company_id == company.id,
            TenantAIProviderAttempt.avenqo_request_id == stable_request_id,
        )).all()
        settlements = db.scalars(select(TenantAICreditLedgerEntry).where(
            TenantAICreditLedgerEntry.company_id == company.id,
            TenantAICreditLedgerEntry.reference_id == stable_request_id,
            TenantAICreditLedgerEntry.transaction_type == "ai_settlement",
        )).all()
        assert len(attempts) == 4
        assert {attempt.operation for attempt in attempts} == {
            "generate", "voice_stt", "voice_realtime_tts",
        }
        assert sum(attempt.operation == "generate" for attempt in attempts) == 2
        assert len(settlements) == 1
    finally:
        db.close()
        engine.dispose()
