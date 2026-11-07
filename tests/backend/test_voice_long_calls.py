"""Offline long-call boundaries with real tenant records and controllable provider time."""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from backend.app.models import VoiceCall, VoiceBusinessConfig
from backend.app.voice.call_policy import CallPolicy, admit, remaining, policy_for, record_ai_cost
from backend.app.voice.realtime_rotation import RotatingRealtimeAdapter
from backend.app.voice.sandbox_deadline import is_sandbox_test_call
from test_voice_commercial_provisioning import setup


def prepare(env, index=0, **policy):
    tenant = env.tenants[index]
    config = env.db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == tenant.company_id))
    config.enabled = True
    config.call_policy = CallPolicy(**policy).model_dump(mode="json")
    call = VoiceCall(company_id=tenant.company_id, config_id=config.id, caller_phone="fixture",
                     telnyx_call_control_id="fixture-" + str(index) + "-" + str(datetime.now().timestamp()),
                     started_at=datetime.now(timezone.utc), status="incoming")
    env.db.add(call)
    env.db.commit()
    env.settings.voice_long_calls_enabled = True
    env.settings.voice_budget_rate_ceiling_usd_per_minute = Decimal("0.05")
    return call, config


@pytest.mark.parametrize("minutes", [5, 30, 60])
def test_call_budget_counts_total_phone_time_not_media_reconnect(setup, minutes):
    call, config = prepare(setup, max_call_seconds=minutes * 60)
    snapshot = admit(setup.db, setup.settings, call, config)
    assert snapshot["reserved_seconds"] == minutes * 60
    start = datetime.fromisoformat(snapshot["started_at"])
    assert remaining(call, now=start + timedelta(seconds=95)) == minutes * 60 - 95
    assert admit(setup.db, setup.settings, call, config) == snapshot
    assert remaining(call, now=start + timedelta(minutes=minutes)) == 0
    assert not snapshot["provider_hard_cap"]


def test_company_cannot_bypass_plan_duration_or_concurrency(setup):
    call, config = prepare(setup, max_call_seconds=7200)
    with pytest.raises(PermissionError, match="Duration"):
        admit(setup.db, setup.settings, call, config)
    config.call_policy = CallPolicy(concurrent_calls=2).model_dump(mode="json")
    with pytest.raises(PermissionError, match="Concurrency"):
        policy_for(setup.db, config, setup.settings)
    config.call_policy = CallPolicy(max_call_seconds=None).model_dump(mode="json")
    with pytest.raises(PermissionError, match="duration limit"):
        policy_for(setup.db, config, setup.settings)


def test_no_fixed_business_duration_still_has_finite_spend_allowance(setup):
    setup.settings.voice_plan_max_call_seconds = {"base": None}
    call, config = prepare(setup, max_call_seconds=None, call_budget_usd=Decimal("8"))
    snapshot = admit(setup.db, setup.settings, call, config)
    assert snapshot["max_call_seconds"] is None
    assert snapshot["reserved_seconds"] == 9600  # Cost allowance still stops an uncontrolled call.


def test_active_calls_reserve_concurrency_until_provider_hangup(setup):
    first, config = prepare(setup)
    admit(setup.db, setup.settings, first, config)
    second, _ = prepare(setup)
    with pytest.raises(PermissionError, match="Concurrent"):
        admit(setup.db, setup.settings, second, config)
    setup.db.rollback()
    first.ended_at = datetime.now(timezone.utc)
    setup.db.commit()
    assert admit(setup.db, setup.settings, second, config)


def test_foreign_tenant_cannot_admit_or_spend_other_company_budget(setup):
    first, config = prepare(setup)
    foreign, foreign_config = prepare(setup, 1)
    with pytest.raises(PermissionError, match="ownership"):
        admit(setup.db, setup.settings, foreign, config)
    admit(setup.db, setup.settings, first, config)
    assert admit(setup.db, setup.settings, foreign, foreign_config)


def test_monthly_budget_unknown_receipt_is_not_silently_refunded(setup):
    first, config = prepare(setup, monthly_budget_usd=Decimal("3"))
    admit(setup.db, setup.settings, first, config)
    first.ended_at = datetime.now(timezone.utc)
    setup.db.commit()
    second, _ = prepare(setup, monthly_budget_usd=Decimal("3"))
    with pytest.raises(PermissionError, match="budget exhausted"):
        admit(setup.db, setup.settings, second, config)


def test_operator_cost_ceiling_required_before_admission(setup):
    call, config = prepare(setup)
    setup.settings.voice_budget_rate_ceiling_usd_per_minute = None
    with pytest.raises(PermissionError, match="approved combined"):
        admit(setup.db, setup.settings, call, config)
    assert not call.source_context.get("runtime_policy")


def test_real_attempt_cost_categories_are_idempotent_and_alert(setup):
    call, config = prepare(setup, call_budget_usd=Decimal("1"))
    admit(setup.db, setup.settings, call, config)
    attempts = [SimpleNamespace(operation="transcription", provider_cost_usd=Decimal(".1")),
                SimpleNamespace(operation="realtime_tts", provider_cost_usd=Decimal(".75"))]
    record_ai_cost(setup.db, call, "fixture-request", attempts)
    record_ai_cost(setup.db, call, "fixture-request", attempts)
    assert call.source_context["runtime_policy"]["ai_cost_usd"] == "0.85"
    assert call.source_context["runtime_policy"]["budget_alert"]


def test_long_pin_session_never_outlives_approved_call_or_operator_limit(setup):
    from backend.app.voice.auth import VoiceCallerAuth
    call, config = prepare(setup, auth_seconds=3600)
    with pytest.raises(PermissionError, match="Authentication"):
        admit(setup.db, setup.settings, call, config)
    setup.db.rollback()
    setup.settings.voice_auth_max_session_seconds = 3600
    admit(setup.db, setup.settings, call, config)
    call.caller_type = "OWNER"
    call.authenticated_user_id = setup.tenants[0].user_id
    setup.db.commit()
    now = datetime.now(timezone.utc)
    session = VoiceCallerAuth(setup.db, setup.settings).establish(call)
    assert 3500 < (session.expires_at - now).total_seconds() <= 3600


def test_policy_api_preserves_other_company_and_rejects_non_managers(setup):
    from backend.app.routers.voice import update_call_policy
    from backend.app.models import User, UserRole
    from fastapi import HTTPException
    first, config = prepare(setup)
    foreign, foreign_config = prepare(setup, 1)
    before = dict(foreign_config.call_policy)
    identity = SimpleNamespace(user=setup.db.get(User, setup.tenants[0].user_id))
    member = SimpleNamespace(role=UserRole.OWNER)
    result = update_call_policy(CallPolicy(max_call_seconds=1800), identity, member, setup.db, setup.settings)
    assert result["policy"]["max_call_seconds"] == 1800
    assert foreign_config.call_policy == before
    with pytest.raises(HTTPException) as denied:
        update_call_policy(CallPolicy(), identity, SimpleNamespace(role=UserRole.USER), setup.db, setup.settings)
    assert denied.value.status_code == 403
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        CallPolicy.model_validate({"company_id": str(foreign.company_id)})


@pytest.mark.asyncio
async def test_idle_stop_ignores_silence_audio_frames_and_uses_provider_hangup():
    from backend.app.voice.telnyx_media import TelnyxMediaBridge
    hangup = AsyncMock()
    bridge = TelnyxMediaBridge(SimpleNamespace(), SimpleNamespace(), locale="fr",
        validate_start=AsyncMock(), authorize=AsyncMock(), execute_turn=AsyncMock(),
        hangup_call=hangup, idle_seconds=0.01)
    bridge._authorized_session = True
    bridge._last_activity = 0
    await asyncio.wait_for(bridge._periodic_auth(), timeout=6)
    assert bridge.telemetry["final_state"] == "IDLE_LIMIT"
    assert hangup.await_count == 1 and bridge._stop_event.is_set()


@pytest.mark.asyncio
async def test_disconnect_never_replays_audio_or_financial_or_crm_actions():
    class Disconnected(Adapter):
        async def events(self):
            if False:
                yield None
            raise ConnectionError("Synthetic transport failure")
    adapter = Disconnected()
    wrapper = RotatingRealtimeAdapter(lambda: adapter, AsyncMock())
    await wrapper.open(locale="en")
    with pytest.raises(ConnectionError, match="no ambiguous"):
        await asyncio.wait_for(anext(wrapper.events()), timeout=1)
    assert adapter.open.await_count == 1 and adapter.speak.await_count == 0
    await wrapper.close()


class Adapter:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.open = AsyncMock()
        self.close = AsyncMock()
        self.speak = AsyncMock()
        self.send_audio = AsyncMock()
        self.interrupt = AsyncMock()
        self.clear_input = AsyncMock()

    async def events(self):
        while True:
            yield await self.queue.get()


@pytest.mark.asyncio
async def test_60_minute_and_longer_rotation_preserves_central_context_without_replaying_actions():
    now = [0.0]
    adapters = []
    def factory():
        item = Adapter()
        adapters.append(item)
        return item
    auth = AsyncMock()
    wrapper = RotatingRealtimeAdapter(factory, auth, clock=lambda: now[0])
    await wrapper.open(locale="fr-CA")
    await wrapper.speak("Authorized response")
    now[0] = 3000
    assert not await wrapper.renew_if_due()  # Speaking; wait for provider confirmation.
    wrapper.response_pending = False
    assert await wrapper.renew_if_due()
    assert len(adapters) == 2 and adapters[1].speak.await_count == 0
    # The caller's persisted Central conversation/tool results are deliberately not copied to audio.
    await adapters[1].queue.put(SimpleNamespace(type="conversation.item.input_audio_transcription.completed", item_id="repeated", transcript="Bonjour"))
    event = await anext(wrapper.events())
    assert event.item_id == "r2:repeated"
    now[0] = 6000
    assert await wrapper.renew_if_due()
    assert len(adapters) == 3 and auth.await_count >= 5
    await wrapper.close()


@pytest.mark.asyncio
async def test_revoked_permission_prevents_session_renewal():
    now = [0.0]
    auth = AsyncMock()
    adapter = Adapter()
    wrapper = RotatingRealtimeAdapter(lambda: adapter, auth, clock=lambda: now[0])
    await wrapper.open(locale="es")
    now[0] = 3000
    auth.side_effect = PermissionError("Revoked")
    with pytest.raises(PermissionError):
        await wrapper.renew_if_due()
    assert adapter.open.await_count == 1
    await wrapper.close()


def test_short_sandbox_trial_is_explicitly_separate_from_commercial_default(setup):
    assert setup.settings.voice_commercial_max_call_seconds == 3600
    from backend.app.voice.sandbox_deadline import PRODUITS_ID, PRODUITS_CONFIG_ID, CONNECTION_ID
    call = SimpleNamespace(company_id=PRODUITS_ID, config_id=PRODUITS_CONFIG_ID)
    setup.settings.environment = "sandbox"
    setup.settings.telnyx_voice_connection_id = CONNECTION_ID
    assert is_sandbox_test_call(call, setup.settings)
    setup.settings.voice_sandbox_test_guard_enabled = False
    assert not is_sandbox_test_call(call, setup.settings)
