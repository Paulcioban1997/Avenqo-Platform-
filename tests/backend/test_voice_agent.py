from __future__ import annotations

import asyncio
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from time import time
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
    CRMActivity,
    Company,
    CompanyModule,
    CompanyModuleStatus,
    CRMAppointment,
    CRMCommunication,
    CRMNote,
    Module,
    VoiceBusinessConfig,
    VoiceCall,
)
from backend.app.routers.voice import _verify_telnyx_signature
from backend.app.voice.service import VoiceOrchestrator, _api_key_hash


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
