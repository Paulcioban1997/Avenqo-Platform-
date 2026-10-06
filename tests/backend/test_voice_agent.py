from __future__ import annotations

import asyncio
import base64
import hashlib
import json
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
from backend.app.routers.voice import voice_central_agent
from backend.app.routers.voice import get_voice_capabilities
from backend.app.schemas.voice import VoiceConfigRequest, VoiceToolRequest
from backend.app.voice.service import VoiceOrchestrator, _api_key_hash
from shared.ai_engine.contracts import TenantContext
from backend.app.core.locale_catalog import BY_LOCALE, resolve_locale
from backend.app.core.rate_limit import reset_rate_limiter
from backend.app.voice.auth import VoiceCallerAuth
from backend.app.config.settings import get_settings
from backend.app.database import get_db
from fastapi import FastAPI
from fastapi.testclient import TestClient
import backend.app.routers.voice as voice_router


class _FakeVoiceProvider:
    async def validate_agent(self, agent_id: str) -> None:
        if agent_id != "agent-test":
            raise ValueError("unknown agent")

    def inbound_target(self, config: VoiceBusinessConfig) -> str:
        return config.retell_sip_uri

    def agent_instructions(self, config: VoiceBusinessConfig) -> str:
        return f"Bonjour, {config.business_name}, assistant virtuel, cet appel peut être enregistré."


@pytest.mark.parametrize("caller_type,role,agent,tool,allowed,confirmed", [
    ("OWNER", UserRole.OWNER, "retail", "get_sales_summary", True, True),
    ("OWNER", UserRole.OWNER, "crm", "get_crm_metrics", True, True),
    ("OWNER", UserRole.OWNER, "accounting", "get_unpaid_invoices", True, True),
    ("OWNER", UserRole.OWNER, "crm", "create_appointment", True, False),
    ("EMPLOYEE", UserRole.ANALYST, "retail", "get_sales_summary", True, True),
    ("EMPLOYEE", UserRole.VIEWER, "accounting", "get_unpaid_invoices", False, True),
    ("CLIENT", UserRole.OWNER, "retail", "get_sales_summary", False, True),
    ("CUSTOMER", UserRole.OWNER, "tenant_capabilities", "get_subscription_options", False, True),
    ("UNKNOWN", UserRole.OWNER, "crm", "get_crm_metrics", False, True),
])
def test_native_voice_bridge_uses_membership_permissions_and_blocks_customers(tmp_path, caller_type, role, agent, tool, allowed, confirmed):
    engine, session, company, config, api_key, orchestrator = _voice_database(tmp_path)
    try:
        user = User(company_id=company.id, first_name="Verified", last_name="Caller",
            email="verified-native@example.com", password_hash="test", role=role, phone="+15145550123", is_active=True)
        session.add(user); session.flush()
        session.add_all([
            CompanyMembership(company_id=company.id, user_id=user.id, role=role, is_active=True),
            BillingAccount(company_id=company.id, plan_code="professional", status="active"),
        ])
        session.commit()
        call = orchestrator.record_inbound(config, {"call_control_id": "native-agent-call", "from": "+15145550123"})
        call.caller_type = caller_type; call.authenticated_user_id = user.id
        call.caller_verified_at = datetime.now(timezone.utc); session.commit()
        if caller_type in {"OWNER", "EMPLOYEE"}:
            VoiceCallerAuth(session, Settings()).establish(call)
            session.commit()

        class Central:
            calls = []

            async def execute(self, tenant, user_id, conversation_id, query, **kwargs):
                self.calls.append((tenant, user_id, conversation_id, kwargs))
                return SimpleNamespace(status="success", answer="Backend-grounded answer", selected_agent=agent,
                    remaining_ai_credits=100, tool_outcomes=({"tool": tool, "success": True, "confirmed": confirmed},))

        central = Central()
        request = VoiceToolRequest(call_id=call.telnyx_call_control_id, action_id="native-once",
            arguments={"question": "Business question", "plan": "enterprise", "tenant_id": str(uuid4()), "permissions": ["billing:manage"]})
        result = asyncio.run(voice_central_agent(request, api_key, session, Settings(), central, None))
        assert result["success"] is (allowed and confirmed)
        if allowed:
            from backend.app.core.permissions import permissions_for
            assert result["selected_agent"] == agent
            assert central.calls[0][0] == TenantContext(company.id, user.id)
            assert central.calls[0][3]["permissions"] == frozenset(permissions_for(role))
            replay = asyncio.run(voice_central_agent(request, api_key, session, Settings(), central, None))
            assert replay == result and len(central.calls) == 1
        else:
            assert central.calls == []
            assert "answer" not in result and "remaining_ai_credits" not in result
    finally:
        session.close(); engine.dispose()


class _FakeTelnyx:
    def __init__(self) -> None:
        self.transfers: list[tuple[str, str]] = []
        self.messages: list[tuple[str, str]] = []
        self.gathers = []
        self.commands = []
        self.fail_transfer = False

    async def answer_call(self, call_control_id: str, *, command_id: str) -> None:
        self.commands.append(("answer", call_control_id, command_id))

    async def transfer_call(self, call_control_id: str, destination: str, caller_id: str | None = None, *, command_id: str | None = None, call_reference: str | None = None) -> None:
        if self.fail_transfer:
            raise RuntimeError("test-secret-never-log")
        self.transfers.append((call_control_id, destination))
        self.commands.append(("transfer", call_control_id, command_id))

    async def hangup(self, call_control_id: str) -> None:
        return None

    async def gather_pin(self, call_control_id: str, *, command_id: str, client_state: str) -> None:
        self.gathers.append((call_control_id, command_id, client_state))

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


def test_voice_greeting_uses_every_canonical_locale_without_claiming_audio_support():
    greetings = {locale: VoiceOrchestrator.greeting_for("Tenant Example", locale) for locale in BY_LOCALE}
    assert len(greetings) == len(BY_LOCALE)
    assert all("Tenant Example" in greeting and greeting.strip() for greeting in greetings.values())
    assert greetings["en"].startswith("Hello, Tenant Example.")
    assert greetings["fr"].startswith("Bonjour, Tenant Example.")
    assert greetings["ro"].startswith("Bună ziua, Tenant Example.")


@pytest.mark.parametrize("principal_type", ["USER", "CUSTOMER"])
def test_pin_hash_call_scope_expiration_lockout_and_customer_isolation(tmp_path, principal_type, caplog):
    from backend.app.models import VoiceAuthSession, VoiceCallerCredential
    engine, session, company, config, _key, orchestrator = _voice_database(tmp_path)
    try:
        if principal_type == "USER":
            principal = User(company_id=company.id, first_name="Owner", last_name="Pin", email="pin-owner@example.com",
                password_hash="test", role=UserRole.OWNER, phone="+15145550123", is_active=True)
            session.add(principal); session.flush()
            session.add(CompanyMembership(company_id=company.id, user_id=principal.id, role=UserRole.OWNER, is_active=True))
        else:
            principal = CRMClient(company_id=company.id, first_name="Client", last_name="Pin", email="pin-client@example.com", phone="+15145550123")
            session.add(principal); session.flush()
        controller = VoiceCallerAuth(session, Settings(AUTH_JWT_SECRET="test-pepper-at-least-32-characters"))
        credential = controller.set_pin(TenantContext(company.id), principal_type, principal.id, "654321")
        session.commit()
        assert credential.pin_hash.startswith("$argon2") and "654321" not in credential.pin_hash
        call = orchestrator.record_inbound(config, {"call_control_id": "pin-call", "from": principal.phone})
        assert controller.valid_session(call) is None
        assert controller.verify_gather(call, "123456") == {"success": False, "authenticated": False, "error": "caller_authentication_failed"}
        assert controller.verify_gather(call, 654321) == {"success": False, "authenticated": False, "error": "caller_authentication_failed"}
        assert controller.valid_session(call) is None
        result = controller.verify_gather(call, "654321"); session.commit()
        assert result == {"success": True, "authenticated": True}
        authenticated = controller.valid_session(call)
        assert authenticated.call_id == call.id and authenticated.company_id == company.id
        assert authenticated.principal_id == principal.id
        if principal_type == "CUSTOMER":
            assert authenticated.permissions == ["customer:self"] and authenticated.caller_type == "CUSTOMER"
            call.verified_client_id = uuid4()
            assert controller.valid_session(call) is None
            call.verified_client_id = principal.id
        another = orchestrator.record_inbound(config, {"call_control_id": "pin-other-call", "from": principal.phone})
        assert controller.valid_session(another) is None
        authenticated.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1); session.flush()
        assert controller.valid_session(call) is None
        for _attempt in range(5): controller.verify_gather(another, "111111")
        session.commit()
        assert credential.locked_until is not None
        third = orchestrator.record_inbound(config, {"call_control_id": "pin-third-call", "from": principal.phone})
        assert controller.verify_gather(third, "654321")["authenticated"] is False
        assert "654321" not in caplog.text + str(result) + str(authenticated.permissions)
        assert session.scalar(select(func.count(VoiceCallerCredential.id))) == 1
        assert session.scalar(select(func.count(VoiceAuthSession.id))) == 1
    finally:
        session.close(); engine.dispose()


@pytest.mark.parametrize("state", [None, "bad-base64", "A" * 1025, "W10=", "bnVsbA==", "MQ==", "eyJ2b2ljZV9waW5fY2hhbGxlbmdlIjoxfQ=="])
def test_pin_challenge_malformed_values_fail_closed(tmp_path, state):
    engine, session, _company, config, _key, orchestrator = _voice_database(tmp_path)
    try:
        call = orchestrator.record_inbound(config, {"call_control_id": "malformed-pin-call", "from": "+15145550123"})
        call.status = "routed"
        auth = VoiceCallerAuth(session, Settings())
        valid = auth.challenge(call)
        assert auth.valid_challenge(call, valid)
        assert auth.valid_challenge(call, state) is False
        assert auth.valid_session(call) is None
    finally:
        session.close(); engine.dispose()


def test_tenant_configuration_can_exist_without_fabricated_retell(tmp_path):
    engine, session, company, config, _key, orchestrator = _voice_database(tmp_path)
    try:
        session.delete(config); session.commit()
        number = VoicePhoneNumber(company_id=company.id, phone_number="+14385550123", country_code="CA",
            provider="telnyx", provider_number_id="owned-number", number_type="local", status="ACTIVE", capabilities=["voice"])
        session.add(number); session.commit()
        request = VoiceConfigRequest(business_name=company.name, timezone_name=company.timezone,
            telnyx_phone_number=number.phone_number, preferred_language="ro")
        result, _secret = asyncio.run(orchestrator.upsert_config(TenantContext(company.id), request.model_dump(mode="json")))
        assert result.retell_agent_id is None and result.retell_sip_uri is None and result.enabled is False
        assert number.config_id == result.id
        same, revealed = asyncio.run(orchestrator.upsert_config(TenantContext(company.id), request.model_dump(mode="json")))
        assert same.id == result.id and revealed is None
        assert session.scalar(select(func.count(VoiceBusinessConfig.id))) == 1
        with pytest.raises(ValueError):
            VoiceConfigRequest(business_name=company.name, telnyx_phone_number=number.phone_number, enabled=True)
    finally:
        session.close(); engine.dispose()


def test_voice_action_replay_is_bound_to_call_and_tool_and_preserves_legacy_history(tmp_path, monkeypatch):
    from backend.app.models import VoiceToolAction
    engine, session, _company, config, _, orchestrator = _voice_database(tmp_path)
    try:
        first_call = orchestrator.record_inbound(config, {"call_control_id": "call-first", "from": "+15145550123"})
        second_call = orchestrator.record_inbound(config, {"call_control_id": "call-second", "from": "+15145550124"})
        dispatched = []

        async def dispatch(_config, call, tool, arguments):
            dispatched.append((call.id, tool))
            return {"success": True, "call_id": str(call.id), "tool": tool}

        monkeypatch.setattr(orchestrator, "_dispatch_tool", dispatch)
        first = asyncio.run(orchestrator.execute_tool(config, "call-first", "shared-id", "get_business_info", {}))
        replay = asyncio.run(orchestrator.execute_tool(config, "call-first", "shared-id", "get_business_info", {}))
        other_call = asyncio.run(orchestrator.execute_tool(config, "call-second", "shared-id", "get_business_info", {}))
        other_tool = asyncio.run(orchestrator.execute_tool(config, "call-first", "shared-id", "take_message", {}))
        assert replay == first
        assert first["call_id"] == str(first_call.id) and other_call["call_id"] == str(second_call.id)
        assert other_tool["tool"] == "take_message" and len(dispatched) == 3
        legacy = VoiceToolAction(company_id=config.company_id, config_id=config.id,
            action_id="legacy-unbound", tool_name="get_business_info", result={"success": True, "private": "do-not-replay"})
        session.add(legacy); session.commit()
        denied = asyncio.run(orchestrator.execute_tool(config, "call-second", "legacy-unbound", "get_business_info", {}))
        assert denied == {"success": False, "error": "legacy_action_context_unavailable"}
        assert legacy.result == {"success": True, "private": "do-not-replay"}
        assert len(dispatched) == 3
    finally:
        session.close(); engine.dispose()


@pytest.mark.parametrize("role", [UserRole.OWNER, UserRole.ANALYST, UserRole.VIEWER])
def test_native_capabilities_handler_uses_server_identity_and_membership(tmp_path, role):
    from fastapi import HTTPException
    from backend.app.ai.central.context import CentralAIContextBuilder
    from backend.app.ai.usage.service import AIUsageService
    from backend.app.ai.usage.policy import AIQuotaPolicy
    from backend.app.services.module_entitlement_service import ModuleEntitlementService
    from backend.app.assistants.registry import build_default_assistant_registry
    from backend.app.core.permissions import permissions_for
    engine, session, company, _config, _, _ = _voice_database(tmp_path)
    try:
        user = User(company_id=company.id, first_name="Capability", last_name="Owner", email="capability-owner@example.com",
            password_hash="test", role=UserRole.OWNER, is_active=True)
        session.add(user)
        session.add(BillingAccount(company_id=company.id, plan_code="professional", status="active"))
        session.commit()
        builder = CentralAIContextBuilder(ModuleEntitlementService(session),
            AIUsageService(session, AIQuotaPolicy(Settings(AUTH_JWT_SECRET="a" * 32))),
            build_default_assistant_registry(), lambda tenant: {"tenant_id": str(tenant.company_id), "sources": []})

        class Central:
            calls = []

            def capability_context(self, tenant, user_id, **kwargs):
                self.calls.append((tenant, user_id, kwargs))
                return builder.build(tenant, user_id, **kwargs)

        central = Central()
        if role == UserRole.VIEWER:
            with pytest.raises(HTTPException) as denied:
                get_voice_capabilities(SimpleNamespace(user=user), SimpleNamespace(role=role), central)
            assert denied.value.status_code == 403
            assert central.calls == []
        else:
            data = get_voice_capabilities(SimpleNamespace(user=user), SimpleNamespace(role=role), central)
            assert data["tenant_id"] == str(company.id)
            assert data["subscription_plan"] == "professional"
            assert data["permissions"] == sorted(permissions_for(role))
            assert data["locale"] == company.preferred_language
            assert data["timezone"] == company.timezone
            assert len(data["language_matrix"]) == 44
            assert data["authorized_sources"]["tenant_id"] == str(company.id)
    finally:
        session.close(); engine.dispose()


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


def test_pin_authentication_tool_requests_keypad_without_returning_or_forwarding_a_pin(tmp_path):
    engine, session, _company, config, _key, orchestrator = _voice_database(tmp_path)
    try:
        call = orchestrator.record_inbound(config, {"call_control_id": "pin-tool-call", "from": "+15145550123"})
        call.status = "in_progress"; session.commit()
        result = asyncio.run(orchestrator._dispatch_tool(config, call, "request_pin_authentication", {"_action_id": "a" * 32}))
        assert result["success"] is True and result["authentication_pending"] is True
        assert len(orchestrator.telnyx.gathers) == 1
        control_id, command_id, state = orchestrator.telnyx.gathers[0]
        assert control_id == "pin-tool-call" and len(command_id) == 36
        assert VoiceCallerAuth(session, Settings()).valid_challenge(call, state)
        assert "pin" not in str(result).casefold() and "digits" not in str(result).casefold()
    finally:
        session.close(); engine.dispose()


def test_pin_setup_http_endpoint_is_self_scoped_strict_and_secret_free(tmp_path):
    from backend.app.models import VoiceCallerCredential
    engine, session, company, _config, _key, _service = _voice_database(tmp_path)
    try:
        user = User(company_id=company.id, first_name="Owner", last_name="PIN", email="pin-http@example.com",
            password_hash="test", role=UserRole.OWNER, phone="+15145550123", is_active=True)
        session.add(user); session.flush()
        membership = CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.OWNER, is_active=True)
        session.add_all([membership, BillingAccount(company_id=company.id, plan_code="professional", status="active")])
        session.commit()
        identity = SimpleNamespace(user=user)
        app = FastAPI(); app.include_router(voice_router.router, prefix="/api/v1")
        app.dependency_overrides[get_db] = lambda: session
        app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, AUTH_JWT_SECRET="test-pin-endpoint-secret-long-enough")
        app.dependency_overrides[voice_router.get_current_identity] = lambda: identity
        app.dependency_overrides[voice_router.get_active_ai_membership] = lambda: membership
        secret = "908172"
        with TestClient(app) as client:
            response = client.put("/api/v1/voice/auth/pin", json={"pin": secret})
            assert response.status_code == 200 and response.json() == {"status": "CONFIGURED"}
            assert secret not in response.text
            malformed = client.put("/api/v1/voice/auth/pin", json={"pin": secret, "company_id": str(uuid4())})
            assert malformed.status_code == 422 and secret not in malformed.text
        credential = session.scalar(select(VoiceCallerCredential).where(VoiceCallerCredential.company_id == company.id))
        assert credential.principal_id == user.id and credential.pin_hash.startswith("$argon2")
        assert secret not in credential.pin_hash
    finally:
        session.close(); engine.dispose()


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

            VoiceCallerAuth(session, Settings()).establish(call)
            session.commit()
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


def _authenticated_booking_calls(session, company, config, service, call_ids):
    from backend.app.services.module_entitlement_service import ModuleEntitlementService
    owner = User(company_id=company.id, first_name="Verified", last_name="Scheduler", email="scheduler@example.com",
        password_hash="test", phone="+15145550123", role=UserRole.OWNER, is_active=True)
    session.add(owner); session.flush()
    session.add_all([CompanyMembership(company_id=company.id, user_id=owner.id, role=UserRole.OWNER, is_active=True),
        BillingAccount(company_id=company.id, plan_code="professional", status="active")])
    session.flush()
    ModuleEntitlementService(session).activate_module(TenantContext(company.id), "crm")
    for call_id in call_ids:
        call = service._resolve_call(config, call_id, caller_phone=owner.phone)
        call.caller_type = "OWNER"; call.authenticated_user_id = owner.id; call.caller_verified_at = datetime.now(timezone.utc)
        VoiceCallerAuth(session, Settings()).establish(call)
    session.commit()


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
        _authenticated_booking_calls(session, company, config, service, ["retell-retry-call"])
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
        _authenticated_booking_calls(session, company, config, service, [f"retell-call-{index}" for index in range(100)])
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


@pytest.fixture
def signed_telnyx_webhook(tmp_path, monkeypatch):
    engine, session, company, config, _, service = _voice_database(tmp_path)
    private_key = Ed25519PrivateKey.generate()
    public = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    settings = Settings(_env_file=None, TELNYX_API_KEY="test-secret-never-log",
        TELNYX_PUBLIC_KEY=base64.b64encode(public).decode(), TELNYX_VOICE_CONNECTION_ID="test-connection",
        RATE_LIMIT_ENABLED=True, RATE_LIMIT_WEBHOOK_PER_MINUTE=100)
    binding = VoicePhoneNumber(company_id=company.id, config_id=config.id, phone_number=config.telnyx_phone_number,
        country_code="CA", provider="telnyx", number_type="local", status="ACTIVE", capabilities=["voice"])
    session.add_all([binding, BillingAccount(company_id=company.id, plan_code="professional", status="active")])
    session.commit()
    app = FastAPI()
    app.include_router(voice_router.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(voice_router, "_orchestrator", lambda _db, _settings: service)
    reset_rate_limiter()

    def event(kind="call.initiated", event_id=None, **payload):
        return {"data": {"id": event_id or str(uuid4()), "event_type": kind, "payload": {
            "call_control_id": "inbound-control", "connection_id": "test-connection", "direction": "incoming",
            "from": "+15145550123", "to": config.telnyx_phone_number, **payload,
        }}}

    with TestClient(app) as client:
        def send(envelope, timestamp=None, valid=True, raw=None):
            body = raw if raw is not None else json.dumps(envelope).encode()
            stamp = timestamp if timestamp is not None else str(int(time()))
            signature = private_key.sign(stamp.encode() + b"|" + body)
            if not valid:
                signature = bytes(64)
            return client.post("/api/v1/voice/telnyx/webhook", content=body, headers={
                "content-type": "application/json", "telnyx-timestamp": stamp,
                "telnyx-signature-ed25519": base64.b64encode(signature).decode(),
            })
        yield SimpleNamespace(send=send, event=event, session=session, settings=settings, config=config,
            binding=binding, company=company, service=service, client=client)
    reset_rate_limiter()
    session.close(); engine.dispose()


def test_signed_telnyx_called_number_routes_tenant_not_caller_and_no_unconfigured_commands(signed_telnyx_webhook):
    env = signed_telnyx_webhook
    owner = User(company_id=env.company.id, first_name="Owner", last_name="Example", email="called-owner@example.com",
        password_hash="test", role=UserRole.OWNER, is_active=True, phone="+15145550123")
    env.session.add(owner); env.session.commit()
    result = env.send(env.event(tenant_id=str(uuid4()), caller_type="OWNER"))
    assert result.status_code == 200 and result.json()["status"] == "READY_FOR_OWNER_ACTION"
    call = env.session.scalar(select(VoiceCall).where(VoiceCall.telnyx_call_control_id == "inbound-control"))
    assert call.company_id == env.company.id and call.config_id == env.config.id
    assert call.caller_type == "UNKNOWN" and call.authenticated_user_id is None
    assert call.status == "awaiting_configuration"
    assert env.service.telnyx.commands == []


@pytest.mark.parametrize("case", ["unknown_number", "wrong_connection", "outgoing", "inactive_binding", "unassigned", "wrong_config", "no_voice", "inactive_subscription", "inactive_module"])
def test_telnyx_readiness_rejects_wrong_binding_or_access_without_commands(signed_telnyx_webhook, case):
    env = signed_telnyx_webhook
    payload = {}
    if case == "unknown_number": payload["to"] = "+14165550999"
    elif case == "wrong_connection": payload["connection_id"] = "other-connection"
    elif case == "outgoing": payload["direction"] = "outgoing"
    elif case == "inactive_binding": env.binding.status = "RELEASED"
    elif case == "unassigned": env.binding.config_id = None
    elif case == "wrong_config": env.binding.config_id = uuid4()
    elif case == "no_voice": env.binding.capabilities = ["sms"]
    elif case == "inactive_subscription": env.session.scalar(select(BillingAccount)).status = "past_due"
    else: env.session.scalar(select(CompanyModule)).status = CompanyModuleStatus.INACTIVE
    env.session.commit()
    response = env.send(env.event(**payload))
    assert response.status_code == 200 and response.json()["routed"] is False
    assert env.session.scalar(select(func.count(VoiceCall.id))) == 0
    assert env.service.telnyx.commands == []


@pytest.mark.parametrize("timestamp,valid,expected", [(None, False, 401), ("nan", True, 401), ("inf", True, 401), ("expired", True, 401), ("future", True, 401)])
def test_signed_webhook_signature_and_replay_fail_closed(signed_telnyx_webhook, timestamp, valid, expected):
    env = signed_telnyx_webhook
    if timestamp == "expired": timestamp = str(int(time()) - 3600)
    if timestamp == "future": timestamp = str(int(time()) + 3600)
    response = env.send(env.event(), timestamp=timestamp, valid=valid)
    assert response.status_code == expected
    assert env.session.scalar(select(func.count(VoiceCall.id))) == 0
    assert env.service.telnyx.commands == []


def test_telnyx_event_idempotency_answer_then_transfer_and_terminal_lifecycle(signed_telnyx_webhook):
    env = signed_telnyx_webhook
    env.settings.retell_api_key = "test-retell-configured"
    initiated = env.event()
    assert env.send(initiated).json()["status"] == "answering"
    assert env.send(initiated).json()["duplicate"] is True
    assert env.send(env.event()).json()["duplicate"] is True
    assert [item[0] for item in env.service.telnyx.commands] == ["answer"]
    answered = env.event("call.answered")
    assert env.send(answered).json()["routed"] is True
    assert env.send(answered).json()["duplicate"] is True
    assert [item[0] for item in env.service.telnyx.commands] == ["answer", "transfer"]
    assert len({item[2] for item in env.service.telnyx.commands}) == 2
    call = env.session.scalar(select(VoiceCall))
    env.send(env.event("call.bridged"))
    env.session.refresh(call); assert call.status == "in_progress"
    hangup = env.event("call.hangup")
    assert env.send(hangup).status_code == 200
    env.session.refresh(call); ended_at = call.ended_at
    assert ended_at is not None and call.status == "ended"
    assert env.send(hangup).json()["duplicate"] is True
    env.send(env.event("call.answered")); env.send(env.event("call.bridged")); env.send(env.event())
    env.session.refresh(call)
    assert call.ended_at == ended_at and call.status == "ended"
    assert len(env.service.telnyx.commands) == 2


def test_telnyx_hangup_preserves_booking_state_but_ends_private_call_access(signed_telnyx_webhook):
    env = signed_telnyx_webhook
    env.send(env.event())
    call = env.session.scalar(select(VoiceCall))
    call.status = "appointment_booked"; env.session.commit()
    assert env.send(env.event("call.hangup")).status_code == 200
    env.session.refresh(call)
    assert call.status == "appointment_booked" and call.ended_at is not None
    result = asyncio.run(env.service.execute_tool(env.config, "inbound-control", "after-hangup", "get_business_info", {}))
    assert result == {"success": False, "error": "voice_call_not_active"}


def test_telnyx_event_collision_and_call_collision_do_not_cross_context(signed_telnyx_webhook):
    env = signed_telnyx_webhook
    original = env.event()
    env.send(original)
    reused = env.event(event_id=original["data"]["id"], call_control_id="other-control")
    assert env.send(reused).json()["routed"] is False
    assert env.session.scalar(select(func.count(VoiceCall.id))) == 1
    other_company = Company(name="Other Telnyx Tenant", slug="other-telnyx", email="other-telnyx@example.com",
        country="CA", timezone="America/Toronto", industry="Retail", subscription_plan="professional")
    env.session.add(other_company); env.session.flush()
    foreign = VoiceCall(company_id=other_company.id, config_id=env.config.id,
        telnyx_call_control_id="foreign-control", caller_phone="unknown", status="incoming")
    env.session.add(foreign); env.session.commit()
    assert env.send(env.event(call_control_id="foreign-control")).json()["routed"] is False
    env.session.refresh(foreign)
    assert foreign.company_id == other_company.id and foreign.status == "incoming"


def test_telnyx_unknown_dtmf_media_sms_are_not_forwarded_or_persisted(signed_telnyx_webhook, caplog):
    from backend.app.models import VoiceToolAction
    env = signed_telnyx_webhook
    for kind in ("call.dtmf.received", "streaming.started", "message.received"):
        response = env.send(env.event(kind, digits="test-pin-never-log", transcript="test-pin-never-log"))
        assert response.status_code == 200 and response.json()["handled"] is False
        assert "test-pin-never-log" not in response.text
    gather = env.send(env.event("call.gather.ended", digits="test-pin-never-log"))
    assert gather.status_code == 200 and gather.json()["routed"] is False
    assert env.session.scalar(select(func.count(VoiceCall.id))) == 0
    assert env.session.scalar(select(func.count(VoiceToolAction.id))) == 0
    assert env.service.telnyx.commands == []
    assert "test-pin-never-log" not in caplog.text


def test_signed_dtmf_gather_authenticates_customer_once_without_persisting_digits(signed_telnyx_webhook, caplog):
    from backend.app.models import VoiceAuthSession, VoiceToolAction
    env = signed_telnyx_webhook
    env.settings.retell_api_key = "test-retell-configured"
    client = CRMClient(company_id=env.company.id, first_name="Scoped", last_name="Customer",
        email="dtmf@example.com", phone="+15145550123")
    env.session.add(client); env.session.flush()
    controller = VoiceCallerAuth(env.session, env.settings)
    controller.set_pin(TenantContext(env.company.id), "CUSTOMER", client.id, "765432")
    env.session.commit()
    env.send(env.event()); env.send(env.event("call.answered"))
    call = env.session.scalar(select(VoiceCall))
    challenge = controller.challenge(call); env.session.commit()
    gathered = env.event("call.gather.ended", digits="765432", client_state=challenge)
    assert env.send(gathered).json()["authenticated"] is True
    assert env.send(gathered).json()["duplicate"] is True
    env.session.refresh(call)
    auth = controller.valid_session(call)
    assert auth.principal_id == client.id and auth.permissions == ["customer:self"]
    assert call.caller_type == "CLIENT" and call.authenticated_user_id is None
    receipts = env.session.scalars(select(VoiceToolAction)).all()
    assert "765432" not in str([item.result for item in receipts]) + caplog.text + str(call.transcript) + str(call.summary)
    assert env.session.scalar(select(func.count(VoiceAuthSession.id))) == 1
    assert call.pin_challenge_hash is None


def test_signed_dtmf_without_matching_challenge_never_authenticates(signed_telnyx_webhook):
    env = signed_telnyx_webhook
    env.settings.retell_api_key = "test-retell-configured"
    env.send(env.event()); env.send(env.event("call.answered"))
    response = env.send(env.event("call.gather.ended", digits="765432", client_state="foreign-challenge"))
    assert response.json()["authenticated"] is False
    call = env.session.scalar(select(VoiceCall))
    assert call.caller_type == "UNKNOWN" and VoiceCallerAuth(env.session, env.settings).valid_session(call) is None


def test_retell_webhook_correlates_only_to_existing_tenant_telnyx_call(signed_telnyx_webhook):
    env = signed_telnyx_webhook
    env.send(env.event())
    call = env.session.scalar(select(VoiceCall))
    payload = {"event": "call_started", "call": {"agent_id": env.config.retell_agent_id,
        "call_id": "retell-correlated-call", "from_number": "+15145550123",
        "custom_sip_headers": {"x-avenqo-call-id": str(call.id)}}}
    headers = {"x-avenqo-voice-key": "avqv_test_key_do_not_use_outside_tests"}
    response = env.client.post("/api/v1/voice/retell/webhook", json=payload, headers=headers)
    assert response.status_code == 200 and response.json() == {"received": True}
    env.session.refresh(call)
    assert call.retell_call_id == "retell-correlated-call" and call.status == "in_progress"
    unrelated = {"event": "call_started", "call": {"agent_id": env.config.retell_agent_id,
        "call_id": "retell-no-correlation", "from_number": call.caller_phone}}
    missing = env.client.post("/api/v1/voice/retell/webhook", json=unrelated, headers=headers)
    assert missing.status_code == 404
    foreign = dict(payload)
    foreign["call"] = {**payload["call"], "call_id": "retell-foreign-call", "custom_sip_headers": {"X-Avenqo-Call-ID": str(uuid4())}}
    assert env.client.post("/api/v1/voice/retell/webhook", json=foreign, headers=headers).status_code == 404


def test_telnyx_rate_limit_and_malformed_envelope(signed_telnyx_webhook):
    env = signed_telnyx_webhook
    assert env.send({}, raw=b"invalid-json").status_code == 400
    assert env.send([]).status_code == 400
    env.settings.rate_limit_webhook_per_minute = 2
    assert env.send(env.event()).status_code == 429
    assert env.service.telnyx.commands == []


def test_telnyx_provider_failure_is_generic_and_not_retried(signed_telnyx_webhook, caplog):
    env = signed_telnyx_webhook
    env.settings.retell_api_key = "test-retell-configured"
    env.send(env.event())
    env.service.telnyx.fail_transfer = True
    answered = env.event("call.answered")
    response = env.send(answered)
    assert response.status_code == 502
    assert "test-secret-never-log" not in response.text + caplog.text
    assert env.send(answered).json()["duplicate"] is True
    call = env.session.scalar(select(VoiceCall))
    assert call.status == "routing_outcome_unknown"
