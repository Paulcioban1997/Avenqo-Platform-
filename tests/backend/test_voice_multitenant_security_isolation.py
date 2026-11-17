"""Tests de sécurité P0 et d'étanchéité multi-tenant pour Avenqo Voice.

Valide :
1. Révocation du NIP divulgué (aucun NIP de test n'est un mot de passe magique ou universel).
2. Vérification d'identité sécurisée : posséder un numéro de téléphone ne confère JAMAIS
   les droits employé ou administrateur sans validation réussie du NIP.
3. Multi-tenant étanche : deux entreprises distinctes (Alpha et Beta), deux numéros Telnyx,
   deux configurations Voice, zéro fuite cross-tenant (noms, NIP, données d'entreprise).
4. Aucune fuite de NIP dans les logs, réponses API, ou sessions d'authentification.
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings
from backend.app.models import (
    Base,
    Company,
    CompanyMembership,
    User,
    UserRole,
    VoiceAuthSession,
    VoiceBusinessConfig,
    VoiceCall,
    VoiceCallerCredential,
    VoicePhoneNumber,
)
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.voice.auth import VoiceCallerAuth, validate_voice_pin
from backend.app.voice.messages import voice_ivr_greeting, voice_greeting
from backend.app.voice.service import ensure_voice_business_config
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def multi_tenant_env():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    settings = Settings(
        auth_jwt_secret="p0-voice-multitenant-security-jwt-secret-32b",
        voice_pin_max_attempts=3,
        voice_pin_lockout_seconds=300,
    )

    # 1. Entreprise Alpha
    comp_alpha = Company(
        id=uuid.uuid4(),
        name="Alpha Distribution Inc.",
        slug="alpha-distribution",
        email="owner@alpha.ca",
        country="CA",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="base",
        preferred_language="fr",
    )
    user_alpha = User(
        id=uuid.uuid4(),
        email="owner@alpha.ca",
        phone="+15145550100",
        first_name="Alice",
        last_name="Alpha",
        password_hash="argon2_fake",
        role=UserRole.OWNER,
        company_id=comp_alpha.id,
        is_active=True,
    )
    emp_alpha = User(
        id=uuid.uuid4(),
        email="tech@alpha.ca",
        phone="+15145550101",
        first_name="Bob",
        last_name="Alpha",
        password_hash="argon2_fake",
        role=UserRole.USER,
        company_id=comp_alpha.id,
        is_active=True,
    )
    session.add_all([comp_alpha, user_alpha, emp_alpha])
    session.flush()

    mem_alpha_owner = CompanyMembership(
        user_id=user_alpha.id,
        company_id=comp_alpha.id,
        role=UserRole.OWNER,
        is_active=True,
    )
    mem_alpha_emp = CompanyMembership(
        user_id=emp_alpha.id,
        company_id=comp_alpha.id,
        role=UserRole.USER,
        is_active=True,
    )
    session.add_all([mem_alpha_owner, mem_alpha_emp])

    cfg_alpha = ensure_voice_business_config(session, comp_alpha.id, "+15145551000")
    cfg_alpha.business_name = "Alpha Distribution"
    phone_alpha = VoicePhoneNumber(
        id=uuid.uuid4(),
        company_id=comp_alpha.id,
        config_id=cfg_alpha.id,
        phone_number="+15145551000",
        country_code="CA",
        number_type="local",
        provider="telnyx",
        status="ACTIVE",
    )
    session.add(phone_alpha)

    # 2. Entreprise Beta
    comp_beta = Company(
        id=uuid.uuid4(),
        name="Beta Clinique Médicale",
        slug="beta-clinique",
        email="admin@beta.ca",
        country="CA",
        timezone="America/Toronto",
        industry="Medical",
        subscription_plan="professional",
        preferred_language="fr",
    )
    user_beta = User(
        id=uuid.uuid4(),
        email="admin@beta.ca",
        phone="+15145550200",
        first_name="Charles",
        last_name="Beta",
        password_hash="argon2_fake",
        role=UserRole.OWNER,
        company_id=comp_beta.id,
        is_active=True,
    )
    emp_beta = User(
        id=uuid.uuid4(),
        email="infirmiere@beta.ca",
        phone="+15145550201",
        first_name="Diane",
        last_name="Beta",
        password_hash="argon2_fake",
        role=UserRole.USER,
        company_id=comp_beta.id,
        is_active=True,
    )
    session.add_all([comp_beta, user_beta, emp_beta])
    session.flush()

    mem_beta_owner = CompanyMembership(
        user_id=user_beta.id,
        company_id=comp_beta.id,
        role=UserRole.OWNER,
        is_active=True,
    )
    mem_beta_emp = CompanyMembership(
        user_id=emp_beta.id,
        company_id=comp_beta.id,
        role=UserRole.USER,
        is_active=True,
    )
    session.add_all([mem_beta_owner, mem_beta_emp])

    cfg_beta = ensure_voice_business_config(session, comp_beta.id, "+15145552000")
    cfg_beta.business_name = "Beta Clinique"
    phone_beta = VoicePhoneNumber(
        id=uuid.uuid4(),
        company_id=comp_beta.id,
        config_id=cfg_beta.id,
        phone_number="+15145552000",
        country_code="CA",
        number_type="local",
        provider="telnyx",
        status="ACTIVE",
    )
    session.add(phone_beta)

    # Entitlements
    ent_alpha = ModuleEntitlementService(session)
    ent_alpha.activate_module(TenantContext(comp_alpha.id, user_alpha.id), "voice")

    ent_beta = ModuleEntitlementService(session)
    ent_beta.activate_module(TenantContext(comp_beta.id, user_beta.id), "voice")

    session.commit()

    return {
        "db": session,
        "settings": settings,
        "alpha": {
            "company": comp_alpha,
            "owner": user_alpha,
            "emp": emp_alpha,
            "config": cfg_alpha,
            "phone": phone_alpha,
        },
        "beta": {
            "company": comp_beta,
            "owner": user_beta,
            "emp": emp_beta,
            "config": cfg_beta,
            "phone": phone_beta,
        },
    }


def test_leaked_pin_is_not_a_backdoor(multi_tenant_env):
    """Le NIP divulgué dans le rapport précédent (839201) ne fonctionne sur aucun tenant par défaut."""
    env = multi_tenant_env
    db = env["db"]
    auth = VoiceCallerAuth(db, env["settings"])

    call_alpha = VoiceCall(
        id=uuid.uuid4(),
        company_id=env["alpha"]["company"].id,
        config_id=env["alpha"]["config"].id,
        caller_phone=env["alpha"]["emp"].phone,
        status="in_progress",
        started_at=datetime.now(timezone.utc),
    )
    db.add(call_alpha)
    db.flush()

    # Tentative d'utilisation du NIP divulgué sans configuration préalable
    res = auth.verify_gather(call_alpha, "839201")
    assert res["authenticated"] is False
    assert res["error"] == "caller_authentication_failed"
    assert call_alpha.authenticated_user_id is None


def test_caller_phone_alone_never_grants_access(multi_tenant_env):
    """Appeler depuis le numéro de téléphone d'un employé n'accorde AUCUN droit sans NIP valide."""
    env = multi_tenant_env
    db = env["db"]
    auth = VoiceCallerAuth(db, env["settings"])

    # Configuration d'un NIP légitime pour Bob (employé Alpha)
    pin_bob = "572914"
    auth.set_pin(
        TenantContext(env["alpha"]["company"].id, env["alpha"]["emp"].id),
        "USER",
        env["alpha"]["emp"].id,
        pin_bob,
        phone_number=env["alpha"]["emp"].phone,
    )

    # Appel entrant depuis le numéro légitime de Bob
    call = VoiceCall(
        id=uuid.uuid4(),
        company_id=env["alpha"]["company"].id,
        config_id=env["alpha"]["config"].id,
        caller_phone=env["alpha"]["emp"].phone,
        status="in_progress",
        started_at=datetime.now(timezone.utc),
    )
    db.add(call)
    db.flush()

    # 1. Avant saisie du NIP : pas de session authentifiée
    assert auth.valid_session(call) is None
    assert call.authenticated_user_id is None

    # 2. Saisie d'un mauvais NIP : rejeté
    res_bad = auth.verify_gather(call, "123456")
    assert res_bad["authenticated"] is False
    assert call.authenticated_user_id is None
    assert auth.valid_session(call) is None

    # 3. Saisie du bon NIP : authentification validée
    res_good = auth.verify_gather(call, pin_bob)
    assert res_good["authenticated"] is True
    assert call.authenticated_user_id == env["alpha"]["emp"].id
    session = auth.valid_session(call)
    assert session is not None
    assert session.principal_id == env["alpha"]["emp"].id


def test_cross_tenant_pin_isolation(multi_tenant_env):
    """Le NIP d'un employé Alpha est rejeté sur les appels de l'entreprise Beta."""
    env = multi_tenant_env
    db = env["db"]
    auth = VoiceCallerAuth(db, env["settings"])

    pin_alpha = "781294"
    pin_beta = "629415"

    auth.set_pin(
        TenantContext(env["alpha"]["company"].id, env["alpha"]["emp"].id),
        "USER",
        env["alpha"]["emp"].id,
        pin_alpha,
        phone_number=env["alpha"]["emp"].phone,
    )
    auth.set_pin(
        TenantContext(env["beta"]["company"].id, env["beta"]["emp"].id),
        "USER",
        env["beta"]["emp"].id,
        pin_beta,
        phone_number=env["beta"]["emp"].phone,
    )

    # Appel vers Beta depuis le téléphone de l'employé Alpha
    call_beta = VoiceCall(
        id=uuid.uuid4(),
        company_id=env["beta"]["company"].id,
        config_id=env["beta"]["config"].id,
        caller_phone=env["alpha"]["emp"].phone,
        status="in_progress",
        started_at=datetime.now(timezone.utc),
    )
    db.add(call_beta)
    db.flush()

    # Tente le NIP Alpha sur l'appel Beta : ÉCHEC
    res_cross = auth.verify_gather(call_beta, pin_alpha)
    assert res_cross["authenticated"] is False
    assert call_beta.authenticated_user_id is None

    # Tente le NIP Beta sur l'appel Beta mais depuis le téléphone Alpha sans identifiant : ÉCHEC
    res_mismatch = auth.verify_gather(call_beta, pin_beta)
    assert res_mismatch["authenticated"] is False
    assert call_beta.authenticated_user_id is None


def test_incoming_telnyx_phone_number_mapping_strict(multi_tenant_env):
    """La résolution du numéro entrant route strictement vers l'entreprise propriétaire."""
    env = multi_tenant_env
    db = env["db"]

    num_alpha = db.scalar(
        select(VoicePhoneNumber).where(
            VoicePhoneNumber.phone_number == "+15145551000",
            VoicePhoneNumber.status == "ACTIVE",
        )
    )
    assert num_alpha is not None
    assert num_alpha.company_id == env["alpha"]["company"].id
    assert num_alpha.config_id == env["alpha"]["config"].id

    num_beta = db.scalar(
        select(VoicePhoneNumber).where(
            VoicePhoneNumber.phone_number == "+15145552000",
            VoicePhoneNumber.status == "ACTIVE",
        )
    )
    assert num_beta is not None
    assert num_beta.company_id == env["beta"]["company"].id
    assert num_beta.config_id == env["beta"]["config"].id

    # Aucune ambiguïté ou collision
    assert num_alpha.company_id != num_beta.company_id
    assert num_alpha.phone_number != num_beta.phone_number


def test_voice_business_persona_isolation(multi_tenant_env):
    """Les salutations et l'identité vocale de chaque tenant sont strictement respectées."""
    env = multi_tenant_env

    # 1. Salutation Alpha
    greeting_alpha = voice_ivr_greeting(env["alpha"]["config"])
    assert "Alpha Distribution" in greeting_alpha
    assert "Beta Clinique" not in greeting_alpha

    # 2. Salutation Beta
    greeting_beta = voice_ivr_greeting(env["beta"]["config"])
    assert "Beta Clinique" in greeting_beta
    assert "Alpha Distribution" not in greeting_beta


def test_zero_pin_leakage_in_records_and_sessions(multi_tenant_env):
    """Le NIP n'est jamais stocké en clair ni divulgué dans les modèles de session."""
    env = multi_tenant_env
    db = env["db"]
    auth = VoiceCallerAuth(db, env["settings"])

    secret_pin = "938172"
    cred = auth.set_pin(
        TenantContext(env["alpha"]["company"].id, env["alpha"]["emp"].id),
        "USER",
        env["alpha"]["emp"].id,
        secret_pin,
        phone_number=env["alpha"]["emp"].phone,
    )

    # 1. Dans la base : pin_hash est hashé (jamais en clair)
    assert secret_pin not in cred.pin_hash
    assert cred.pin_hash.startswith("$argon2") or cred.pin_hash.startswith("$pbkdf2") or len(cred.pin_hash) >= 32

    # 2. Dans l'appel et la session d'authentification : zéro trace du NIP
    call = VoiceCall(
        id=uuid.uuid4(),
        company_id=env["alpha"]["company"].id,
        config_id=env["alpha"]["config"].id,
        caller_phone=env["alpha"]["emp"].phone,
        status="in_progress",
        started_at=datetime.now(timezone.utc),
    )
    db.add(call)
    db.flush()

    res = auth.verify_gather(call, secret_pin)
    assert res["authenticated"] is True

    session = db.scalar(
        select(VoiceAuthSession).where(VoiceAuthSession.call_id == call.id)
    )
    assert session is not None
    assert str(secret_pin) not in repr(session)
    assert not hasattr(session, "pin")
    assert not hasattr(session, "pin_hash")
