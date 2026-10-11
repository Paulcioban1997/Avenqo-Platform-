"""Regression coverage for the local PR33/PR37 reconciliation."""
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from backend.app.models import VoiceCall
from backend.app.services.automation_service import AutomationService
from backend.app.voice.telnyx_media import TelnyxMediaBridge
from tests.backend.test_voice_agent import _authenticated_booking_calls, _voice_database
from tests.backend.test_telnyx_media import (
    authorized_media_call,  # noqa: F401 - shared pytest fixture
    FakeAudioAdapter,
    FakeMediaSocket,
    test_public_caller_natural_multi_turn_crm_appointment_preserves_conversation_context as _public_conversation,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("iteration", range(3))
async def test_public_conversation_cleanup_repeated(authorized_media_call, monkeypatch, iteration):
    """Exercise closure repeatedly with fresh call/tenant fixtures."""
    await _public_conversation(authorized_media_call, monkeypatch)


@pytest.mark.asyncio
async def test_cancelled_turn_cannot_reenter_queue_after_child_completion(monkeypatch):
    entered = asyncio.Event()

    async def noop(*_args):
        return None

    bridge = TelnyxMediaBridge(FakeMediaSocket(), FakeAudioAdapter(), locale="fr",
        validate_start=noop, authorize=noop, execute_turn=noop)

    async def raced_completion(*_args):
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return

    monkeypatch.setattr(bridge, "_execute", raced_completion)
    task = asyncio.create_task(bridge._execute_turns())
    try:
        await bridge._turns.put(("cancelled-turn", "test transcript", 0))
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        done, _pending = await asyncio.wait({task}, timeout=0.5)
        assert task in done, "Cancelled audio turn re-entered an empty queue"
        assert task.cancelled()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def test_booking_retains_confirmation_automation_and_replay_isolation(tmp_path, monkeypatch):
    engine, db, company, config, _key, service = _voice_database(tmp_path)
    events = []

    def dispatch(_self, company_id, event_type, payload, **kwargs):
        events.append((company_id, event_type, payload, kwargs))

    monkeypatch.setattr(AutomationService, "dispatch", dispatch)
    try:
        _authenticated_booking_calls(db, company, config, service, ["integration-booking"])
        arguments = {
            "confirmed": True,
            "caller_name": "Integration Client",
            "caller_phone": "+15145550123",
            "service_name": "Consultation",
            "starts_at": (datetime.now(ZoneInfo("America/Toronto")) + timedelta(days=2))
            .replace(hour=10, minute=0, second=0, microsecond=0).isoformat(),
        }
        result = asyncio.run(service.execute_tool(
            config, "integration-booking", "integration-action", "book_appointment", arguments,
        ))
        replay = asyncio.run(service.execute_tool(
            config, "integration-booking", "integration-action", "book_appointment", arguments,
        ))
        assert result["success"] is True and replay == result
        call = db.scalar(select(VoiceCall).where(VoiceCall.company_id == company.id))
        assert call.status == "appointment_booked"
        assert call.source_context["appointment_confirmed"] is True
        dispatched = [event for event in events if event[1] == "voice_appointment"]
        assert len(dispatched) == 1
        tenant, _, payload, options = dispatched[0]
        assert tenant == company.id
        assert payload == {"appointment_id": str(call.appointment_id), "call_id": str(call.id)}
        assert options["idempotency_key"] == str(call.appointment_id)
    finally:
        db.close()
        engine.dispose()
