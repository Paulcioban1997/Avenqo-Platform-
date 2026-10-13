"""Sandbox-only elapsed-call guard. Not a provider-side duration guarantee."""
import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

GARAGE_ID = UUID("96f25272-f659-4323-b158-4fc76d761a92")
CONFIG_ID = UUID("dd5c1f24-353f-4f68-a6f8-743c02011152")
PRODUITS_ID = UUID("9c97cb94-e9f9-46fb-afd4-8a1d21019cff")
PRODUITS_CONFIG_ID = UUID("ae35875f-b2f9-442c-b73e-8d3a9f78a272")
CONNECTION_ID = "3069110156336826311"
PHONE = "+14386075438"
_tasks = set()
_scheduled_ids = set()
logger = logging.getLogger("avenqo.voice.deadline")


def approved_test_bindings():
    return ((GARAGE_ID, CONFIG_ID), (PRODUITS_ID, PRODUITS_CONFIG_ID))


def is_sandbox_test_call(call, settings):
    return (getattr(settings, "voice_sandbox_test_guard_enabled", True)
            and settings.environment == "sandbox"
            and settings.telnyx_voice_connection_id == CONNECTION_ID
            and (call.company_id, call.config_id) in approved_test_bindings())


def remaining_seconds(started_at, *, now=None):
    if started_at is None:
        return 0.0
    now = now or datetime.now(timezone.utc)
    start = started_at.replace(tzinfo=timezone.utc) if started_at.tzinfo is None else started_at
    # A future timestamp must never extend the trial duration.
    return max(0.0, 90.0 - max(0.0, (now - start).total_seconds()))


async def stop_expired_call(call_id, *, session_factory, settings, client):
    """Fresh session; revalidate the exact synthetic binding before any command."""
    from sqlalchemy import select
    from backend.app.models import VoiceCall, VoicePhoneNumber

    if settings.environment != "sandbox" or settings.telnyx_voice_connection_id != CONNECTION_ID:
        raise PermissionError("Sandbox connection required")
    with session_factory() as db:
        call = db.scalar(select(VoiceCall).where(VoiceCall.id == call_id).with_for_update())
        if call is None or not is_sandbox_test_call(call, settings):
            raise PermissionError("Synthetic call ownership required")
        if call.ended_at is not None:
            return False
        binding = db.scalar(select(VoicePhoneNumber).where(
            VoicePhoneNumber.company_id == call.company_id, VoicePhoneNumber.config_id == call.config_id,
            VoicePhoneNumber.phone_number == PHONE, VoicePhoneNumber.status == "ACTIVE",
            VoicePhoneNumber.provider == "telnyx", VoicePhoneNumber.provider_connection_id == CONNECTION_ID))
        if binding is None:
            raise PermissionError("Synthetic number binding required")
        if remaining_seconds(call.started_at) > 0:
            return False
        if not call.telnyx_call_control_id:
            raise ValueError("Provider call identifier required")
        # Do not mark completion if provider termination fails.
        await asyncio.wait_for(client.hangup(call.telnyx_call_control_id), timeout=5)
        call.ended_at = datetime.now(timezone.utc)
        call.source_context = {**(call.source_context or {}), "sandbox_stop_reason": "total_duration_limit"}
        db.commit()
        logger.info("Sandbox total-call stop accepted; call_id=%s", call.id)
        return True


def schedule_deadline(call, settings):
    if not is_sandbox_test_call(call, settings):
        return
    from backend.app.database import SessionLocal
    from backend.app.voice.providers import TelnyxClient

    call_id, delay = call.id, remaining_seconds(call.started_at)
    if call_id in _scheduled_ids:
        return
    _scheduled_ids.add(call_id)

    async def watchdog():
        await asyncio.sleep(delay)
        try:
            await stop_expired_call(call_id, session_factory=SessionLocal,
                settings=settings, client=TelnyxClient(settings))
        except Exception as exc:
            logger.error("Sandbox total-call stop failed; call_id=%s error_class=%s", call_id, type(exc).__name__)

    task = asyncio.create_task(watchdog())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    task.add_done_callback(lambda _task: _scheduled_ids.discard(call_id))
