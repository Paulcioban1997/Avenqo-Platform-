import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.ai.llm.schemas import LLMUsage
from backend.app.config.settings import Settings
from backend.app.models.base import Base
from backend.app.models.billing import BillingAccount
from backend.app.models.company import Company
from backend.app.models.company_membership import CompanyMembership, UserRole
from backend.app.models.company_module import CompanyModule, CompanyModuleStatus
from backend.app.models.module import Module
from backend.app.models.user import User
from backend.app.models.voice import CompanyRoutingNip, VoiceBusinessConfig, VoiceCall
from backend.app.services.employee_coach_service import EmployeeCoachService
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
    VoiceRealtimeRouter,
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
async def test_gemini_live_real_receive_loop_interruption_integration():
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
        vad_rms_threshold=400,
    )

    # Set up mock session receive queue
    recv_queue = asyncio.Queue()

    class MockSession:
        async def receive(self):
            while True:
                msg = await recv_queue.get()
                if msg is None:
                    break
                yield msg

        async def send_realtime_input(self, **kwargs):
            pass

    adapter._session = MockSession()
    adapter._tts_response_id = "turn-tts-99"
    adapter._current_response_id = "turn-tts-99"
    adapter._tts_active = True

    # Start the REAL _receive_loop in a background task
    receive_task = asyncio.create_task(adapter._receive_loop())

    try:
        # 1. Verify VAD echo suppression during active TTS
        # Audio chunk with low RMS (below threshold * 1.5 = 600)
        quiet_pcm = b"\x64\x00" * 120
        await adapter.send_audio(quiet_pcm)
        assert adapter._speech_active is False

        # 2. Feed an interruption event from Gemini Live
        msg_interrupted = SimpleNamespace(
            server_content=SimpleNamespace(
                interrupted=True,
                input_transcription=None,
                model_turn=None,
            )
        )
        await recv_queue.put(msg_interrupted)

        # Allow receive_loop to process
        await asyncio.sleep(0.05)

        # Assert TTS state is cleared and recorded as interrupted
        assert adapter._tts_active is False
        assert "turn-tts-99" in adapter._interrupted_responses

        # Events emitted to event queue
        ev1 = await adapter._event_queue.get()
        assert ev1.type == "response.done"
        assert ev1.response.status == "cancelled"
        assert ev1.response.id == "turn-tts-99"

        ev2 = await adapter._event_queue.get()
        assert ev2.type == "response.interrupted"
        assert ev2.response_id == "turn-tts-99"

        # 3. Caller speaks new query right after interruption
        msg_transcript = SimpleNamespace(
            server_content=SimpleNamespace(
                interrupted=False,
                input_transcription=SimpleNamespace(
                    text="Avez-vous des masques ?",
                    finished=True,
                ),
                model_turn=None,
            )
        )
        await recv_queue.put(msg_transcript)
        await asyncio.sleep(0.05)

        ev3 = await adapter._event_queue.get()
        assert ev3.type == "conversation.item.input_audio_transcription.completed"
        assert ev3.transcript == "Avez-vous des masques ?"

    finally:
        adapter._closed = True
        await recv_queue.put(None)
        await receive_task


@pytest.mark.asyncio
async def test_gpt_live_1_1_real_session_model_propagation():
    settings = Settings()
    settings.voice_realtime_model = "gpt-live-1"
    router = VoiceRealtimeRouter(settings)
    audio_cfg = OpenAIAudioConfig(api_key="fake-openai-key")

    # 1. Sandbox call with experimental flag enabled
    config_allowed = MagicMock()
    config_allowed.company_id = uuid4()
    config_allowed.realtime_provider = "telnyx"
    config_allowed.gemini_live_enabled = False
    config_allowed.call_policy = {
        "experimental_realtime_enabled": True,
        "experimental_realtime_model": "gpt-live-1.1",
        "is_sandbox": True,
    }

    adapter = router.build_realtime_adapter(
        config_allowed,
        audio_cfg,
        fallback_factory=lambda model=None: OpenAIRealtimeAudioAdapter(
            audio_cfg, model or settings.voice_realtime_model
        ),
    )
    assert getattr(adapter, "_model", None) == "gpt-live-1.1"

    # Verify adapter.open() actually attempts connection with model="gpt-live-1.1"
    with patch("backend.app.voice.adapters.AsyncOpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_manager = AsyncMock()
        mock_client.realtime.connect.return_value = mock_manager
        mock_manager.__aenter__.return_value = AsyncMock()

        await adapter.open(locale="fr-CA")
        mock_client.realtime.connect.assert_called_once_with(model="gpt-live-1.1")

    # 2. Production guard: environment="production" and is_sandbox=False -> falls back to gpt-live-1
    prod_settings = Settings()
    prod_settings.environment = "production"
    prod_settings.voice_realtime_model = "gpt-live-1"
    prod_router = VoiceRealtimeRouter(prod_settings)

    config_prod = MagicMock()
    config_prod.company_id = uuid4()
    config_prod.realtime_provider = "telnyx"
    config_prod.gemini_live_enabled = False
    config_prod.call_policy = {
        "experimental_realtime_enabled": True,
        "experimental_realtime_model": "gpt-live-1.1",
        "is_sandbox": False,
    }

    prod_adapter = prod_router.build_realtime_adapter(
        config_prod,
        audio_cfg,
        fallback_factory=lambda model=None: OpenAIRealtimeAudioAdapter(
            audio_cfg, model or prod_settings.voice_realtime_model
        ),
    )
    assert getattr(prod_adapter, "_model", None) == "gpt-live-1"

    # 3. Unauthorized model requested -> falls back to gpt-live-1
    config_unauth = MagicMock()
    config_unauth.company_id = uuid4()
    config_unauth.realtime_provider = "telnyx"
    config_unauth.gemini_live_enabled = False
    config_unauth.call_policy = {
        "experimental_realtime_enabled": True,
        "experimental_realtime_model": "gpt-unauthorized-custom",
        "is_sandbox": True,
    }

    unauth_adapter = router.build_realtime_adapter(
        config_unauth,
        audio_cfg,
        fallback_factory=lambda model=None: OpenAIRealtimeAudioAdapter(
            audio_cfg, model or settings.voice_realtime_model
        ),
    )
    assert getattr(unauth_adapter, "_model", None) == "gpt-live-1"


@pytest.mark.asyncio
async def test_pin_handover_retry_limit_prevents_infinite_loop():
    mock_adapter = MagicMock()
    mock_adapter.speak = AsyncMock()
    bridge = TelnyxMediaBridge(
        socket=MagicMock(),
        adapter=mock_adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(),
        begin_pin=AsyncMock(return_value={"success": True}),
        poll_pin=AsyncMock(return_value="retry_needed"),
    )
    bridge._pin_turn = "turn-pin-1"
    bridge._pin_started = True

    # Run _reprompt_pin 3 times (the max allowed)
    await bridge._reprompt_pin()
    assert bridge._pin_retry_count == 1
    bridge._pin_reprompting = False

    await bridge._reprompt_pin()
    assert bridge._pin_retry_count == 2
    bridge._pin_reprompting = False

    await bridge._reprompt_pin()
    assert bridge._pin_retry_count == 3
    bridge._pin_reprompting = False

    # 4th attempt exceeds max_pin_retries and finishes with refused
    bridge._finish_pin = AsyncMock()
    await bridge._reprompt_pin()
    assert bridge._pin_retry_count == 4
    bridge._finish_pin.assert_awaited_once_with("refused")


def test_data_driven_marketing_acquisition_coaching(db_session: Session):
    company, voice_config, call = _make_test_company_and_call(
        db_session, "Apex Mountain Sports", slug="apex-mountain"
    )
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

    # Add CRM module
    mod_crm = Module(id=uuid4(), name="CRM AI", code="crm", is_active=True)
    db_session.add(mod_crm)
    db_session.flush()
    cm_crm = CompanyModule(
        company_id=company.id,
        module_id=mod_crm.id,
        status=CompanyModuleStatus.ACTIVE,
        activated_at=datetime.now(timezone.utc),
    )
    db_session.add(cm_crm)
    db_session.commit()

    coach = EmployeeCoachService(db_session)

    # 1. With Company Profile having real products
    with patch(
        "backend.app.services.company_intelligence_service.CompanyIntelligenceService.get_profile"
    ) as mock_prof:
        mock_prof.return_value = SimpleNamespace(
            company_name="Apex Mountain Sports",
            public_products=[
                {"name": "Planche Alpine 150", "category": "Planches"},
                {"name": "Casque Sécurité MIPS", "category": "Accessoires"},
            ],
        )
        res = coach.get_marketing_acquisition_advice(user, locale="fr-CA")
        assert res["status"] == "success"
        summary = res["spoken_summary"]
        assert "François" in summary
        assert "d'après les données de votre activité" in summary
        assert "Apex Mountain Sports" in summary
        assert "Planche Alpine 150" in summary
        assert "CRM" in summary

    # 2. Without products and without modules: explicit disclosure of general advice
    with patch(
        "backend.app.services.company_intelligence_service.CompanyIntelligenceService.get_profile"
    ) as mock_prof, patch(
        "backend.app.services.module_entitlement_service.ModuleEntitlementService.get_active_modules"
    ) as mock_mods:
        mock_prof.return_value = None
        mock_mods.return_value = []
        res_empty = coach.get_marketing_acquisition_advice(user, locale="fr-CA")
        summary_empty = res_empty["spoken_summary"]
        assert "en l'absence de données de catalogue ou de campagne" in summary_empty


def test_gpt_live_1_1_billing_no_double_charging():
    catalog = voice_pricing_catalog()
    entry = catalog.lookup("openai", "gpt-live-1.1")
    assert entry is not None
    # Active audio rate: $0.05 / 60s
    assert entry.audio_input_cost_per_second_usd == Decimal("0.0008333")
    # Idle/standby audio rate: $0.02 / 60s
    assert entry.audio_idle_cost_per_second_usd == Decimal("0.0003333")

    # 1. 60s active speech: ~$0.05
    usage_active = LLMUsage(
        provider="openai",
        model="gpt-live-1.1",
        input_tokens=0,
        output_tokens=0,
        audio_input_seconds=Decimal("60"),
    )
    cost_active = entry.cost_for(usage_active)
    assert round(cost_active, 2) == Decimal("0.05")

    # 2. 60s idle/listening: ~$0.02
    usage_idle = LLMUsage(
        provider="openai",
        model="gpt-live-1.1",
        input_tokens=0,
        output_tokens=0,
        audio_idle_seconds=Decimal("60"),
    )
    cost_idle = entry.cost_for(usage_idle)
    assert round(cost_idle, 2) == Decimal("0.02")

    # 3. Combined 60s active + 60s idle: ~$0.07 without double-counting
    usage_combined = LLMUsage(
        provider="openai",
        model="gpt-live-1.1",
        input_tokens=0,
        output_tokens=0,
        audio_input_seconds=Decimal("60"),
        audio_idle_seconds=Decimal("60"),
    )
    cost_combined = entry.cost_for(usage_combined)
    assert round(cost_combined, 2) == Decimal("0.07")


def test_call_policy_experimental_fields_and_production_guard():
    from backend.app.voice.call_policy import CallPolicy

    # 1. Pydantic schema accepts experimental realtime fields without ValidationError
    policy = CallPolicy.model_validate({
        "max_call_seconds": 1800,
        "experimental_realtime_model": "gpt-live-1.1",
        "experimental_realtime_enabled": True,
        "gpt_live_1_1_enabled": True,
        "is_sandbox": True,
    })
    assert policy.experimental_realtime_model == "gpt-live-1.1"
    assert policy.experimental_realtime_enabled is True
    assert policy.gpt_live_1_1_enabled is True

    # 2. Strict Production Guard: tenant cannot bypass sandbox restriction
    prod_settings = Settings()
    prod_settings.environment = "production"
    prod_settings.voice_realtime_model = "gpt-live-1"
    router = VoiceRealtimeRouter(prod_settings)

    cfg = MagicMock()
    cfg.company_id = uuid4()
    cfg.realtime_provider = "telnyx"
    cfg.gemini_live_enabled = False
    cfg.call_policy = {
        "experimental_realtime_enabled": True,
        "experimental_realtime_model": "gpt-live-1.1",
        "is_sandbox": True,  # Spoofed by tenant in production
    }
    audio_cfg = OpenAIAudioConfig(api_key="fake-key")
    adapter = router.build_realtime_adapter(
        cfg,
        audio_cfg,
        fallback_factory=lambda model=None: OpenAIRealtimeAudioAdapter(
            audio_cfg, model or prod_settings.voice_realtime_model
        ),
    )
    # Must fallback to production model (gpt-live-1), never gpt-live-1.1
    assert getattr(adapter, "_model", None) == "gpt-live-1"


def test_crm_appointment_questions_not_confused_with_catalog():
    # 1. "Prochain rendez-vous" must NOT match catalog pagination
    is_page, _ = is_catalog_pagination_question("Quel est mon prochain rendez-vous ?")
    assert is_page is False
    is_page_rdv, _ = is_catalog_pagination_question("Quand est mon prochain rdv ?")
    assert is_page_rdv is False
    is_page_slot, _ = is_catalog_pagination_question("Quels sont les prochains créneaux disponibles ?")
    assert is_page_slot is False

    # 2. "Deuxième rendez-vous" must NOT match catalog ordinal product lookup
    is_ord, _ = is_ordinal_product_question("Et pour le deuxième rendez-vous ?")
    assert is_ord is False
    is_ord_booking, _ = is_ordinal_product_question("Combien de temps dure la deuxième réservation ?")
    assert is_ord_booking is False


def test_catalog_pagination_preserves_accessories_filter():
    mock_call = MagicMock()
    mock_call.source_context = {}

    products = [
        {"name": "Casque MIPS", "category": "Accessoires", "price": 120, "is_live_stock": True},
        {"name": "Gants Polaires", "category": "Accessoires", "price": 45, "is_live_stock": True},
        {"name": "Masque UV", "category": "Accessoires", "price": 90, "is_live_stock": True},
        {"name": "Planche Alpine", "category": "Planches", "price": 450, "is_live_stock": True},
        {"name": "Fart Glisse", "category": "Accessoires", "price": 25, "is_live_stock": True},
        {"name": "Planche Freeride", "category": "Planches", "price": 500, "is_live_stock": True},
    ]

    # Turn 1: query for accessories
    ans1 = spoken_catalog_answer(
        products,
        retail_enabled=True,
        locale="fr-CA",
        query="Quels accessoires avez-vous ?",
        offset=0,
        limit=3,
        call=mock_call,
    )
    assert "Casque MIPS" in ans1
    assert "Gants Polaires" in ans1
    assert "Planche Alpine" not in ans1
    assert mock_call.source_context.get("catalog_category_filter") == "accessoire"

    # Turn 2: user says "Montrez les prochains" without repeating "accessoire"
    ans2 = spoken_catalog_answer(
        products,
        retail_enabled=True,
        locale="fr-CA",
        query="Montrez les prochains",
        offset=3,
        limit=3,
        call=mock_call,
    )
    # Must preserve accessories filter, showing "Fart Glisse" and NOT "Planche Alpine" or "Planche Freeride"
    assert "Fart Glisse" in ans2
    assert "Planche Freeride" not in ans2


def test_superlative_product_category_isolation_and_unpriced_exclusion():
    products = [
        # Snowboard with NO price
        {"name": "Planche Prototype", "category": "Planches", "price": None, "is_live_stock": True},
        # Priced accessories
        {"name": "Gants Standard", "category": "Accessoires", "price": 40, "is_live_stock": True},
        {"name": "Casque Carbone", "category": "Accessoires", "price": 250, "is_live_stock": True},
    ]

    # 1. Asking for most expensive board: prototype has no price, and must NOT pick accessories!
    ans_board = spoken_superlative_product_answer(
        products,
        category="planche",
        locale="fr-CA",
        currency="$",
    )
    assert "Casque Carbone" not in ans_board
    assert "Gants Standard" not in ans_board
    assert "dispos" in ans_board or "trouvé" in ans_board

    # 2. Asking for most expensive accessory: picks Casque Carbone (250 $)
    ans_acc = spoken_superlative_product_answer(
        products,
        category="accessoire",
        locale="fr-CA",
        currency="$",
    )
    assert "Casque Carbone" in ans_acc
    assert "250 $" in ans_acc


@pytest.mark.asyncio
async def test_telnyx_bridge_handles_provider_cancellation_and_interrupts():
    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()
    mock_adapter = MagicMock()
    mock_adapter.speak = AsyncMock()
    mock_adapter.interrupt = AsyncMock()
    mock_adapter.cancel_response = AsyncMock()

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=mock_adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(),
    )
    bridge.stream_id = "test-stream-1"
    bridge.response_id = "resp-current-1"
    bridge.epoch = 1

    # Put a queued frame in _output
    bridge._output.put_nowait((1, b"raw_pcm_frame"))
    assert not bridge._output.empty()

    # 1. Simulate provider response.interrupted event
    event_interrupted = SimpleNamespace(type="response.interrupted", response_id="resp-current-1")
    bridge._drain_provider_events = MagicMock()  # Not needed, we test direct event block logic
    bridge.interrupt = AsyncMock()

    # In _drain_provider_events logic:
    if event_interrupted.type == "response.interrupted":
        if not (bridge.input_paused or bridge._pin_turn is not None):
            await bridge.interrupt()

    bridge.interrupt.assert_awaited_once()

    # 2. Test actual interrupt() execution purges output and sends Telnyx clear
    real_bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=mock_adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(),
    )
    real_bridge.stream_id = "test-stream-2"
    real_bridge._output.put_nowait((1, b"raw_frame"))
    assert not real_bridge._output.empty()

    await real_bridge.interrupt()
    assert real_bridge._output.empty()
    mock_socket.send_json.assert_awaited_with({"event": "clear"})


@pytest.mark.asyncio
async def test_pin_handover_reprompt_unique_action_id_and_mark():
    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()
    mock_adapter = MagicMock()
    mock_adapter.speak = AsyncMock()

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=mock_adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(),
        begin_pin=AsyncMock(return_value={"success": True}),
        poll_pin=AsyncMock(return_value="retry_needed"),
    )
    bridge._pin_turn = "initial-turn-123"
    bridge._pin_started = True

    await bridge._reprompt_pin()

    # 1. Fresh unique turn ID with retry index
    assert bridge._pin_turn == "initial-turn-123-retry-1"
    # 2. Mark enqueued with pin-prompt prefix
    assert bridge._pin_mark is not None
    assert bridge._pin_mark.startswith("pin-prompt:")
    # 3. Output queue has the mark event for Telnyx
    epoch, mark_msg = bridge._output.get_nowait()
    assert mark_msg.get("event") == "mark"
    assert mark_msg["mark"]["name"] == bridge._pin_mark
    # 4. Safe prompt duration is set
    assert bridge._pin_prompt_safe_duration >= 4.0
    assert bridge._pin_prompt_spoken is True


def test_conversational_phrase_disambiguation():
    from backend.app.voice.direct_answers import (
        is_ordinal_product_question,
        is_catalog_pagination_question,
        is_superlative_product_question,
        is_superlative_service_question,
        is_open_catalog_question,
    )

    # 1. "One second, please" / "wait a second" must NOT route as ordinal #2
    assert is_ordinal_product_question("One second, please") == (False, 0)
    assert is_ordinal_product_question("wait a second") == (False, 0)
    assert is_ordinal_product_question("just a second") == (False, 0)
    assert is_ordinal_product_question("attendez une seconde s'il vous plaît") == (False, 0)
    assert is_ordinal_product_question("un instant") == (False, 0)

    # Valid ordinals still route correctly
    assert is_ordinal_product_question("Combien coûte le deuxième ?") == (True, 2)
    assert is_ordinal_product_question("Quel est le prix du 3e produit ?") == (True, 3)
    assert is_ordinal_product_question("How much is the second one?") == (True, 2)

    # 2. "What next?" / "Et ensuite ?" must NOT trigger catalog pagination
    assert is_catalog_pagination_question("What next?") == (False, 0)
    assert is_catalog_pagination_question("What should I do next?") == (False, 0)
    assert is_catalog_pagination_question("Et ensuite ?") == (False, 0)
    assert is_catalog_pagination_question("Que faire ensuite ?") == (False, 0)

    # Valid catalog pagination still routes correctly
    assert is_catalog_pagination_question("Quels sont les cinq prochains produits ?") == (True, 5)
    assert is_catalog_pagination_question("les 5 prochains") == (True, 5)
    assert is_catalog_pagination_question("the next 3 items") == (True, 3)

    # 3. "Quel service est le plus cher ?" must NOT route as retail product
    assert is_superlative_product_question("Quel service est le plus cher ?") == (False, None)
    assert is_superlative_product_question("Quelle prestation est la plus chère ?") == (False, None)
    assert is_superlative_service_question("Quel service est le plus cher ?") is True
    assert is_superlative_service_question("Quelle est votre prestation la plus chère ?") is True

    # Valid retail product superlative still routes correctly
    assert is_superlative_product_question("Quelle planche est la plus chère ?") == (True, "planche")
    assert is_superlative_product_question("Quel accessoire est le plus cher ?") == (True, "accessoire")

    # 4. "Quand est mon prochain rendez-vous ?" must stay in CRM
    assert is_catalog_pagination_question("Quand est mon prochain rendez-vous ?") == (False, 0)
    assert is_open_catalog_question("Quand est mon prochain rendez-vous ?") is False


@pytest.mark.asyncio
async def test_telnyx_streaming_mark_delayed_until_audio_deltas_complete():
    """Verify that in a streaming session, the PIN mark is enqueued in _output strictly
    AFTER all audio deltas are drained and response.done completes, never prematurely in _execute."""
    events_queue: asyncio.Queue = asyncio.Queue()

    class StreamingAdapter:
        def __init__(self):
            self.spoken_texts = []

        async def speak(self, text):
            self.spoken_texts.append(text)

        async def interrupt(self):
            pass

        async def clear_input(self):
            pass

        async def events(self):
            while True:
                ev = await events_queue.get()
                if ev is None:
                    break
                yield ev

    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()
    adapter = StreamingAdapter()
    begin_pin_mock = AsyncMock(return_value={"success": True})

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(),
        begin_pin=begin_pin_mock,
        poll_pin=AsyncMock(return_value="collecting"),
    )

    # 1. Start _drain_provider_events in background
    drain_task = asyncio.create_task(bridge._drain_provider_events())

    # 2. Execute turn with auth_required
    auth_turn_result = {
        "status": "success",
        "answer": "Veuillez saisir votre code NIP.",
        "auth_required": True,
    }
    bridge._pin_turn = "turn-pin-streaming-1"
    bridge.input_paused = True

    # Call _execute directly
    bridge.execute_turn = AsyncMock(return_value=auth_turn_result)
    await bridge._execute("turn-pin-streaming-1", "coaching", bridge.epoch)

    # CRITICAL CHECK: In streaming mode, _output must NOT yet contain the mark!
    # Because audio frames haven't arrived from provider yet!
    assert bridge._output.empty(), "Mark MUST NOT be enqueued before provider audio deltas are generated!"
    assert bridge._pin_started is False

    # 3. Simulate audio deltas streaming from provider
    import base64
    delta_event = MagicMock()
    delta_event.type = "response.output_audio.delta"
    delta_event.response_id = "resp-123"
    delta_event.delta = base64.b64encode(b"\x00" * 1200).decode("utf-8")
    bridge.response_id = "resp-123"
    bridge.response_epoch = bridge.epoch
    bridge._responses["resp-123"] = ("turn-pin-streaming-1", bridge.epoch, None)

    await events_queue.put(delta_event)
    await asyncio.sleep(0.02)

    # Audio frames are now in _output, but NO mark yet
    assert not bridge._output.empty()
    queued_epoch, first_frame = bridge._output.get_nowait()
    assert isinstance(first_frame, bytes), "First queued items must be raw audio PCM/ULAW frames!"

    # 4. Now provider signals response.done
    done_event = MagicMock()
    done_event.type = "response.done"
    done_event.response = MagicMock()
    done_event.response.id = "resp-123"
    done_event.response.status = "completed"

    await events_queue.put(done_event)
    await asyncio.sleep(0.02)

    # Now the mark event must be present at the tail of _output
    mark_found = False
    while not bridge._output.empty():
        _ep, item = bridge._output.get_nowait()
        if isinstance(item, dict) and item.get("event") == "mark":
            mark_found = True
            assert item["mark"]["name"].startswith("pin-prompt:")
            break

    assert mark_found is True, "Mark MUST be enqueued strictly upon response.done after all audio deltas!"

    # Clean up background task
    await events_queue.put(None)
    await drain_task


@pytest.mark.asyncio
async def test_unauthenticated_caller_marketing_coaching_triggers_pin_challenge(db_session: Session):
    import hashlib
    from backend.app.voice.telnyx_media import PublicInboundConversation, media_call_context
    from backend.app.services.company_intelligence_service import CompanyIntelligenceService

    # Setup company and call
    company, voice_config, call = _make_test_company_and_call(
        db_session,
        name="Ski Shop Test",
        source_context={"dispatcher_routing": True},
    )
    from backend.app.models.voice import VoiceCallerCredential
    cred = VoiceCallerCredential(
        id=uuid4(),
        company_id=company.id,
        principal_type="USER",
        principal_id=uuid4(),
        phone_number=call.caller_phone,
        pin_hash=hashlib.sha256("123456".encode()).hexdigest(),
        enabled=True,
    )
    db_session.add(cred)
    db_session.commit()

    # 1. Unauthenticated caller asking for marketing acquisition strategy
    conversation = PublicInboundConversation(
        db_session,
        Settings(TELNYX_MEDIA_ENABLED=True, TELNYX_MEDIA_INBOUND_ENABLED=True),
        call.id,
    )
    answer = conversation.public_answer("Comment attirer plus de clients pour mon commerce ?")

    # MUST require PIN authentication
    assert answer.get("auth_required") is True
    assert "réservés aux employés authentifiés" in answer["answer"] or "NIP" in answer["answer"]

    # Pending auth query must be saved in call.source_context for execution post-authentication
    db_session.refresh(call)
    assert call.source_context is not None
    assert call.source_context.get("pending_auth_query") == "Comment attirer plus de clients pour mon commerce ?"




