from __future__ import annotations

import asyncio
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from time import time
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from backend.app.config.settings import Settings
from backend.app.models import (
    Base,
    BillingAccount,
    CRMActivity,
    Company,
    CompanyMembership,
    CompanyModule,
    CompanyModuleStatus,
    CRMAppointment,
    CRMClient,
    CRMCommunication,
    CRMNote,
    Module,
    VoiceBusinessConfig,
    VoiceCall,
    User,
    UserRole,
    VoicePhoneNumber,
)
from backend.app.routers.voice import _verify_telnyx_signature, get_voice_status, voice_business_metrics
from backend.app.schemas.voice import VoiceConfigRequest, VoiceToolRequest
from backend.app.voice.service import VoiceOrchestrator, _api_key_hash
from shared.ai_engine.contracts import TenantContext
from backend.app.core.locale_catalog import BY_LOCALE, resolve_locale


class _FakeVoiceProvider:
    async def validate_agent(self, agent_id: str) -> None:
        if agent_id != "agent-test":
            raise ValueError("unknown agent")

    def inbound_target(self, config: VoiceBusinessConfig) -> str:
        return config.retell_sip_uri

    def agent_instructions(self, config: VoiceBusinessConfig) -> str:
        return f"Bonjour, {config.business_name}, assistant virtuel, cet appel peut être enregistré."


class _FakeTelnyx:
    def __init__(self) -> None:
        self.transfers: list[tuple[str, str]] = []
        self.messages: list[tuple[str, str]] = []

    async def transfer_call(self, call_control_id: str, destination: str, caller_id: str | None = None) -> None:
        self.transfers.append((call_control_id, destination))

    async def hangup(self, call_control_id: str) -> None:
        return None

    async def send_sms(self, *, from_number: str, to_number: str, text: str) -> str:
        self.messages.append((to_number, text))
        return "msg-test"


def test_voice_configuration_accepts_all_canonical_application_locales():
    base = {
        "business_name": "Test business",
        "services": [{"name": "Consultation", "duration_minutes": 30}],
        "transfer_phone": "+15145550199",
        "telnyx_phone_number": "+15145550100",
        "retell_agent_id": "agent-test",
        "retell_sip_uri": "sip:agent-test@sip.retell.example",
    }
    for locale in BY_LOCALE:
        request = VoiceConfigRequest(**base, preferred_language=locale)
        assert request.preferred_language == resolve_locale(locale)

    with pytest.raises(ValueError, match="existing Avenqo locale"):
        VoiceConfigRequest(**base, preferred_language="xx-INVALID")


def test_voice_config_cannot_claim_number_owned_by_another_tenant(tmp_path):
    engine, session, company, config, _, _ = _voice_database(tmp_path)
    try:
        other_company = Company(
            name="Other Voice Tenant",
            slug="other-voice-tenant",
            email="other-voice@example.com",
            country="CA",
            timezone="America/Toronto",
            industry="Retail",
            subscription_plan="professional",
        )
        session.add(other_company)
        session.flush()
        module = session.query(Module).filter_by(code="voice").one()
        session.add(CompanyModule(
            company_id=other_company.id,
            module_id=module.id,
            activated_at=datetime.now(timezone.utc),
            status=CompanyModuleStatus.ACTIVE,
        ))
        session.add(VoicePhoneNumber(
            company_id=other_company.id,
            phone_number="+14165550998",
            country_code="CA",
            provider="telnyx",
            provider_number_id="owned-by-other-tenant",
            number_type="local",
            capabilities=["voice"],
            status="ACTIVE",
        ))
        session.commit()
        service = VoiceOrchestrator(
            session,
            Settings(TELNYX_API_KEY="configured"),
            provider=_FakeVoiceProvider(),
            telnyx=_FakeTelnyx(),
        )

        with pytest.raises(PermissionError, match="another tenant"):
            asyncio.run(service.upsert_config(TenantContext(company.id), {
                "business_name": config.business_name,
                "timezone_name": config.timezone_name,
                "opening_hours": config.opening_hours,
                "services": config.services,
                "transfer_phone": config.transfer_phone,
                "telnyx_phone_number": "+14165550998",
                "preferred_language": config.preferred_language,
                "retell_agent_id": config.retell_agent_id,
                "retell_sip_uri": config.retell_sip_uri,
                "enabled": False,
            }))
        assert config.telnyx_phone_number == "+15145550100"
    finally:
        session.close()
        engine.dispose()


def test_voice_status_is_visible_before_entitlement_or_provider_provisioning(tmp_path):
    engine, session, company, config, _, _ = _voice_database(tmp_path)
    try:
        snapshot = SimpleNamespace(
            active_source_provider=None,
            active_source_name=None,
            active_source_type=None,
            active_source_selected=False,
            active_source_last_updated_at=None,
            active_source_last_event_received_at=None,
            status="no_data",
            prepared=(),
            retail_summaries=(),
        )

        class _Analytics:
            def load(self, _tenant):
                return snapshot

        identity = SimpleNamespace(user=SimpleNamespace(id=uuid4(), company_id=company.id, company=company))
        status = get_voice_status(identity, session, Settings(), _Analytics())

        assert status["voice_status"] == "ENABLED"
        assert status["module_entitled"] is True
        assert status["telnyx_status"] == "NOT_CONFIGURED"
        assert status["retell_status"] == "NOT_CONFIGURED"
        assert status["number_status"] == "READY_FOR_OWNER_ACTION"
        assert "telnyx_api_key" not in str(status)
        assert "voice_api_key_hash" not in str(status)
    finally:
        session.close()
        engine.dispose()


def _voice_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'voice-agent.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    company = Company(
        name="Voice Test Shop",
        slug="voice-test-shop",
        email="voice-test@example.com",
        country="CA",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
        currency_code="CAD",
    )
    module = Module(name="Voice AI", code="voice", is_active=True)
    session.add_all([company, module])
    session.flush()
    session.add(CompanyModule(
        company_id=company.id,
        module_id=module.id,
        activated_at=datetime.now(timezone.utc),
        status=CompanyModuleStatus.ACTIVE,
    ))
    api_key = "avqv_test_key_do_not_use_outside_tests"
    config = VoiceBusinessConfig(
        company_id=company.id,
        business_name=company.name,
        timezone_name="America/Toronto",
        opening_hours={day: {"open": "00:00", "close": "23:59"} for day in (
            "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
        )},
        services=[{"name": "Consultation", "duration_minutes": 30, "price": 80, "currency": "CAD"}],
        transfer_phone="+15145550199",
        telnyx_phone_number="+15145550100",
        preferred_language="fr",
        greeting_message="Bonjour, Voice Test Shop, assistant virtuel, cet appel peut être enregistré.",
        retell_agent_id="agent-test",
        retell_sip_uri="sip:agent-test@sip.retell.example",
        voice_api_key_hash=_api_key_hash(api_key),
        voice_api_key_last4=api_key[-4:],
        enabled=True,
    )
    session.add(config)
    session.commit()
    service = VoiceOrchestrator(
        session,
        Settings(),
        provider=_FakeVoiceProvider(),
        telnyx=_FakeTelnyx(),
    )
    return engine, session, company, config, api_key, service


def test_voice_api_key_is_tenant_scoped_and_not_stored_in_plaintext(tmp_path) -> None:
    engine, session, _, config, key, service = _voice_database(tmp_path)
    try:
        assert service.config_from_api_key(key).id == config.id
        assert service.config_from_api_key("avqv_other_tenant_key") is None
        assert key not in config.voice_api_key_hash
        assert config.voice_api_key_hash == hashlib.sha256(key.encode()).hexdigest()
    finally:
        session.close()
        engine.dispose()


def test_caller_id_alone_stays_unknown_and_cannot_reschedule_or_cancel(tmp_path):
    engine, session, company, config, _, orchestrator = _voice_database(tmp_path)
    try:
        call = orchestrator.record_inbound(config, {
            "call_control_id": "spoofable-call-id",
            "from": "+15145550123",
        })
        assert call.caller_type == "UNKNOWN"
        result = asyncio.run(orchestrator._dispatch_tool(
            config,
            call,
            "cancel_appointment",
            {"appointment_id": str(uuid4()), "confirmed": True},
        ))
        assert result == {"success": False, "error": "caller_verification_required"}
    finally:
        session.close()
        engine.dispose()


def test_voice_owner_requires_sms_otp_before_privileged_caller_type(tmp_path):
    engine, session, company, config, _, orchestrator = _voice_database(tmp_path)
    try:
        owner = User(
            company_id=company.id,
            first_name="Owner",
            last_name="Example",
            email="owner@example.com",
            phone="+15145550123",
            password_hash="test-hash",
            role=UserRole.OWNER,
            is_active=True,
        )
        session.add(owner)
        session.flush()
        session.add(CompanyMembership(
            company_id=company.id,
            user_id=owner.id,
            role=UserRole.OWNER,
            is_active=True,
        ))
        session.commit()
        call = orchestrator.record_inbound(config, {
            "call_control_id": "owner-otp-call",
            "from": owner.phone,
        })

        assert call.caller_type == "UNKNOWN"
        sent = asyncio.run(orchestrator._request_caller_verification(config, call))
        sms_text = orchestrator.telnyx.messages[-1][1]
        code = sms_text.split(": ", 1)[1].split(".", 1)[0]
        assert sent == {"success": True, "verification_sent": True}
        assert owner.phone in orchestrator.telnyx.messages[-1]
        assert call.verification_code_hash is not None
        assert code not in call.verification_code_hash

        verified = orchestrator._verify_caller(config, call, code)

        assert verified == {"success": True, "verified": True, "caller_type": "OWNER"}
        assert call.authenticated_user_id == owner.id
        assert call.caller_verified_at is not None
        assert call.verification_code_hash is None
    finally:
        session.close()
        engine.dispose()


def test_voice_client_sms_verification_creates_client_scoped_identity(tmp_path):
    engine, session, company, config, _, orchestrator = _voice_database(tmp_path)
    try:
        client = CRMClient(
            company_id=company.id,
            first_name="Client",
            last_name="Example",
            email="client@example.com",
            phone="+15145550124",
        )
        session.add(client)
        session.commit()
        call = orchestrator.record_inbound(config, {
            "call_control_id": "verified-client-call",
            "from": client.phone,
        })

        sent = asyncio.run(orchestrator._request_caller_verification(config, call))
        code = orchestrator.telnyx.messages[-1][1].split(": ", 1)[1].split(".", 1)[0]
        verified = orchestrator._verify_caller(config, call, code)

        assert sent == {"success": True, "verification_sent": True}
        assert verified == {"success": True, "verified": True, "caller_type": "CLIENT"}
        assert call.verified_client_id == client.id
        assert call.authenticated_user_id is None
    finally:
        session.close()
        engine.dispose()


def test_verified_client_cannot_reschedule_or_cancel_another_clients_appointment(tmp_path):
    engine, session, company, config, _, orchestrator = _voice_database(tmp_path)
    try:
        verified_client = CRMClient(
            company_id=company.id,
            first_name="Verified",
            last_name="Client",
            email="verified@example.com",
            phone="+15145550125",
        )
        other_client = CRMClient(
            company_id=company.id,
            first_name="Other",
            last_name="Client",
            email="other@example.com",
            phone="+15145550126",
        )
        session.add_all([verified_client, other_client])
        session.flush()
        appointment = CRMAppointment(
            company_id=company.id,
            client_id=other_client.id,
            title="Private appointment",
            start_time=datetime.now(timezone.utc) + timedelta(days=3),
            end_time=datetime.now(timezone.utc) + timedelta(days=3, minutes=30),
            duration_minutes=30,
            status="confirmed",
            price=80,
            currency="CAD",
        )
        session.add(appointment)
        session.commit()
        call = orchestrator.record_inbound(config, {
            "call_control_id": "verified-client-ownership-call",
            "from": verified_client.phone,
        })
        call.caller_type = "CLIENT"
        call.verified_client_id = verified_client.id
        call.caller_verified_at = datetime.now(timezone.utc)
        session.commit()

        cancelled = asyncio.run(orchestrator._dispatch_tool(config, call, "cancel_appointment", {
            "appointment_id": str(appointment.id), "confirmed": True,
        }))
        rescheduled = asyncio.run(orchestrator._dispatch_tool(config, call, "reschedule_appointment", {
            "appointment_id": str(appointment.id), "starts_at": (datetime.now(timezone.utc) + timedelta(days=4)).isoformat(), "confirmed": True,
        }))

        assert cancelled == {"success": False, "error": "appointment_not_owned_by_verified_caller"}
        assert rescheduled == {"success": False, "error": "appointment_not_owned_by_verified_caller"}
        assert appointment.status == "confirmed"
        assert appointment.start_time.date() == (datetime.now(timezone.utc) + timedelta(days=3)).date()
    finally:
        session.close()
        engine.dispose()


def test_verified_voice_metrics_reuse_central_ai_and_are_idempotent(tmp_path):
    engine, session, company, config, api_key, orchestrator = _voice_database(tmp_path)
    try:
        owner = User(
            company_id=company.id,
            first_name="Owner",
            last_name="Example",
            email="owner-metrics@example.com",
            phone="+15145550123",
            password_hash="test-hash",
            role=UserRole.OWNER,
            is_active=True,
        )
        session.add(owner)
        session.flush()
        session.add_all([
            CompanyMembership(company_id=company.id, user_id=owner.id, role=UserRole.OWNER, is_active=True),
            BillingAccount(company_id=company.id, plan_code="professional", status="active"),
        ])
        session.commit()
        call = orchestrator.record_inbound(config, {
            "call_control_id": "verified-metrics-call",
            "from": owner.phone,
        })
        call.caller_type = "OWNER"
        call.authenticated_user_id = owner.id
        call.caller_verified_at = datetime.now(timezone.utc)
        session.commit()

        class _CentralAI:
            def __init__(self):
                self.calls = []

            async def execute(self, tenant, user_id, conversation_id, query, **kwargs):
                self.calls.append((tenant, user_id, conversation_id, query, kwargs))
                return SimpleNamespace(
                    status="success",
                    answer="Vous avez 12 commandes aujourd'hui.",
                    selected_agent="retail",
                    remaining_ai_credits=6499,
                    tool_outcomes=({"tool": "get_sales_summary", "success": True, "confirmed": True},),
                )

        central = _CentralAI()
        request = VoiceToolRequest(
            call_id=call.telnyx_call_control_id,
            action_id="metrics-action-once",
            arguments={"question": "Combien de commandes aujourd'hui ?"},
        )
        first = asyncio.run(voice_business_metrics(
            request, api_key, session, Settings(), central, None
        ))
        second = asyncio.run(voice_business_metrics(
            request, api_key, session, Settings(), central, None
        ))

        assert first["success"] is True
        assert first["selected_agent"] == "retail"
        assert second == first
        assert len(central.calls) == 1
        assert central.calls[0][0] == TenantContext(company.id, owner.id)
        assert central.calls[0][1] == owner.id
        assert call.central_conversation_id is not None
    finally:
        session.close()
        engine.dispose()


def test_voice_availability_reuses_canonical_service_and_fails_closed(tmp_path, monkeypatch):
    from backend.app.services.crm_availability_service import AvailabilityUnavailable, CRMAvailabilityService
    engine, session, company, config, _, orchestrator = _voice_database(tmp_path)
    calls = []

    async def unavailable(service, tenant_id, day, **kwargs):
        calls.append(tenant_id)
        raise AvailabilityUnavailable("EXTERNAL_AVAILABILITY_UNAVAILABLE")

    monkeypatch.setattr(CRMAvailabilityService, "list_available_slots", unavailable)
    try:
        response = asyncio.run(orchestrator._check_availability(config, {
            "service_name": "Consultation", "date": (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat(),
        }))
        assert calls == [company.id]
        assert response["success"] is False
        assert response["state"] == "EXTERNAL_AVAILABILITY_UNAVAILABLE"
        assert response["available_slots"] == []
        assert not session.new and not session.dirty
    finally:
        session.close()
        engine.dispose()


def test_voice_opening_precheck_uses_tenant_hours_not_legacy_voice_hours(tmp_path):
    engine, session, company, config, _, service = _voice_database(tmp_path)
    try:
        target = datetime(2027, 2, 8, tzinfo=timezone.utc).date()
        company.business_hours = {"weekly": {"monday": [{"open": "10:00", "close": "12:00"}]}}
        config.opening_hours = {}
        session.commit()
        opened, closed = service._opening_interval(config, target)
        assert opened.hour == 15 and closed.hour == 17
        assert service._utc_datetime("2027-02-08T10:00:00", config) == opened
    finally:
        session.close()
        engine.dispose()


def test_duplicate_telnyx_inbound_event_reuses_single_call_row(tmp_path) -> None:
    engine, session, _, config, _, service = _voice_database(tmp_path)
    payload = {"call_control_id": "telnyx-replayed-call", "from": "+15145550120"}
    try:
        first = service.record_inbound(config, payload)
        replay = service.record_inbound(config, payload)
        assert first.id == replay.id
        assert session.scalar(select(func.count()).select_from(VoiceCall).where(
            VoiceCall.config_id == config.id,
            VoiceCall.telnyx_call_control_id == payload["call_control_id"],
        )) == 1
    finally:
        session.close()
        engine.dispose()


def test_unconfirmed_voice_booking_does_not_create_appointment(tmp_path) -> None:
    engine, session, company, config, _, service = _voice_database(tmp_path)
    try:
        result = asyncio.run(service.execute_tool(
            config,
            "retell-call-unconfirmed",
            "action-unconfirmed",
            "book_appointment",
            {
                "confirmed": False,
                "caller_name": "Alex Client",
                "caller_phone": "+15145550123",
                "service_name": "Consultation",
                "starts_at": (datetime.now(ZoneInfo("America/Toronto")) + timedelta(days=2)).replace(hour=10, minute=0).isoformat(),
            },
        ))
        assert result["confirmation_required"] is True
        assert session.scalar(select(func.count()).select_from(CRMAppointment).where(CRMAppointment.company_id == company.id)) == 0
    finally:
        session.close()
        engine.dispose()


def test_retried_voice_booking_action_creates_one_appointment(tmp_path) -> None:
    engine, session, company, config, _, service = _voice_database(tmp_path)
    starts_at = (datetime.now(ZoneInfo("America/Toronto")) + timedelta(days=2)).replace(
        hour=10, minute=0, second=0, microsecond=0
    ).isoformat()
    arguments = {
        "confirmed": True,
        "caller_name": "Alex Client",
        "caller_phone": "+15145550123",
        "service_name": "Consultation",
        "starts_at": starts_at,
    }
    try:
        first = asyncio.run(service.execute_tool(
            config, "retell-retry-call", "same-booking-action", "book_appointment", arguments
        ))
        replay = asyncio.run(service.execute_tool(
            config, "retell-retry-call", "same-booking-action", "book_appointment", arguments
        ))
        assert first["success"] is True
        assert replay == first
        assert session.scalar(select(func.count()).select_from(CRMAppointment).where(
            CRMAppointment.company_id == company.id,
        )) == 1
    finally:
        session.close()
        engine.dispose()


def test_one_hundred_parallel_confirmed_calls_cannot_double_book(tmp_path) -> None:
    engine, session, company, config, _, service = _voice_database(tmp_path)
    start_time = (datetime.now(ZoneInfo("America/Toronto")) + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0).isoformat()

    async def reserve(index: int) -> dict:
        return await service.execute_tool(
            config,
            f"retell-call-{index}",
            f"book-action-{index}",
            "book_appointment",
            {
                "confirmed": True,
                "caller_name": f"Caller {index}",
                "caller_phone": f"+1514555{index:04d}",
                "service_name": "Consultation",
                "starts_at": start_time,
            },
        )

    try:
        async def run_all() -> list[dict]:
            return await asyncio.gather(*(reserve(i) for i in range(100)))

        results = asyncio.run(run_all())
        booked = [result for result in results if result.get("success") is True]
        conflicts = [result for result in results if result.get("conflict") is True]
        assert len(booked) == 1
        assert len(conflicts) == 99
        assert session.scalar(select(func.count()).select_from(CRMAppointment).where(CRMAppointment.company_id == company.id)) == 1
    finally:
        session.close()
        engine.dispose()


def test_after_hours_message_is_saved_in_crm(tmp_path) -> None:
    engine, session, company, config, _, service = _voice_database(tmp_path)
    try:
        result = asyncio.run(service.execute_tool(
            config,
            "retell-after-hours-call",
            "take-message-action",
            "take_message",
            {"caller_name": "Sam Caller", "caller_phone": "+15145550124", "message": "Please call me back."},
        ))
        assert result == {"success": True, "message_recorded": True}
        assert session.scalar(select(func.count()).select_from(CRMNote).where(CRMNote.company_id == company.id)) == 1
        assert session.scalar(select(func.count()).select_from(CRMCommunication).where(CRMCommunication.company_id == company.id)) == 1
    finally:
        session.close()
        engine.dispose()


def test_two_consecutive_uncertainties_transfer_to_human(tmp_path) -> None:
    engine, session, _, config, _, service = _voice_database(tmp_path)
    telnyx = service.telnyx
    try:
        call = VoiceCall(
            company_id=config.company_id,
            config_id=config.id,
            telnyx_call_control_id="telnyx-control-test",
            retell_call_id="retell-uncertain-test",
            caller_phone="+15145550125",
            status="in_progress",
        )
        session.add(call)
        session.commit()
        first = asyncio.run(service.execute_tool(
            config, "retell-uncertain-test", "uncertain-1", "transfer_to_human",
            {"uncertain": True, "reason": "unresolved_question"},
        ))
        second = asyncio.run(service.execute_tool(
            config, "retell-uncertain-test", "uncertain-2", "transfer_to_human",
            {"uncertain": True, "reason": "unresolved_question"},
        ))
        assert first["action"] == "clarify_once"
        assert second["transfer"] is True
        assert telnyx.transfers == [("telnyx-control-test", "+15145550199")]
    finally:
        session.close()
        engine.dispose()


def test_call_transcript_and_summary_are_idempotently_saved_to_crm(tmp_path) -> None:
    engine, session, company, config, _, service = _voice_database(tmp_path)
    try:
        call_id = "retell-finished-call"
        session.add(VoiceCall(
            company_id=company.id,
            config_id=config.id,
            retell_call_id=call_id,
            caller_phone="+15145550126",
            status="in_progress",
        ))
        session.commit()
        call_data = {
            "transcript": "Caller asked about a service and left a message.",
            "call_analysis": {"call_summary": "Asked for a callback."},
        }
        asyncio.run(service.finish_call(config, call_id, call_data))
        asyncio.run(service.finish_call(config, call_id, call_data))

        activities = list(session.scalars(select(CRMActivity).where(CRMActivity.company_id == company.id)).all())
        assert len(activities) == 1
        assert "Asked for a callback." in activities[0].notes
        assert "Caller asked about a service" in activities[0].notes
    finally:
        session.close()
        engine.dispose()


def test_telnyx_signature_accepts_signed_body_and_rejects_body_changes() -> None:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    body = b'{"data":{"event_type":"call.initiated"}}'
    timestamp = str(int(time()))
    signature = base64.b64encode(private_key.sign(timestamp.encode() + b"|" + body)).decode()
    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/v1/voice/telnyx/webhook",
        "headers": [
            (b"telnyx-signature-ed25519", signature.encode()),
            (b"telnyx-timestamp", timestamp.encode()),
        ],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "scheme": "http",
    })
    settings = Settings(TELNYX_PUBLIC_KEY=base64.b64encode(public_key).decode())
    _verify_telnyx_signature(request, body, settings)
    with pytest.raises(Exception):
        _verify_telnyx_signature(request, body + b" ", settings)
