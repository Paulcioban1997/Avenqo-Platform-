from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import Base, VoiceBusinessConfig, VoicePhoneNumber, VoiceCall
from backend.app.voice import sandbox_deadline as guard
from scripts.voice_sandbox_scenarios import prepare_scenarios


def test_elapsed_call_budget_is_not_reset_by_media_reconnect():
    start = datetime(2026, 10, 13, tzinfo=timezone.utc)
    assert guard.remaining_seconds(start, now=start + timedelta(seconds=35)) == 55
    assert guard.remaining_seconds(start, now=start + timedelta(seconds=89)) == 1
    assert guard.remaining_seconds(start, now=start + timedelta(seconds=90)) == 0
    assert guard.remaining_seconds(None, now=start) == 0
    assert guard.remaining_seconds(start + timedelta(hours=1), now=start) == 90


def test_produits_deadline_matches_exact_tenant_agent_and_sandbox_connection():
    settings = SimpleNamespace(environment="sandbox", telnyx_voice_connection_id=guard.CONNECTION_ID)
    call = SimpleNamespace(company_id=guard.PRODUITS_ID, config_id=guard.PRODUITS_CONFIG_ID)
    assert guard.is_sandbox_test_call(call, settings)
    call.config_id = guard.CONFIG_ID
    assert not guard.is_sandbox_test_call(call, settings)
    call.config_id = guard.PRODUITS_CONFIG_ID
    settings.environment = "production"
    assert not guard.is_sandbox_test_call(call, settings)
    settings.environment = "sandbox";settings.telnyx_voice_connection_id = "foreign-connection"
    assert not guard.is_sandbox_test_call(call, settings)


@pytest.fixture
def calls(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path/'deadline.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    with Session(engine) as db:
        tenants = prepare_scenarios(db, environment="test")
        garage, _ = tenants["garage-montreal"]
        other, _ = tenants["ecommerce-english"]
        config = db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == garage.id))
        other_config = db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == other.id))
        monkeypatch.setattr(guard, "GARAGE_ID", garage.id)
        monkeypatch.setattr(guard, "CONFIG_ID", config.id)
        db.add(VoicePhoneNumber(company_id=garage.id, config_id=config.id, phone_number=guard.PHONE,
            country_code="CA", number_type="local", provider="telnyx", status="ACTIVE",
            capabilities=["voice"], provider_connection_id=guard.CONNECTION_ID))
        call = VoiceCall(company_id=garage.id, config_id=config.id, status="in_progress",
            caller_phone="synthetic", telnyx_call_control_id="synthetic-control",
            started_at=datetime.now(timezone.utc)-timedelta(seconds=91))
        foreign = VoiceCall(company_id=other.id, config_id=other_config.id, status="in_progress",
            caller_phone="synthetic", telnyx_call_control_id="foreign-control",
            started_at=call.started_at)
        db.add_all([call, foreign]); db.commit()
        ids = call.id, foreign.id
    yield factory, ids
    engine.dispose()


@pytest.mark.asyncio
async def test_expired_call_without_media_stops_once_and_preserves_other_tenant(calls):
    factory, (id, other) = calls
    client = SimpleNamespace(hangup=AsyncMock())
    settings = SimpleNamespace(environment="sandbox", telnyx_voice_connection_id=guard.CONNECTION_ID)
    assert await guard.stop_expired_call(id, session_factory=factory, settings=settings, client=client)
    assert not await guard.stop_expired_call(id, session_factory=factory, settings=settings, client=client)
    client.hangup.assert_awaited_once_with("synthetic-control")
    with factory() as db:
        assert db.get(VoiceCall, id).ended_at is not None
        assert db.get(VoiceCall, other).ended_at is None


@pytest.mark.asyncio
async def test_failure_never_claims_call_ended_and_foreign_or_production_is_denied(calls):
    factory, (id, other) = calls
    client = SimpleNamespace(hangup=AsyncMock(side_effect=RuntimeError("Synthetic provider failure")))
    settings = SimpleNamespace(environment="sandbox", telnyx_voice_connection_id=guard.CONNECTION_ID)
    with pytest.raises(RuntimeError):
        await guard.stop_expired_call(id, session_factory=factory, settings=settings, client=client)
    with factory() as db:
        assert db.get(VoiceCall, id).ended_at is None
    client.hangup.reset_mock()
    with pytest.raises(PermissionError):
        await guard.stop_expired_call(other, session_factory=factory, settings=settings, client=client)
    settings.environment = "production"
    with pytest.raises(PermissionError):
        await guard.stop_expired_call(id, session_factory=factory, settings=settings, client=client)
    client.hangup.assert_not_awaited()


@pytest.mark.asyncio
async def test_sandbox_media_hangup_failure_preserves_open_call_for_watchdog(monkeypatch):
    from backend.app.voice import telnyx_media as media
    call = SimpleNamespace(company_id=guard.GARAGE_ID, config_id=guard.CONFIG_ID,
        telnyx_call_control_id="synthetic-control", status="in_progress", ended_at=None)
    monkeypatch.setattr(media, "media_transport_context", lambda *a, **kw: (call, None, None))
    monkeypatch.setattr(media, "TelnyxClient", lambda settings: SimpleNamespace(
        hangup=AsyncMock(side_effect=RuntimeError("Synthetic failure"))))
    db = SimpleNamespace(commit=lambda: pytest.fail("Must not commit a false termination"))
    with pytest.raises(RuntimeError):
        await media.complete_media_hangup(db, SimpleNamespace(environment="sandbox", telnyx_voice_connection_id=guard.CONNECTION_ID), "synthetic-id")
    assert call.ended_at is None and call.status == "in_progress"


def test_live_calls_bypass_synthetic_test_deadline_guard():
    """Regression test: live calls from real callers or dispatcher routing must never
    be classified as synthetic test calls, preventing 90s or 0.001s test overrides.
    """
    settings = SimpleNamespace(
        environment="sandbox",
        telnyx_voice_connection_id=guard.CONNECTION_ID,
        voice_sandbox_test_guard_enabled=True,
    )

    # 1. Dispatcher routed live call with real phone number -> Must NOT be test call
    live_call = SimpleNamespace(
        company_id=guard.PRODUITS_ID,
        config_id=guard.PRODUITS_CONFIG_ID,
        caller_phone="+15149876543",
        source_context={"dispatcher_routing": True, "routing_nip": True, "live_call": True},
    )
    assert not guard.is_sandbox_test_call(live_call, settings)

    # 2. Live call with real phone number without dispatcher routing -> Must NOT be test call
    direct_live_call = SimpleNamespace(
        company_id=guard.PRODUITS_ID,
        config_id=guard.PRODUITS_CONFIG_ID,
        caller_phone="+14385550199",
        source_context={"live_call": True},
    )
    assert not guard.is_sandbox_test_call(direct_live_call, settings)

    # 3. Synthetic test call -> Must be classified as test call for test runners
    synthetic_call = SimpleNamespace(
        company_id=guard.PRODUITS_ID,
        config_id=guard.PRODUITS_CONFIG_ID,
        caller_phone="synthetic",
        source_context={},
    )
    assert guard.is_sandbox_test_call(synthetic_call, settings)

    # 4. Bare test namespace (from legacy test fixtures) -> Must still pass for backward compatibility
    bare_test_call = SimpleNamespace(
        company_id=guard.PRODUITS_ID,
        config_id=guard.PRODUITS_CONFIG_ID,
    )
    assert guard.is_sandbox_test_call(bare_test_call, settings)

