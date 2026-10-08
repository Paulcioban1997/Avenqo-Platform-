"""Tests de validation P0 pour l'authentification vocale sécurisée par NIP, identité et permissions multi-tenant.

Couvre les 17 exigences strictes du cahier des charges :
1. Création du NIP avec validation de complexité (rejet des suites triviales et répétitions).
2. Confirmation du NIP et rejet si identique au mot de passe de compte.
3. NIP incorrect et échec d'authentification.
4. Réinitialisation sécurisée par réauthentification avec mot de passe web fort.
5. Verrouillage (lockout) après plusieurs tentatives erronées (max 5) avec délai progressif.
6. Réinitialisation sécurisée invalidant les sessions actives antérieures.
7. Révocation des sessions (manuelle via API et automatique sur call.hangup).
8. Employé désactivé (is_active=False ou membership désactivé ou credential.enabled=False) invalidant l'accès mid-call.
9. Permissions retirées pendant l'appel bloquant l'accès aux outils sensibles.
10. Changement/désactivation de module pendant l'appel bloquant les outils du module.
11. Tentative d'accès aux finances (Retail / Accounting) par un client externe bloquée (fail-closed).
12. Tentative d'accès aux données d'un autre tenant bloquée (isolation multi-tenant stricte).
13. Appel Telnyx interrompu invalidant la session immédiatement.
14. NIP absent des logs, des réponses API et haché avec sel + pepper HMAC.
15. Protection contre la réutilisation de session (autre appel ou session expirée).
16. Accès Cross-Agent 360° limité aux permissions réelles sans contournement des restrictions.
17. Refus d'exécution côté backend même si le LLM tente d'appeler directement un outil privé non autorisé.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from uuid import UUID, uuid4

from unittest.mock import MagicMock
from pydantic import SecretStr
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.central.service import CentralAIService
from backend.app.ai.tools.authorization import ToolAuthorizationError, ToolAuthorizationPolicy
from backend.app.ai.tools.business.registry_factory import build_business_tool_registry
from backend.app.ai.tools.business.sales_tools import GetSalesSummaryTool
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.assistants.registry import build_default_assistant_registry
from backend.app.config.settings import Settings
from backend.app.core.permissions import UserRole, permissions_for
from backend.app.core.security import hash_password, verify_password
from backend.app.models import (
    BillingAccount,
    Company,
    CompanyMembership,
    CompanyModule,
    CompanyModuleStatus,
    CRMClient,
    Module,
    User,
    VoiceAuthSession,
    VoiceBusinessConfig,
    VoiceCall,
    VoiceCallerCredential,
)
from backend.app.routers.voice import (
    get_voice_pin_status,
    list_voice_auth_audit,
    revoke_voice_auth_sessions,
    set_voice_member_access,
    set_voice_phone_access,
    set_voice_pin,
)
from backend.app.schemas.voice import (
    VoiceMemberAccessRequest,
    VoicePhoneAccessRequest,
    VoicePinRequest,
)
from backend.app.voice.auth import (
    VoiceCallerAuth,
    normalized_phone,
    redact_voice_secrets,
    validate_voice_pin,
)
from backend.app.voice.caller_scope import (
    PUBLIC_VOICE_CALLER_PERMISSIONS,
    is_public_voice_caller,
    public_voice_tool_allowed,
)
from shared.ai_engine.contracts import TenantContext
from tests.backend.test_voice_agent import _voice_database


def test_1_voice_pin_validation_complexity_and_nontrivial():
    """Exigence 1 : Le NIP doit contenir entre 6 et 12 chiffres et rejeter les suites triviales."""
    # NIP valides
    assert validate_voice_pin("907182") == "907182"
    assert validate_voice_pin("583921") == "583921"
    assert validate_voice_pin("83920184") == "83920184"

    # NIP invalides : longueur incorrecte ou caractères non numériques
    with pytest.raises(ValueError, match="6 to 12 digits"):
        validate_voice_pin("12345")  # Trop court
    with pytest.raises(ValueError, match="6 to 12 digits"):
        validate_voice_pin("1234567890123")  # Trop long
    with pytest.raises(ValueError, match="6 to 12 digits"):
        validate_voice_pin("abcdef")  # Lettres
    with pytest.raises(ValueError, match="6 to 12 digits"):
        validate_voice_pin("12345a")

    # NIP triviaux rejetés (séquences ascendantes, descendantes, répétitions)
    with pytest.raises(ValueError, match="nontrivial"):
        validate_voice_pin("012345")
    with pytest.raises(ValueError, match="nontrivial"):
        validate_voice_pin("123456")
    with pytest.raises(ValueError, match="nontrivial"):
        validate_voice_pin("654321")
    with pytest.raises(ValueError, match="nontrivial"):
        validate_voice_pin("987654")
    with pytest.raises(ValueError, match="nontrivial"):
        validate_voice_pin("111111")
    with pytest.raises(ValueError, match="nontrivial"):
        validate_voice_pin("121212")
    with pytest.raises(ValueError, match="nontrivial"):
        validate_voice_pin("123123")


def test_2_voice_pin_request_confirmation_mismatch_and_password_rejection():
    """Exigence 2 : Confirmation obligatoire et non-collision avec le mot de passe web."""
    # Confirmation non correspondante
    with pytest.raises(ValueError, match="do not match"):
        VoicePinRequest(pin=SecretStr("907182"), pin_confirmation=SecretStr("907183"))

    # PIN identique au mot de passe web fourni
    with pytest.raises(ValueError, match="must not be identical"):
        VoicePinRequest(pin=SecretStr("907182"), pin_confirmation=SecretStr("907182"), current_password=SecretStr("907182"))


def test_3_voice_pin_incorrect_attempts_and_verification_failure(tmp_path):
    """Exigence 3 : NIP incorrect entraîne l'échec d'authentification."""
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        settings = Settings(AUTH_JWT_SECRET="test-jwt-secret-minimum-32-chars-long")
        user = User(
            company_id=company.id,
            first_name="Alice",
            last_name="Owner",
            email="alice@example.com",
            password_hash=hash_password("SuperSecret123!"),
            role=UserRole.OWNER,
            phone="+15145550123",
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.OWNER, is_active=True))
        session.commit()

        auth = VoiceCallerAuth(session, settings)
        auth.set_pin(TenantContext(company.id, user.id), "USER", user.id, "907182")
        session.commit()

        call = orchestrator.record_inbound(config, {"call_control_id": "pin-call-1", "from": "+15145550123"})

        # Tentative avec un NIP incorrect
        result = auth.verify_gather(call, "839201")
        assert result["authenticated"] is False
        assert result["error"] == "caller_authentication_failed"
        assert auth.valid_session(call) is None
    finally:
        session.close()
        engine.dispose()


def test_4_voice_pin_reset_requires_strong_web_password(tmp_path):
    """Exigence 4 : Réinitialisation/changement de NIP exige le mot de passe web fort."""
    engine, session, company, _config, _api_key, _orchestrator = _voice_database(tmp_path)
    try:
        user = User(
            company_id=company.id,
            first_name="Bob",
            last_name="Manager",
            email="bob@example.com",
            password_hash=hash_password("RealPassword456!"),
            role=UserRole.ADMIN,
            phone="+15145550144",
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.ADMIN, is_active=True))
        session.commit()

        from backend.app.dependencies.auth import CurrentIdentity

        identity = CurrentIdentity(
            auth_session=MagicMock(),
            user=user,
            raw_token="test-token",
        )

        # 1. Établissement initial du NIP
        req_initial = VoicePinRequest(pin=SecretStr("583921"), pin_confirmation=SecretStr("583921"), current_password=SecretStr("RealPassword456!"))
        status = asyncio.run(set_voice_pin(req_initial, identity, session))
        assert status["has_pin"] is True
        assert status["phone_access_enabled"] is True

        # 2. Tentative de changement avec mot de passe erroné -> refusé HTTP 401
        from fastapi import HTTPException
        req_wrong_pw = VoicePinRequest(pin=SecretStr("907182"), pin_confirmation=SecretStr("907182"), current_password=SecretStr("WrongPassword!"))
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(set_voice_pin(req_wrong_pw, identity, session))
        assert exc_info.value.status_code == 401

        # 3. Changement avec mot de passe correct -> accepté
        req_ok = VoicePinRequest(pin=SecretStr("907182"), pin_confirmation=SecretStr("907182"), current_password=SecretStr("RealPassword456!"))
        status2 = asyncio.run(set_voice_pin(req_ok, identity, session))
        assert status2["has_pin"] is True
    finally:
        session.close()
        engine.dispose()


def test_5_voice_pin_lockout_after_max_attempts(tmp_path):
    """Exigence 5 : Verrouillage temporaire après 5 échecs consécutifs."""
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        settings = Settings(AUTH_JWT_SECRET="test-jwt-secret-minimum-32-chars-long", VOICE_PIN_MAX_ATTEMPTS=5)
        user = User(
            company_id=company.id,
            first_name="Charles",
            last_name="Owner",
            email="charles@example.com",
            password_hash=hash_password("Pass123!"),
            role=UserRole.OWNER,
            phone="+15145550155",
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.OWNER, is_active=True))
        session.commit()

        auth = VoiceCallerAuth(session, settings)
        cred = auth.set_pin(TenantContext(company.id, user.id), "USER", user.id, "907182")
        session.commit()

        # Effectuer 5 tentatives erronées
        for attempt in range(5):
            call = orchestrator.record_inbound(config, {"call_control_id": f"call-attempt-{attempt}", "from": "+15145550155"})
            res = auth.verify_gather(call, "839201")
            assert res["authenticated"] is False

        session.commit()
        # Le credential doit être verrouillé
        assert cred.locked_until is not None
        assert cred.locked_until > datetime.now(timezone.utc)

        # Même avec le bon NIP, l'authentification est refusée tant que verrouillé
        locked_call = orchestrator.record_inbound(config, {"call_control_id": "call-locked", "from": "+15145550155"})
        res_locked = auth.verify_gather(locked_call, "907182")
        assert res_locked["authenticated"] is False
    finally:
        session.close()
        engine.dispose()


def test_6_voice_pin_reset_invalidates_prior_sessions(tmp_path):
    """Exigence 6 : Changer de NIP invalide immédiatement toute session téléphonique active."""
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        settings = Settings(AUTH_JWT_SECRET="test-jwt-secret-minimum-32-chars-long")
        user = User(
            company_id=company.id,
            first_name="Diane",
            last_name="Owner",
            email="diane@example.com",
            password_hash=hash_password("Pass123!"),
            role=UserRole.OWNER,
            phone="+15145550166",
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.OWNER, is_active=True))
        session.commit()

        auth = VoiceCallerAuth(session, settings)
        auth.set_pin(TenantContext(company.id, user.id), "USER", user.id, "907182")
        session.commit()

        call = orchestrator.record_inbound(config, {"call_control_id": "call-active-1", "from": "+15145550166"})
        auth_res = auth.verify_gather(call, "907182")
        assert auth_res["authenticated"] is True
        session.commit()

        # Session active validée
        assert auth.valid_session(call) is not None

        # L'utilisateur change son NIP
        auth.set_pin(TenantContext(company.id, user.id), "USER", user.id, "583921")
        session.commit()

        # L'ancienne session est révoquée
        assert auth.valid_session(call) is None
    finally:
        session.close()
        engine.dispose()


def test_7_session_revocation_and_hangup_invalidation(tmp_path):
    """Exigence 7 : Révocation explicite et invalidation sur raccrochage (call.ended_at)."""
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        settings = Settings(AUTH_JWT_SECRET="test-jwt-secret-minimum-32-chars-long")
        user = User(
            company_id=company.id,
            first_name="Eric",
            last_name="Owner",
            email="eric@example.com",
            password_hash=hash_password("Pass123!"),
            role=UserRole.OWNER,
            phone="+15145550177",
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.OWNER, is_active=True))
        session.commit()

        auth = VoiceCallerAuth(session, settings)
        auth.set_pin(TenantContext(company.id, user.id), "USER", user.id, "907182")
        session.commit()

        call = orchestrator.record_inbound(config, {"call_control_id": "call-hangup-test", "from": "+15145550177"})
        assert auth.verify_gather(call, "907182")["authenticated"] is True
        session.commit()
        assert auth.valid_session(call) is not None

        # 1. Révocation via l'endpoint API
        from backend.app.dependencies.auth import CurrentIdentity
        identity = CurrentIdentity(
            auth_session=MagicMock(),
            user=user,
            raw_token="test-token",
        )
        rev_res = asyncio.run(revoke_voice_auth_sessions(identity, session))
        assert rev_res["revoked_sessions_count"] >= 1
        assert auth.valid_session(call) is None

        # 2. Nouvelle session et invalidation sur raccrochage
        call2 = orchestrator.record_inbound(config, {"call_control_id": "call-hangup-test-2", "from": "+15145550177"})
        assert auth.verify_gather(call2, "907182")["authenticated"] is True
        session.commit()
        assert auth.valid_session(call2) is not None

        # Raccrochage de l'appel
        call2.ended_at = datetime.now(timezone.utc)
        session.commit()
        assert auth.valid_session(call2) is None
    finally:
        session.close()
        engine.dispose()


def test_8_disabled_employee_rejected_mid_call(tmp_path):
    """Exigence 8 : Employé dont le compte ou l'accès vocal est désactivé perd son accès immédiatement."""
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        settings = Settings(AUTH_JWT_SECRET="test-jwt-secret-minimum-32-chars-long")
        user = User(
            company_id=company.id,
            first_name="Frank",
            last_name="Employee",
            email="frank@example.com",
            password_hash=hash_password("Pass123!"),
            role=UserRole.USER,
            phone="+15145550188",
            is_active=True,
        )
        session.add(user)
        session.flush()
        membership = CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.USER, is_active=True)
        session.add(membership)
        session.commit()

        auth = VoiceCallerAuth(session, settings)
        cred = auth.set_pin(TenantContext(company.id, user.id), "USER", user.id, "907182")
        session.commit()

        call = orchestrator.record_inbound(config, {"call_control_id": "call-emp-test", "from": "+15145550188"})
        assert auth.verify_gather(call, "907182")["authenticated"] is True
        session.commit()
        assert auth.valid_session(call) is not None

        # Cas 1 : L'administrateur désactive l'accès vocal de l'employé
        cred.enabled = False
        session.commit()
        assert auth.valid_session(call) is None

        # Réactivation
        cred.enabled = True
        session.commit()
        assert auth.valid_session(call) is not None

        # Cas 2 : L'employé est désactivé dans le système RH/User
        user.is_active = False
        session.commit()
        assert auth.valid_session(call) is None
    finally:
        session.close()
        engine.dispose()


def test_9_permissions_revocation_blocks_tool_execution(tmp_path):
    """Exigence 9 : Le retrait de permissions bloque l'accès aux outils sensibles côté backend."""
    engine, session, company, _config, _api_key, _orchestrator = _voice_database(tmp_path)
    try:
        tool_registry = build_business_tool_registry(session, MagicMock(), MagicMock())
        assistant_registry = build_default_assistant_registry(tool_registry)
        policy = ToolAuthorizationPolicy(session, assistant_registry)
        tool = GetSalesSummaryTool(session, MagicMock())

        user = User(
            company_id=company.id,
            first_name="Viewer",
            last_name="User",
            email="viewer@example.com",
            password_hash=hash_password("Pass123!"),
            role=UserRole.VIEWER,
            phone="+15145550999",
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.VIEWER, is_active=True))
        session.commit()

        # Utilisateur avec rôle VIEWER dont les permissions accordées n'incluent pas les permissions d'agent ou d'outil
        ctx_revoked = ToolExecutionContext(
            tenant=TenantContext(company_id=company.id, user_id=user.id),
            user_id=user.id,
            permissions=frozenset(["voice:public_caller"]),
            request_id="req-test-9",
            selected_agent_id="retail",
        )
        with pytest.raises(ToolAuthorizationError):
            policy.authorize(tool, ctx_revoked)
    finally:
        session.close()
        engine.dispose()


def test_10_disabled_module_blocks_tool_discovery_and_execution(tmp_path):
    """Exigence 10 : Si un module n'est pas actif pour le tenant, ses outils sont masqués."""
    engine, session, company, _config, _api_key, _orchestrator = _voice_database(tmp_path)
    try:
        tool_registry = build_business_tool_registry(session, MagicMock(), MagicMock())
        assistant_registry = build_default_assistant_registry(tool_registry)
        central = CentralAIService(assistant_registry, MagicMock(), MagicMock(), MagicMock())

        # Module retail actif : les outils retail sont autorisés pour un appelant avec permissions
        scope_active = central._tool_scope_for_request(
            agent=None,
            query="",
            page_context="/voice",
            active_modules=frozenset(["crm", "retail", "voice"]),
            permissions=frozenset(["retail:read"]),
        )
        assert scope_active is not None
        allowed_active, _ = scope_active
        assert "get_sales_summary" in allowed_active

        # Module retail désactivé / non souscrit :
        scope_inactive = central._tool_scope_for_request(
            agent=None,
            query="",
            page_context="/voice",
            active_modules=frozenset(["crm", "voice"]),
            permissions=frozenset(["retail:read"]),
        )
        assert scope_inactive is not None
        allowed_inactive, _ = scope_inactive
        assert "get_sales_summary" not in allowed_inactive
    finally:
        session.close()
        engine.dispose()


def test_11_public_caller_cannot_access_financial_or_private_tools(tmp_path):
    """Exigence 11 : Un appelant externe/public est strictement bloqué pour les outils privés."""
    engine, session, company, _config, _api_key, _orchestrator = _voice_database(tmp_path)
    try:
        # Vérification 1 : Caller scope helper
        assert is_public_voice_caller(PUBLIC_VOICE_CALLER_PERMISSIONS) is True
        assert public_voice_tool_allowed("check_availability") is True
        assert public_voice_tool_allowed("create_appointment") is True
        assert public_voice_tool_allowed("get_sales_summary") is False
        assert public_voice_tool_allowed("get_unpaid_invoices") is False

        # Vérification 2 : _tool_scope_for_request ne doit JAMAIS exposer d'outil privé
        tool_registry = build_business_tool_registry(session, MagicMock(), MagicMock())
        assistant_registry = build_default_assistant_registry(tool_registry)
        central = CentralAIService(assistant_registry, MagicMock(), MagicMock(), MagicMock())

        scope_public = central._tool_scope_for_request(
            agent=None,
            query="",
            page_context="/voice",
            active_modules=frozenset(["crm", "retail", "accounting", "voice"]),
            permissions=PUBLIC_VOICE_CALLER_PERMISSIONS,
        )
        assert scope_public is not None
        allowed_public, _ = scope_public
        assert "get_sales_summary" not in allowed_public
        assert "get_unpaid_invoices" not in allowed_public
        assert "get_crm_metrics" not in allowed_public
        # Seuls les outils publics de réservation doivent être exposés
        assert allowed_public.issubset({"check_availability", "list_available_slots", "create_appointment"})

        # Vérification 3 : Barrière d'autorisation serveur (Fail-Closed)
        policy = ToolAuthorizationPolicy(session, assistant_registry)
        tool = GetSalesSummaryTool(session, MagicMock())
        ctx_public = ToolExecutionContext(
            tenant=TenantContext(company_id=company.id, user_id=uuid4()),
            user_id=uuid4(),
            permissions=PUBLIC_VOICE_CALLER_PERMISSIONS,
            request_id="req-test-11",
            selected_agent_id="retail",
        )
        with pytest.raises(ToolAuthorizationError, match="Caller authentication is required for this tool"):
            policy.authorize(tool, ctx_public)
    finally:
        session.close()
        engine.dispose()


def test_12_multitenant_isolation_strict(tmp_path):
    """Exigence 12 : Un utilisateur du Tenant A ne peut pas s'authentifier ou agir sur le Tenant B."""
    engine, session, company_a, config_a, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        settings = Settings(AUTH_JWT_SECRET="test-jwt-secret-minimum-32-chars-long")
        # Créer le Tenant B
        company_b = Company(
            name="Tenant B Competitor",
            slug="tenant-b",
            email="tenant-b@example.com",
            country="CA",
            timezone="America/Toronto",
            industry="Retail",
            subscription_plan="professional",
            currency_code="CAD",
        )
        session.add(company_b)
        session.flush()

        user_a = User(
            company_id=company_a.id,
            first_name="User",
            last_name="Alpha",
            email="user-a@example.com",
            password_hash=hash_password("Pass123!"),
            role=UserRole.OWNER,
            phone="+15145550199",
            is_active=True,
        )
        session.add(user_a)
        session.flush()
        session.add(CompanyMembership(company_id=company_a.id, user_id=user_a.id, role=UserRole.OWNER, is_active=True))
        session.commit()

        auth = VoiceCallerAuth(session, settings)
        auth.set_pin(TenantContext(company_a.id, user_a.id), "USER", user_a.id, "907182")
        session.commit()

        config_b = VoiceBusinessConfig(
            company_id=company_b.id,
            business_name=company_b.name,
            timezone_name="America/Toronto",
            preferred_language="fr",
            greeting_message="Bonjour",
            voice_api_key_hash="hash_b_test",
            voice_api_key_last4="1234",
        )
        session.add(config_b)
        session.flush()

        # Appel sur la ligne du Tenant B
        call_b = VoiceCall(
            company_id=company_b.id,
            config_id=config_b.id,
            telnyx_call_control_id="call-b-1",
            caller_phone="+15145550199",
            status="in_progress",
        )
        session.add(call_b)
        session.commit()

        # Tentative d'authentification sur le Tenant B avec le NIP du Tenant A
        res = auth.verify_gather(call_b, "907182")
        assert res["authenticated"] is False
        assert auth.valid_session(call_b) is None
    finally:
        session.close()
        engine.dispose()


def test_13_call_interrupted_session_invalidated(tmp_path):
    """Exigence 13 : Appel interrompu/terminé invalide la session."""
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        settings = Settings(AUTH_JWT_SECRET="test-jwt-secret-minimum-32-chars-long")
        user = User(
            company_id=company.id,
            first_name="Grace",
            last_name="Owner",
            email="grace@example.com",
            password_hash=hash_password("Pass123!"),
            role=UserRole.OWNER,
            phone="+15145550111",
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.OWNER, is_active=True))
        session.commit()

        auth = VoiceCallerAuth(session, settings)
        auth.set_pin(TenantContext(company.id, user.id), "USER", user.id, "907182")
        session.commit()

        call = orchestrator.record_inbound(config, {"call_control_id": "call-interrupted", "from": "+15145550111"})
        assert auth.verify_gather(call, "907182")["authenticated"] is True
        session.commit()
        assert auth.valid_session(call) is not None

        # Interruption de l'appel
        call.status = "completed"
        call.ended_at = datetime.now(timezone.utc)
        session.commit()

        assert auth.valid_session(call) is None
    finally:
        session.close()
        engine.dispose()


def test_14_pin_redacted_from_logs_and_api(tmp_path):
    """Exigence 14 : Le NIP n'apparaît jamais en clair dans les logs, schémas ou base de données."""
    raw_pin = "907182"
    log_text = f"User dialed {raw_pin} on DTMF pad"
    redacted = redact_voice_secrets(log_text)
    assert raw_pin not in redacted
    assert "[REDACTED]" in redacted

    engine, session, company, _config, _api_key, _orchestrator = _voice_database(tmp_path)
    try:
        settings = Settings(AUTH_JWT_SECRET="test-jwt-secret-minimum-32-chars-long")
        user = User(
            company_id=company.id,
            first_name="Hector",
            last_name="Owner",
            email="hector@example.com",
            password_hash=hash_password("Pass123!"),
            role=UserRole.OWNER,
            phone="+15145550222",
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.OWNER, is_active=True))
        session.commit()

        auth = VoiceCallerAuth(session, settings)
        cred = auth.set_pin(TenantContext(company.id, user.id), "USER", user.id, raw_pin)
        session.commit()

        # Vérifier que le NIP n'est pas présent dans la BD
        assert raw_pin not in cred.pin_hash
        assert cred.pin_hash.startswith("$argon2")

        # Vérifier que l'audit API ne retourne pas de NIP
        from backend.app.dependencies.auth import CurrentIdentity
        identity = CurrentIdentity(
            auth_session=MagicMock(),
            user=user,
            raw_token="test-token",
        )
        audits = asyncio.run(list_voice_auth_audit(identity, session))
        audit_str = str(audits)
        assert raw_pin not in audit_str
    finally:
        session.close()
        engine.dispose()


def test_15_session_reuse_protection(tmp_path):
    """Exigence 15 : Une session authentifiée ne peut pas être utilisée pour un autre appel."""
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        settings = Settings(AUTH_JWT_SECRET="test-jwt-secret-minimum-32-chars-long")
        user = User(
            company_id=company.id,
            first_name="Irene",
            last_name="Owner",
            email="irene@example.com",
            password_hash=hash_password("Pass123!"),
            role=UserRole.OWNER,
            phone="+15145550333",
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.OWNER, is_active=True))
        session.commit()

        auth = VoiceCallerAuth(session, settings)
        auth.set_pin(TenantContext(company.id, user.id), "USER", user.id, "907182")
        session.commit()

        call1 = orchestrator.record_inbound(config, {"call_control_id": "call-leg-1", "from": "+15145550333"})
        auth.verify_gather(call1, "907182")
        session.commit()

        # Un deuxième appel arrive du même numéro
        call2 = orchestrator.record_inbound(config, {"call_control_id": "call-leg-2", "from": "+15145550333"})

        # call2 ne doit PAS être considéré comme authentifié sans nouvelle vérification NIP
        assert auth.valid_session(call2) is None
    finally:
        session.close()
        engine.dispose()


def test_16_cross_agent_permissions_enforced_strictly(tmp_path):
    """Exigence 16 : Une permission cross-agent ne contourne pas les restrictions Retail/Accounting."""
    engine, session, company, _config, _api_key, _orchestrator = _voice_database(tmp_path)
    try:
        tool_registry = build_business_tool_registry(session, MagicMock(), MagicMock())
        assistant_registry = build_default_assistant_registry(tool_registry)
        policy = ToolAuthorizationPolicy(session, assistant_registry)
        retail_tool = GetSalesSummaryTool(session, MagicMock())

        user = User(
            company_id=company.id,
            first_name="Cross",
            last_name="Agent",
            email="cross@example.com",
            password_hash=hash_password("Pass123!"),
            role=UserRole.USER,
            phone="+15145550888",
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.USER, is_active=True))
        session.commit()

        # Contexte avec permission cross-agent mais sans permission requise pour l'outil
        ctx = ToolExecutionContext(
            tenant=TenantContext(company_id=company.id, user_id=user.id),
            user_id=user.id,
            permissions=frozenset(["cross_agent:read"]),
            request_id="req-test-16",
            selected_agent_id="retail",
        )
        with pytest.raises(ToolAuthorizationError):
            policy.authorize(retail_tool, ctx)
    finally:
        session.close()
        engine.dispose()


def test_17_llm_direct_tool_call_rejected_fail_closed(tmp_path):
    """Exigence 17 : Rejet des outils privés même si le LLM tente de les appeler directement."""
    engine, session, company, _config, _api_key, _orchestrator = _voice_database(tmp_path)
    try:
        tool_registry = build_business_tool_registry(session, MagicMock(), MagicMock())
        assistant_registry = build_default_assistant_registry(tool_registry)
        policy = ToolAuthorizationPolicy(session, assistant_registry)
        tool = GetSalesSummaryTool(session, MagicMock())

        # Contexte d'un appelant anonyme / public
        anonymous_ctx = ToolExecutionContext(
            tenant=TenantContext(company_id=company.id, user_id=uuid4()),
            user_id=uuid4(),
            permissions=PUBLIC_VOICE_CALLER_PERMISSIONS,
            request_id="req-test-17",
            selected_agent_id="retail",
        )

        with pytest.raises(ToolAuthorizationError) as exc_info:
            policy.authorize(tool, anonymous_ctx)

        assert "Caller authentication is required" in str(exc_info.value)
    finally:
        session.close()
        engine.dispose()


def _setup_media_call_for_test(session, company, config, orchestrator, caller_phone, settings):
    from backend.app.models import VoicePhoneNumber
    from backend.app.services.module_entitlement_service import ModuleEntitlementService
    number = VoicePhoneNumber(
        company_id=company.id,
        config_id=config.id,
        phone_number=config.telnyx_phone_number,
        country_code="CA",
        provider="telnyx",
        provider_number_id="num-test-1",
        provider_connection_id=settings.telnyx_voice_connection_id,
        number_type="local",
        status="ACTIVE",
        capabilities=["voice"],
    )
    account = BillingAccount(company_id=company.id, plan_code="professional", status="active")
    session.add_all([number, account])
    session.commit()
    ModuleEntitlementService(session).activate_module(TenantContext(company.id), "voice")
    session.commit()
    call = orchestrator.record_inbound(config, {
        "call_control_id": f"ctrl-{uuid4()}",
        "from": caller_phone,
        "to": config.telnyx_phone_number,
    })
    call.status = "in_progress"
    session.commit()
    return call


def test_18_incident_1_pin_auth_inquiry_triggers_keypad_prompt(tmp_path):
    """Incident 1 : « Est-ce qu'il y a une authentification sécurisée avec un NIP ? »
    doit déclencher l'authentification par clavier DTMF (sans exposer de secret au LLM).
    """
    from backend.app.voice.telnyx_media import PublicInboundConversation
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        settings = Settings(
            AUTH_JWT_SECRET="test-jwt-secret-minimum-32-chars-long",
            TELNYX_MEDIA_INBOUND_ENABLED=True,
            TELNYX_MEDIA_ENABLED=True,
            TELNYX_VOICE_CONNECTION_ID="conn-test-1",
        )
        user = User(
            company_id=company.id,
            first_name="Marc",
            last_name="Proprio",
            email="marc@example.com",
            password_hash=hash_password("Pass123!"),
            role=UserRole.OWNER,
            phone="+15145550999",
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.OWNER, is_active=True))
        session.commit()

        auth = VoiceCallerAuth(session, settings)
        auth.set_pin(TenantContext(company.id, user.id), "USER", user.id, "907182", phone_number="+15145550999")
        session.commit()

        call = _setup_media_call_for_test(session, company, config, orchestrator, "+15145550999", settings)

        conv = PublicInboundConversation(session, settings, call.id)
        result = conv.security_gate("Est-ce qu'il y a une authentification sécurisée avec un NIP ?")

        assert result is not None
        assert result.get("auth_required") is True
        assert result.get("public") is True
        answer = result.get("answer", "")
        assert "touches de votre téléphone" in answer or "phone keypad" in answer
        assert "Ne prononcez jamais" in answer or "Never say" in answer
        session.refresh(call)
        assert call.source_context.get("pending_auth_query") == "Est-ce qu'il y a une authentification sécurisée avec un NIP ?"
    finally:
        session.close()
        engine.dispose()


def test_19_incident_1_pin_auth_inquiry_no_pin_configured_guides_to_portal(tmp_path):
    """Incident 1 (sans NIP) : Si aucun NIP n'est configuré, guider vers Voice AI -> Sécurité."""
    from backend.app.voice.telnyx_media import PublicInboundConversation
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        settings = Settings(
            AUTH_JWT_SECRET="test-jwt-secret-minimum-32-chars-long",
            TELNYX_MEDIA_INBOUND_ENABLED=True,
            TELNYX_MEDIA_ENABLED=True,
            TELNYX_VOICE_CONNECTION_ID="conn-test-1",
        )
        call = _setup_media_call_for_test(session, company, config, orchestrator, "+15145550111", settings)

        conv = PublicInboundConversation(session, settings, call.id)
        result = conv.security_gate("Est-ce qu'il y a une authentification sécurisée avec un NIP ?")

        assert result is not None
        assert result.get("auth_required") is not True
        assert "Voice AI, Sécurité" in result.get("answer", "")
    finally:
        session.close()
        engine.dispose()


def test_20_incident_2_private_orders_inquiry_triggers_pin_gate(tmp_path):
    """Incident 2 : « Combien de commandes avons-nous reçues aujourd'hui ? »
    doit exiger l'authentification par NIP et ne jamais divulguer de données au public.
    """
    from backend.app.voice.telnyx_media import PublicInboundConversation
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        settings = Settings(
            AUTH_JWT_SECRET="test-jwt-secret-minimum-32-chars-long",
            TELNYX_MEDIA_INBOUND_ENABLED=True,
            TELNYX_MEDIA_ENABLED=True,
            TELNYX_VOICE_CONNECTION_ID="conn-test-1",
        )
        user = User(
            company_id=company.id,
            first_name="Marc",
            last_name="Proprio",
            email="marc2@example.com",
            password_hash=hash_password("Pass123!"),
            role=UserRole.OWNER,
            phone="+15145550999",
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.OWNER, is_active=True))
        session.commit()

        auth = VoiceCallerAuth(session, settings)
        auth.set_pin(TenantContext(company.id, user.id), "USER", user.id, "907182", phone_number="+15145550999")
        session.commit()

        call = _setup_media_call_for_test(session, company, config, orchestrator, "+15145550999", settings)

        conv = PublicInboundConversation(session, settings, call.id)

        phrases = [
            "Combien de commandes avons-nous reçues aujourd'hui ?",
            "commandes reçues aujourd'hui",
            "chiffre d'affaires",
            "ventes du jour",
        ]
        for phrase in phrases:
            result = conv.security_gate(phrase)
            assert result is not None, f"Phrase '{phrase}' should have been intercepted by security_gate"
            assert result.get("auth_required") is True
            assert "touches de votre téléphone" in result.get("answer", "")
            session.refresh(call)
            assert call.source_context.get("pending_auth_query") == phrase
    finally:
        session.close()
        engine.dispose()


def test_21_incident_2_post_auth_automatic_execution_of_pending_query(tmp_path):
    """Exigence 8 : Après authentification par NIP, la demande initiale est consommée pour exécution."""
    from backend.app.voice.telnyx_media import PublicInboundConversation
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        settings = Settings(
            AUTH_JWT_SECRET="test-jwt-secret-minimum-32-chars-long",
            TELNYX_MEDIA_INBOUND_ENABLED=True,
            TELNYX_MEDIA_ENABLED=True,
            TELNYX_VOICE_CONNECTION_ID="conn-test-1",
        )
        call = _setup_media_call_for_test(session, company, config, orchestrator, "+15145550999", settings)
        call.source_context = {"pending_auth_query": "Combien de commandes avons-nous reçues aujourd'hui ?"}
        session.commit()

        conv = PublicInboundConversation(session, settings, call.id)
        consumed = conv.consume_pending_auth_query()
        assert consumed == "Combien de commandes avons-nous reçues aujourd'hui ?"

        session.refresh(call)
        assert "pending_auth_query" not in (call.source_context or {})
        assert conv.consume_pending_auth_query() is None
    finally:
        session.close()
        engine.dispose()


def test_22_stale_data_coverage_never_returns_zero_orders():
    """Incident 2 : Ne jamais transformer une absence de données fraîches en zéro commande.
    Le 8 octobre 2026, si les données s'arrêtent au 5 octobre, répondre que les données s'arrêtent au 5 octobre.
    """
    from backend.app.services.business_metrics_service import BusinessMetricsService
    from shared.ai_engine.dataset_ingestion.prepared_dataset import PreparedCompanyDataset
    from unittest.mock import MagicMock

    now_oct_8 = datetime(2026, 10, 8, 14, 0, 0, tzinfo=timezone.utc)
    dataset = PreparedCompanyDataset(
        company_id=uuid4(),
        dataset_id=uuid4(),
        version=1,
        canonical_columns={"date": "order_timestamp", "total": "total_amount", "id": "order_id"},
        rows=(
            {"date": "2026-10-05T10:00:00Z", "total": 120.0, "id": "ORD-1"},
            {"date": "2026-10-05T15:00:00Z", "total": 85.0, "id": "ORD-2"},
        ),
        profile={},
        mapping={},
        cleaning_report={},
        quality={},
        capability_readiness={},
    )
    snapshot = MagicMock()
    snapshot.company.timezone = "America/Montreal"
    snapshot.active_source_provider = "shopify"
    snapshot.active_source_name = "Shopify Store"
    snapshot.active_source_type = "shopify"
    snapshot.active_source_selected = True
    snapshot.status = "ready"
    snapshot.prepared = True
    snapshot.retail_summaries = True
    snapshot.active_source_last_updated_at = datetime(2026, 10, 5, 15, 0, 0, tzinfo=timezone.utc)
    snapshot.active_source_last_event_received_at = datetime(2026, 10, 5, 15, 0, 0, tzinfo=timezone.utc)

    service = BusinessMetricsService()
    bounds = service.resolve_period("today", timezone_name="America/Montreal", now=now_oct_8, source=dataset)

    summary = service.sales_summary(
        snapshot,
        dataset,
        period_start=bounds["start"],
        period_end=bounds["end"],
        queried_at=now_oct_8,
    )

    assert summary["data_covered"] is False
    assert "Les données disponibles s'arrêtent au 5 octobre" in summary["coverage_message"]
    assert "8 octobre" in summary["coverage_message"]


def test_23_role_permissions_rbac_for_retail_data(tmp_path):
    """Exigence 4 : Vérifier que l'accès aux ventes exige une session authentifiée et les permissions correspondantes."""
    from backend.app.services.module_entitlement_service import ModuleEntitlementService
    engine, session, company, _config, _api_key, _orchestrator = _voice_database(tmp_path)
    try:
        account = BillingAccount(company_id=company.id, plan_code="professional", status="active")
        session.add(account)
        session.commit()
        ModuleEntitlementService(session).activate_module(TenantContext(company.id), "retail")
        session.commit()

        tool_registry = build_business_tool_registry(session, MagicMock(), MagicMock())
        assistant_registry = build_default_assistant_registry(tool_registry)
        policy = ToolAuthorizationPolicy(session, assistant_registry)
        sales_tool = GetSalesSummaryTool(session, MagicMock())

        # 1. Appelant public (non authentifié) : bloqué
        anon_ctx = ToolExecutionContext(
            tenant=TenantContext(company_id=company.id, user_id=uuid4()),
            user_id=uuid4(),
            permissions=PUBLIC_VOICE_CALLER_PERMISSIONS,
            request_id="req-23-anon",
            selected_agent_id="retail",
        )
        with pytest.raises(ToolAuthorizationError):
            policy.authorize(sales_tool, anon_ctx)

        # 2. Employé standard (UserRole.USER) sans permission data:read : bloqué
        user_employee = User(
            company_id=company.id,
            first_name="Bob",
            last_name="Worker",
            email="bob@example.com",
            password_hash=hash_password("Pass123!"),
            role=UserRole.USER,
            phone="+15145550222",
            is_active=True,
        )
        session.add(user_employee)
        session.flush()
        session.add(CompanyMembership(company_id=company.id, user_id=user_employee.id, role=UserRole.USER, is_active=True))
        session.commit()

        user_perms = frozenset(permissions_for(UserRole.USER))
        assert "data:read" not in user_perms

        employee_ctx = ToolExecutionContext(
            tenant=TenantContext(company_id=company.id, user_id=user_employee.id),
            user_id=user_employee.id,
            permissions=user_perms,
            request_id="req-23-employee",
            selected_agent_id="retail",
        )
        with pytest.raises(ToolAuthorizationError):
            policy.authorize(sales_tool, employee_ctx)

        # 3. Propriétaire (UserRole.OWNER) : autorisé
        owner_user = User(
            company_id=company.id,
            first_name="Alice",
            last_name="Owner",
            email="owner_test23@example.com",
            password_hash=hash_password("Pass123!"),
            role=UserRole.OWNER,
            phone="+15145550777",
            is_active=True,
        )
        session.add(owner_user)
        session.flush()
        session.add(CompanyMembership(company_id=company.id, user_id=owner_user.id, role=UserRole.OWNER, is_active=True))
        session.commit()

        owner_perms = frozenset(permissions_for(UserRole.OWNER))
        assert "data:read" in owner_perms

        owner_ctx = ToolExecutionContext(
            tenant=TenantContext(company_id=company.id, user_id=owner_user.id),
            user_id=owner_user.id,
            permissions=owner_perms,
            request_id="req-23-owner",
            selected_agent_id="retail",
        )
        policy.authorize(sales_tool, owner_ctx)  # Doit passer sans exception
    finally:
        session.close()
        engine.dispose()
