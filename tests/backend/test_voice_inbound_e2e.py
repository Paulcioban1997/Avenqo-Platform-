"""Inbound Telnyx → mocked Realtime → French CRM booking e2e.

Covers the gaps left after PR #29: webhook answer/bridge, mocked media/Realtime
session, French conversation turns, Voice→CRM appointment booking, then hangup.

Never contacts live Telnyx or OpenAI. Uses signed webhook fixtures, a loopback
Realtime adapter, and the existing CreateAppointmentTool hook with CRMService
running against the test SQLite database.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select
from starlette.websockets import WebSocketDisconnect

from backend.app.ai.tools.business.crm_tools import CreateAppointmentArgs, CreateAppointmentTool
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.dependencies.ai_engine import get_prediction_service
from backend.app.dependencies.central_ai import get_central_ai_service
from backend.app.models import CompanyMembership, CRMAppointment, CRMClient, User, UserRole, VoiceCall
from backend.app.services.crm_service import CRMService
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.voice.auth import VoiceCallerAuth
import backend.app.voice.telnyx_media as media_module
from shared.ai_engine.contracts import TenantContext
from tests.backend.test_telnyx_media import (
    FakeAudioAdapter,
    FakeMediaSocket,
    FakeUsageService,
    configure_local_public_call,
    eventually,
    start_event,
)
from tests.backend.test_voice_agent import signed_telnyx_webhook  # noqa: F401


FRENCH_BOOKING_TURNS = [
    "Allô bonjour",
    "Je voudrais prendre un rendez-vous pour une consultation",
    "Demain à 14 heures s'il vous plaît",
        "Mon nom est Marie Tremblay, mon courriel est marie.tremblay@clinique.ca",
    "Oui, confirmez le rendez-vous",
]


def _weekday_afternoon(hours_utc: int = 18) -> datetime:
    start = (datetime.now(timezone.utc) + timedelta(days=2)).replace(
        hour=hours_utc, minute=0, second=0, microsecond=0
    )
    while start.weekday() >= 5:
        start += timedelta(days=1)
    return start


def _prepare_inbound_media_tenant(env) -> User:
    """Professional tenant with Voice + CRM only (two of five plan slots)."""
    configure_local_public_call(env)
    env.company.business_hours = {
        "weekly": {
            "monday": [{"open": "09:00", "close": "17:00"}],
            "tuesday": [{"open": "09:00", "close": "17:00"}],
            "wednesday": [{"open": "09:00", "close": "17:00"}],
            "thursday": [{"open": "09:00", "close": "17:00"}],
            "friday": [{"open": "09:00", "close": "17:00"}],
        }
    }
    owner = User(
        company_id=env.company.id,
        first_name="Owner",
        last_name="Inbound",
        email="inbound-e2e@example.com",
        password_hash="test",
        phone="+15145550999",
        role=UserRole.OWNER,
        is_active=True,
    )
    env.session.add(owner)
    env.session.flush()
    env.session.add(CompanyMembership(
        company_id=env.company.id, user_id=owner.id, role=UserRole.OWNER, is_active=True,
    ))
    ModuleEntitlementService(env.session).activate_module(TenantContext(env.company.id), "crm")
    env.session.commit()
    return owner


class InboundLoopbackAdapter(FakeAudioAdapter):
    """Mocked OpenAI Realtime: emits French transcripts, never opens a live socket."""

    def __init__(self, phrases: list[str]):
        super().__init__()
        self._phrases = list(phrases)
        self.turn_count = 0

    async def send_audio(self, audio):
        await super().send_audio(audio)
        if self._phrases:
            self.turn_count += 1
            text = self._phrases.pop(0)
            await self.incoming.put(SimpleNamespace(
                type="conversation.item.input_audio_transcription.completed",
                item_id=f"inbound-turn-{self.turn_count}",
                event_id=f"inbound-evt-{self.turn_count}",
                transcript=text,
                usage=None,
            ))

    async def speak(self, text):
        await super().speak(text)
        resp_id = f"inbound-resp-{len(self.spoken)}"
        await self.incoming.put(SimpleNamespace(type="response.created", response=SimpleNamespace(id=resp_id)))
        await self.incoming.put(SimpleNamespace(
            type="response.output_audio.delta",
            response_id=resp_id,
            delta=base64.b64encode(b"\x00\x00" * 480).decode(),
        ))
        await self.incoming.put(SimpleNamespace(
            type="response.done",
            event_id=f"done-{resp_id}",
            response=SimpleNamespace(id=resp_id, status="completed", usage=SimpleNamespace(input_tokens=8, output_tokens=8)),
        ))


def _bind_mocked_realtime(env, monkeypatch, adapter, central) -> None:
    monkeypatch.setattr(media_module, "OpenAIRealtimeAudioAdapter", lambda *_args: adapter)
    monkeypatch.setattr(media_module, "TelnyxClient", lambda *_args: env.service.telnyx)
    monkeypatch.setattr(media_module, "resolve_tenant_capabilities", lambda *_args: frozenset({"crm:read", "crm:write"}))
    env.client.app.dependency_overrides[get_central_ai_service] = lambda: central
    env.client.app.dependency_overrides[get_prediction_service] = lambda: object()


def _pcmu_frame(stream_id: str, chunk: int) -> dict[str, Any]:
    return {
        "event": "media",
        "stream_id": stream_id,
        "media": {
            "track": "inbound",
            "chunk": str(chunk),
            "payload": base64.b64encode(b"\xff" * 160).decode(),
        },
    }


def _drain_socket(socket) -> None:
    try:
        for _ in range(20):
            socket.receive_json()
    except (WebSocketDisconnect, Exception):
        pass


@pytest.mark.asyncio
async def test_inbound_telnyx_french_realtime_books_crm_appointment_then_hangup(
    signed_telnyx_webhook, monkeypatch,
):
    env = signed_telnyx_webhook
    _prepare_inbound_media_tenant(env)
    starts_at = _weekday_afternoon()
    crm_creates: list[dict[str, Any]] = []
    captured_turns: list[str] = []
    captured_conversations: list[Any] = []
    booking_results: list[Any] = []
    real_create = CRMService.create_appointment

    async def spy_create(self, company_id, data, actor_name="Utilisateur", check_conflicts=True):
        crm_creates.append({"company_id": company_id, "title": data.get("title"), "actor_name": actor_name})
        return await real_create(self, company_id, data, actor_name=actor_name, check_conflicts=check_conflicts)

    monkeypatch.setattr(CRMService, "create_appointment", spy_create)

    class Central:
        def __init__(self):
            self.usage_service = FakeUsageService()

        async def execute(self, *args, **kwargs):
            tenant, user_id, conversation_id, transcript = args[:4]
            captured_turns.append(transcript)
            captured_conversations.append(conversation_id)
            lowered = transcript.lower()
            if "allô bonjour" in lowered or "allo bonjour" in lowered:
                return SimpleNamespace(status="success", answer="Bonjour ! Comment puis-je vous aider aujourd'hui ?", selected_agent="crm")
            if "rendez-vous" in lowered and "confirmez" not in lowered:
                return SimpleNamespace(status="success", answer="Avec plaisir. Quel jour et quelle heure vous conviendraient ?", selected_agent="crm")
            if "14 heures" in lowered:
                return SimpleNamespace(status="success", answer="Le créneau de 14 heures est disponible. Quel est votre nom et votre courriel ?", selected_agent="crm")
            if "marie tremblay" in lowered:
                return SimpleNamespace(status="success", answer="Merci madame Tremblay. Souhaitez-vous que je confirme ce rendez-vous ?", selected_agent="crm")
            if "confirmez" in lowered:
                context = ToolExecutionContext(
                    tenant=tenant,
                    user_id=user_id,
                    permissions=kwargs.get("permissions") or frozenset({"ai:use", "crm:appointments:write"}),
                    request_id="voice-inbound-e2e-book",
                    conversation_id=conversation_id,
                    locale="fr",
                    company_timezone=env.company.timezone or "America/Toronto",
                )
                booked = await CreateAppointmentTool(env.session).run(
                    context,
                    CreateAppointmentArgs(
                        client_name_or_id="Marie Tremblay",
                        client_email="marie.tremblay@clinique.ca",
                        client_phone="+15145550123",
                        start_time=starts_at.isoformat(),
                        title="Consultation",
                        duration_minutes=30,
                        service_name="Consultation",
                        confirmed=True,
                    ),
                )
                booking_results.append(booked)
                if booked.success:
                    call = env.session.scalar(select(VoiceCall))
                    call.appointment_id = UUID(str(booked.data["id"]))
                    call.status = "appointment_booked"
                    call.source_context = {**(call.source_context or {}), "appointment_confirmed": True}
                    env.session.commit()
                return SimpleNamespace(
                    status="success",
                    answer="C'est confirmé pour demain à 14 heures. Autre chose ?",
                    selected_agent="crm",
                )
            return SimpleNamespace(status="success", answer="Je suis à votre écoute.", selected_agent="crm")

    phrases = [*FRENCH_BOOKING_TURNS, "Au revoir et bonne journée"]
    adapter = InboundLoopbackAdapter(phrases)
    central = Central()
    _bind_mocked_realtime(env, monkeypatch, adapter, central)

    initiated = env.send(env.event())
    assert initiated.status_code == 200 and initiated.json()["status"] == "answering"
    assert env.service.telnyx.commands[0][0] == "answer"
    answered = env.send(env.event("call.answered"))
    assert answered.status_code == 200 and answered.json()["routed"] is True
    assert env.service.telnyx.media_streams
    control_id, stream_url, client_state, _command = env.service.telnyx.media_streams[0]
    assert control_id == "inbound-control"
    call = env.session.scalar(select(VoiceCall))
    assert call.status == "in_progress" and call.caller_type == "UNKNOWN"
    assert stream_url.endswith(str(call.id))
    assert VoiceCallerAuth(env.session, env.settings).valid_session(call) is None

    event = start_event()
    event["stream_id"] = "stream-inbound-e2e"
    event["start"].update(
        call_control_id=call.telnyx_call_control_id,
        to=env.config.telnyx_phone_number,
        client_state=client_state,
    )

    with env.client.websocket_connect(f"/api/v1/voice/telnyx/media/{call.id}") as socket:
        socket.send_json(event)
        for index in range(1, len(FRENCH_BOOKING_TURNS) + 1):
            socket.send_json(_pcmu_frame("stream-inbound-e2e", index))
            response = socket.receive_json()
            assert response.get("event") in {"media", "clear"}
        socket.send_json(_pcmu_frame("stream-inbound-e2e", 6))
        try:
            socket.receive_json()
        except WebSocketDisconnect:
            pass
        try:
            socket.send_json({"event": "stop", "stream_id": "stream-inbound-e2e"})
        except Exception:
            pass
        _drain_socket(socket)

    assert captured_turns == FRENCH_BOOKING_TURNS
    assert len(captured_conversations) == 5
    assert captured_conversations[0] is not None
    assert all(item == captured_conversations[0] for item in captured_conversations)
    assert len(adapter.spoken) >= 6
    assert "Voice Test Shop" in adapter.spoken[0]
    assert any("confirmé" in spoken for spoken in adapter.spoken)
    for spoken in adapter.spoken:
        assert "*" not in spoken and "#" not in spoken

    assert len(booking_results) == 1 and booking_results[0].success is True
    assert len(crm_creates) == 1
    assert crm_creates[0]["company_id"] == env.company.id
    assert crm_creates[0]["actor_name"] == "IA Copilot"
    client = env.session.scalar(select(CRMClient).where(
        CRMClient.company_id == env.company.id, CRMClient.first_name == "Marie",
    ))
    assert client is not None and client.email == "marie.tremblay@clinique.ca"
    appointments = env.session.scalars(select(CRMAppointment).where(CRMAppointment.company_id == env.company.id)).all()
    assert len(appointments) == 1
    assert appointments[0].title == "Consultation"
    assert appointments[0].client_id == client.id

    hangup = env.send(env.event("call.hangup"))
    assert hangup.status_code == 200
    env.session.expire_all()
    ended = env.session.get(VoiceCall, call.id)
    assert ended.ended_at is not None
    assert ended.status == "appointment_booked"
    assert ended.central_conversation_id == captured_conversations[0]
    assert str(ended.appointment_id) == booking_results[0].data["id"]
    assert env.session.scalar(select(func.count()).select_from(CRMAppointment).where(
        CRMAppointment.company_id == env.company.id,
    )) == 1
    assert env.settings.openai_api_key == "fake-audio-key"
    assert env.settings.telnyx_api_key == "test-secret-never-log"
    assert "test-secret-never-log" not in "".join(adapter.spoken)


@pytest.mark.asyncio
async def test_inbound_telnyx_realtime_barge_in_interrupt_then_hangup(signed_telnyx_webhook, monkeypatch):
    env = signed_telnyx_webhook
    _prepare_inbound_media_tenant(env)
    captured: list[str] = []
    adapter = FakeAudioAdapter()
    hangups: list[bool] = []

    async def hangup_call() -> None:
        hangups.append(True)
        await env.service.telnyx.hangup("inbound-control")

    async def execute_turn(_item_id: str, transcript: str) -> dict[str, Any]:
        captured.append(transcript)
        if "au revoir" in transcript.lower():
            return {"status": "success", "answer": "Merci de votre appel. Au revoir !", "hangup": True}
        return {"status": "success", "answer": "Oui, je vous écoute."}

    assert env.send(env.event()).json()["status"] == "answering"
    assert env.send(env.event("call.answered")).json()["routed"] is True
    call = env.session.scalar(select(VoiceCall))
    assert call.status == "in_progress"

    socket = FakeMediaSocket()
    start = start_event()
    start["start"].update(
        call_control_id=call.telnyx_call_control_id,
        to=env.config.telnyx_phone_number,
        client_state=env.service.telnyx.media_streams[0][2],
    )
    async def validate_start(_event):
        return None

    async def authorize():
        return None

    bridge = media_module.TelnyxMediaBridge(
        socket, adapter, locale="fr",
        validate_start=validate_start,
        authorize=authorize,
        execute_turn=execute_turn,
        hangup_call=hangup_call,
        initial_answer="Bonjour, Voice Test Shop.",
    )
    await socket.incoming.put(start)
    running = asyncio.create_task(bridge.run())
    await eventually(lambda: adapter.opened)
    await eventually(lambda: len(adapter.spoken) >= 1)
    await adapter.incoming.put(SimpleNamespace(type="input_audio_buffer.speech_started"))
    await eventually(lambda: adapter.interruptions >= 1)
    assert any(item.get("event") == "clear" for item in socket.sent)
    await adapter.incoming.put(SimpleNamespace(
        type="conversation.item.input_audio_transcription.completed",
        item_id="interrupt-turn-1",
        transcript="Allô, vous m'entendez ?",
    ))
    await eventually(lambda: captured == ["Allô, vous m'entendez ?"])
    await adapter.incoming.put(SimpleNamespace(
        type="conversation.item.input_audio_transcription.completed",
        item_id="interrupt-hangup",
        transcript="Au revoir",
    ))
    await eventually(lambda: hangups == [True])
    # Wait for the provider command, not just entry into the async callback.
    # Sending stop earlier cancels the pending callback while audio drains.
    await eventually(lambda: ("hangup", "inbound-control") in env.service.telnyx.commands)
    await socket.incoming.put({"event": "stop", "stream_id": "stream-test"})
    await running

    assert adapter.interruptions >= 1
    assert ("hangup", "inbound-control") in env.service.telnyx.commands
    assert env.send(env.event("call.hangup")).status_code == 200
    env.session.expire_all()
    ended = env.session.get(VoiceCall, call.id)
    assert ended.ended_at is not None
    assert ended.status in {"ended", "completed"}
    assert env.session.scalar(select(func.count()).select_from(CRMAppointment).where(
        CRMAppointment.company_id == env.company.id,
    )) == 0
