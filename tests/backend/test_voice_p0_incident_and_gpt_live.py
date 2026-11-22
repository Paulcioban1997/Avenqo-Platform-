import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config.settings import Settings
from backend.app.models.base import Base
from backend.app.models.billing import BillingAccount
from backend.app.models.company import Company
from backend.app.models.company_membership import CompanyMembership, UserRole
from backend.app.models.company_module import CompanyModule, CompanyModuleStatus
from backend.app.models.module import Module
from backend.app.models.user import User
from backend.app.models.voice import CompanyRoutingNip, VoiceBusinessConfig, VoiceCall
from backend.app.voice.adapters import OpenAIAudioConfig, OpenAIRealtimeAudioAdapter
from backend.app.voice.auth import VoiceCallerAuth
from backend.app.voice.direct_answers import (
    is_catalog_pagination_question,
    is_marketing_acquisition_question,
    is_ordinal_product_question,
    is_superlative_product_question,
    resolve_direct_voice_answer,
    spoken_catalog_answer,
    spoken_ordinal_product_answer,
    spoken_superlative_product_answer,
)
from backend.app.voice.realtime_provider import (
    GeminiLiveRealtimeAudioAdapter,
    NaturalInterruptionManager,
    build_personality_system_prompt,
)
from backend.app.voice.telnyx_media import PublicInboundConversation, TelnyxMediaBridge
from backend.app.voice.usage import voice_pricing_catalog


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def _make_test_company_and_call(
    db_session: Session,
    name="Entreprise Test",
    slug=None,
    email=None,
    status="in_progress",
    source_context=None,
    verification_attempts=0,
):
    uid = uuid4().hex[:8]
    company = Company(
        id=uuid4(),
        name=name,
        slug=slug or f"company-{uid}",
        email=email or f"contact-{uid}@example.com",
        country="CA",
        timezone="America/Toronto",
        industry="retail",
        subscription_plan="enterprise",
    )
    db_session.add(company)
    mod_voice = db_session.query(Module).filter_by(code="voice").first()
    if not mod_voice:
        mod_voice = Module(id=uuid4(), name="Voice AI", code="voice", is_active=True)
        db_session.add(mod_voice)
        db_session.flush()
    now = datetime.now(timezone.utc)
    cm_voice = CompanyModule(company_id=company.id, module_id=mod_voice.id, status=CompanyModuleStatus.ACTIVE, activated_at=now)
    db_session.add(cm_voice)
    billing = BillingAccount(id=uuid4(), company_id=company.id, status="active", plan_code="enterprise")
    db_session.add(billing)
    nip = CompanyRoutingNip(
        id=uuid4(),
        company_id=company.id,
        routing_code="12345",
        routing_code_hash=f"hash_{uid}",
        status="ACTIVE",
    )
    db_session.add(nip)
    voice_config = VoiceBusinessConfig(
        id=uuid4(),
        company_id=company.id,
        business_name=name,
        preferred_language="fr-CA",
        greeting_message="Bonjour! Bienvenue.",
        voice_api_key_hash="dummy_hash",
        voice_api_key_last4="1234",
        enabled=True,
    )
    db_session.add(voice_config)
    call = VoiceCall(
        id=uuid4(),
        company_id=company.id,
        config_id=voice_config.id,
        telnyx_call_control_id="v-call-ctl-123",
        caller_phone="+15145551234",
        status=status,
        verification_attempts=verification_attempts,
        source_context=source_context,
    )
    db_session.add(call)
    db_session.commit()
    return company, voice_config, call


def test_verify_gather_empty_pin_does_not_count_attempts(db_session: Session):
    company, voice_config, call = _make_test_company_and_call(
        db_session, "Entreprise Test"
    )

    settings = Settings()
    auth_ctrl = VoiceCallerAuth(db_session, settings)

    # Calling verify_gather with empty digits should not increment attempts
    res = auth_ctrl.verify_gather(call, "")
    assert res["authenticated"] is False
    assert res["is_empty"] is True
    assert res["reason"] == "empty_pin"
    assert call.verification_attempts == 0

    # Repeating 6 times should not lock out
    for _ in range(6):
        res = auth_ctrl.verify_gather(call, "   ")
        assert res["is_empty"] is True
        assert res["authenticated"] is False
        assert call.verification_attempts == 0


def test_public_inbound_conversation_pin_retry_state(db_session: Session):
    company, voice_config, call = _make_test_company_and_call(
        db_session,
        "Entreprise Test",
        slug="entreprise-test-2",
        source_context={"pin_gather_status": "retry_needed", "dispatcher_routing": True},
    )

    settings = Settings()
    settings.telnyx_media_enabled = True
    settings.telnyx_media_inbound_enabled = True
    telnyx_mock = MagicMock()
    conv = PublicInboundConversation(db_session, settings, call.id, telnyx_mock)

    assert conv.pin_state() == "retry_needed"

    conv.reset_pin_retry()
    db_session.refresh(call)
    assert (call.source_context or {}).get("pin_gather_status") == "pending_retry"
    assert conv.pin_state() == "refused"  # Pending retry is not final refused/auth


def test_spoken_catalog_pagination_and_superlative():
    products = [
        {"name": "Planche Alpine 150", "price": 450, "currency": "CAD", "category": "planche"},
        {"name": "Fixations Pro", "price": 180, "currency": "CAD", "category": "accessoire"},
        {"name": "Planche Apex Summit Carbon", "price": 890, "currency": "CAD", "category": "planche"},
        {"name": "Casque Sécurité MIPS", "price": 120, "currency": "CAD", "category": "accessoire"},
        {"name": "Gants Hiver GoreTex", "price": 95, "currency": "CAD", "category": "accessoire"},
        {"name": "Planche Freestyle 145", "price": 420, "currency": "CAD", "category": "planche"},
        {"name": "Masque Neige Prizm", "price": 160, "currency": "CAD", "category": "accessoire"},
    ]

    mock_call = MagicMock()
    mock_call.source_context = {}

    # Initial 3 items
    ans1 = spoken_catalog_answer(products, retail_enabled=True, locale="fr-CA", offset=0, limit=3, call=mock_call)
    assert "Planche Alpine 150" in ans1
    assert "Planche Apex Summit Carbon" in ans1
    presented = mock_call.source_context.get("presented_catalog_products")
    assert len(presented) == 3
    assert mock_call.source_context.get("catalog_pagination_offset") == 3

    # Ordinal query: "Combien coûte le deuxième ?"
    is_ord, ord_idx = is_ordinal_product_question("Combien coûte le deuxième ?")
    assert is_ord is True
    assert ord_idx == 2
    ord_ans = spoken_ordinal_product_answer(presented, ord_idx, locale="fr-CA")
    assert "Fixations Pro" in ord_ans
    assert "180 $" in ord_ans

    # Superlative query: "Quelle planche est la plus chère ?"
    is_sup, sup_cat = is_superlative_product_question("Quelle planche est la plus chère ?")
    assert is_sup is True
    assert sup_cat == "planche"
    sup_ans = spoken_superlative_product_answer(products, sup_cat, locale="fr-CA")
    assert "Planche Apex Summit Carbon" in sup_ans
    assert "890 $" in sup_ans

    # Pagination: "Quels sont les cinq prochains produits ?"
    is_page, req_count = is_catalog_pagination_question("Quels sont les cinq prochains produits ?")
    assert is_page is True
    assert req_count == 5
    ans_page = spoken_catalog_answer(products, retail_enabled=True, locale="fr-CA", offset=3, limit=req_count, call=mock_call)
    assert "Casque Sécurité MIPS" in ans_page
    assert "Gants Hiver GoreTex" in ans_page
    assert "Masque Neige Prizm" in ans_page
    assert mock_call.source_context.get("catalog_pagination_offset") == 7


def test_marketing_acquisition_coaching(db_session: Session):
    uid = uuid4().hex[:8]
    company = Company(
        id=uuid4(),
        name="Boutique Plein Air",
        slug="boutique-plein-air",
        email=f"contact-{uid}@example.com",
        country="CA",
        timezone="America/Toronto",
        industry="retail",
        subscription_plan="starter",
    )
    db_session.add(company)
    user = User(
        id=uuid4(),
        company_id=company.id,
        email="francois@example.com",
        password_hash="mock_hash_123",
        first_name="François",
        last_name="Tremblay",
        role=UserRole.OWNER,
        is_active=True,
    )
    db_session.add(user)
    membership = CompanyMembership(
        id=uuid4(),
        company_id=company.id,
        user_id=user.id,
        role=UserRole.OWNER,
        is_active=True,
    )
    db_session.add(membership)
    db_session.commit()

    # Question from authenticated staff
    q = "Comment attirer plus de clients pour la nouvelle saison ?"
    assert is_marketing_acquisition_question(q) is True

    ans = resolve_direct_voice_answer(
        db_session,
        company_id=company.id,
        transcript=q,
        authenticated_staff=True,
        staff_role="owner",
        locale="fr-CA",
        user_id=user.id,
    )
    assert ans is not None
    assert "François" in ans
    assert "attirer plus de clients" in ans.lower()
    # Ensure it's not giving internal HR bottleneck advice
    assert "goulots d'étranglement de l'équipe" not in ans

    # Question from unauthenticated public caller should require PIN
    public_ans = resolve_direct_voice_answer(
        db_session,
        company_id=company.id,
        transcript=q,
        authenticated_staff=False,
        staff_role=None,
        locale="fr-CA",
        user_id=None,
    )
    assert public_ans is not None
    assert "NIP" in public_ans


def test_public_receptionist_prompt_strict_mode():
    prompt = build_personality_system_prompt(
        company_name="Produits Héros",
        locale="fr-CA",
        is_authenticated_staff=False,
        staff_name=None,
        staff_role=None,
    )
    assert "PUBLIC CUSTOMER SERVICE RECEPTIONIST MODE" in prompt
    assert "Bonjour François" in prompt  # Mentioned in rule: Never greet them by an employee or owner name
    assert "Never assume they are an employee or owner" in prompt


@pytest.mark.asyncio
async def test_gemini_live_interruption_event_dispatch():
    config = MagicMock()
    config.company_name = "Produits Héros"
    config.custom_pronunciation = None
    config.tts_voice = "Puck"
    config.delivery_style = "natural"
    config.stt_model = "default"
    config.input_noise_reduction = "off"
    config.speech_speed = 1.0

    audio_cfg = OpenAIAudioConfig(api_key="fake-key")
    settings = MagicMock()
    settings.google_ai_api_key = "fake-key"
    adapter = GeminiLiveRealtimeAudioAdapter(
        settings=settings,
        config=config,
        audio_config=audio_cfg,
        model="gemini-3.8-live",
        company_name="Produits Héros",
    )

    # Set up active TTS response
    adapter._tts_response_id = "test-response-1"
    adapter._current_response_id = "test-response-1"
    adapter._tts_active = True
    adapter._session = MagicMock()

    # Simulate receiving interrupted=True
    msg = SimpleNamespace(
        server_content=SimpleNamespace(
            interrupted=True,
            input_transcription=None,
            model_turn=None,
            turn_complete=None,
        )
    )

    async def fake_receive():
        yield msg

    adapter._session.receive = fake_receive

    # Run one pass of _receive_loop logic
    async for message in adapter._session.receive():
        server_content = message.server_content
        if server_content.interrupted:
            if adapter._tts_response_id is not None:
                adapter._interrupted_responses.add(adapter._tts_response_id)
            interrupted_resp = adapter._current_response_id or adapter._tts_response_id
            adapter._tts_active = False
            adapter._tts_response_id = None
            adapter._current_response_id = None
            if interrupted_resp is not None:
                await adapter._event_queue.put(
                    SimpleNamespace(
                        type="response.done",
                        response=SimpleNamespace(
                            id=interrupted_resp,
                            status="cancelled",
                            usage=None,
                        ),
                    )
                )
                await adapter._event_queue.put(
                    SimpleNamespace(
                        type="response.interrupted",
                        response_id=interrupted_resp,
                    )
                )

    assert adapter._tts_active is False
    assert "test-response-1" in adapter._interrupted_responses

    event1 = await adapter._event_queue.get()
    assert event1.type == "response.done"
    assert event1.response.status == "cancelled"

    event2 = await adapter._event_queue.get()
    assert event2.type == "response.interrupted"
    assert event2.response_id == "test-response-1"


def test_gpt_live_1_1_pricing_catalog():
    catalog = voice_pricing_catalog()
    entry = catalog.lookup("openai", "gpt-live-1.1")
    assert entry is not None
    assert entry.input_cost_per_million_usd == Decimal("2.50")
    assert entry.output_cost_per_million_usd == Decimal("10.00")

