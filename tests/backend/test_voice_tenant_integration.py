"""Cross-PR regressions: live tenant grants and explicit locale authority."""
from types import SimpleNamespace
from uuid import uuid4
import pytest
from sqlalchemy.orm import Session
from backend.app.models import CompanyMembership
from backend.app.services.tenant_locale_service import upsert_profile
from backend.app.voice.module_actions import company_call_language_session, voice_agent_language
from backend.app.voice.tool_guard import VoiceToolDenied, VoiceToolGuard
from backend.app.voice.language_resolver import CallLanguageSession
from backend.app.core.permissions import permissions_for
from backend.app.models import UserRole
from tests.backend.test_voice_module_permissions import _engine, _company, _activate, _grant, BOOKING


def test_tenant_profile_overrides_stale_config_and_call_metadata(tmp_path):
    engine = _engine(tmp_path, "profile.db")
    with Session(engine) as db:
        company, _ = _company(db, "profile")
        config = SimpleNamespace(company_id=company.id, preferred_language="en")
        upsert_profile(db, company.id, primary_locale="ro", secondary_locales=[])
        call = SimpleNamespace(company_id=company.id, id=uuid4(), source_context={
            "allowed_locales": ["en-US", "fr-CA"],
            "call_language_session": {"active_locale": "en-US"},
        })
        assert voice_agent_language(db, config) == "ro"
        lock = company_call_language_session(db, config, call)
        assert lock.primary_locale == lock.active_locale == "ro-RO"
        assert lock.allowed_locales == ("ro-RO",)
        for _ in range(4):
            assert lock.process_utterance("Can we speak English please") == "ro-RO"
        upsert_profile(db, company.id, primary_locale="ro", secondary_locales=["en"])
        lock = company_call_language_session(db, config, call)
        assert lock.process_utterance("Can we speak English please") == "en-US"
        call.company_id = uuid4()
        with pytest.raises(PermissionError):
            company_call_language_session(db, config, call)
    engine.dispose()


def test_language_lock_never_adds_secondary_or_implicitly_escapes_allowlist(monkeypatch):
    lock = CallLanguageSession(uuid4(), "test-only-call", "fr", "fr", ())
    assert lock.allowed_locales == ("fr-CA",)
    monkeypatch.setattr("backend.app.voice.language_resolver.detect_spoken_language",
        lambda *args, **kwargs: SimpleNamespace(locale="en", confidence=1.0))
    for _ in range(5):
        assert lock.process_utterance("This is clearly a sentence in English") == "fr-CA"


def test_retell_read_guard_rechecks_revoked_membership(tmp_path):
    engine = _engine(tmp_path, "revoke.db")
    with Session(engine) as db:
        company, owner = _company(db, "revoke")
        tenant = _activate(db, company, "voice", "crm")
        _grant(db, company, BOOKING, owner.id)
        db.commit()
        guard = VoiceToolGuard(db)
        guard.authorize(tenant, "check_availability", permissions_for(UserRole.OWNER), user_id=owner.id)
        from sqlalchemy import select
        row = db.scalar(select(CompanyMembership).where(CompanyMembership.user_id == owner.id))
        row.is_active = False
        db.commit()
        with pytest.raises(VoiceToolDenied):
            guard.authorize(tenant, "check_availability", permissions_for(UserRole.OWNER), user_id=owner.id)
    engine.dispose()


def test_voice_grant_revoked_in_another_transaction_blocks_cached_session(tmp_path):
    from sqlalchemy import select, update
    from backend.app.models import VoiceModulePermission
    engine = _engine(tmp_path, "concurrent-revoke.db")
    with Session(engine) as db:
        company, owner = _company(db, "external-revoke")
        tenant = _activate(db, company, "voice", "crm")
        _grant(db, company, BOOKING, owner.id)
        db.commit()
        retained_grant = db.scalar(select(VoiceModulePermission).where(
            VoiceModulePermission.company_id == company.id,
            VoiceModulePermission.action_code == "read_availability",
        ))
        guard = VoiceToolGuard(db)
        guard.authorize(tenant, "check_availability", permissions_for(UserRole.OWNER), user_id=owner.id)
        with Session(engine) as other:
            other.execute(update(VoiceModulePermission).where(VoiceModulePermission.id == retained_grant.id).values(granted=False))
            other.commit()
        with pytest.raises(VoiceToolDenied):
            guard.authorize(tenant, "check_availability", permissions_for(UserRole.OWNER), user_id=owner.id)
    engine.dispose()


def test_voice_subscription_canceled_in_another_transaction_blocks_next_tool(tmp_path):
    from sqlalchemy import update
    from backend.app.models import BillingAccount
    engine = _engine(tmp_path, "subscription-revoke.db")
    with Session(engine) as db:
        company, owner = _company(db, "subscription-revoke")
        tenant = _activate(db, company, "voice", "crm")
        _grant(db, company, BOOKING, owner.id)
        db.commit()
        guard = VoiceToolGuard(db)
        guard.authorize(tenant, "check_availability", permissions_for(UserRole.OWNER), user_id=owner.id)
        with Session(engine) as other:
            other.execute(update(BillingAccount).where(BillingAccount.company_id == company.id).values(status="canceled"))
            other.commit()
        with pytest.raises(VoiceToolDenied, match="subscription"):
            guard.authorize(tenant, "check_availability", permissions_for(UserRole.OWNER), user_id=owner.id)
    engine.dispose()


def test_public_greeting_uses_explicit_profile_instead_of_stale_voice_config(tmp_path, monkeypatch):
    from backend.app.voice.telnyx_media import PublicInboundConversation
    engine = _engine(tmp_path, "greeting-profile.db")
    with Session(engine) as db:
        company, _ = _company(db, "greeting-profile")
        upsert_profile(db, company.id, primary_locale="ro", secondary_locales=[])
        config = SimpleNamespace(company_id=company.id, preferred_language="en", business_name="Test Only Company")
        conversation = PublicInboundConversation(db, SimpleNamespace(), uuid4())
        monkeypatch.setattr(conversation, "context", lambda: (SimpleNamespace(), config, company))
        greeting = conversation.greeting()
        assert "Test Only Company" in greeting and "Hello" not in greeting and "Bonjour" not in greeting
    engine.dispose()
