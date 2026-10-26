"""Tests automatisés Phase P2 : Intelligence Conversationnelle + Routage Employés/Clients + Activation par Entreprise.

Couvre :
1. Cycle de vie fail-closed (DRAFT -> CONFIGURING -> READY_FOR_TEST -> ACTIVE -> SUSPENDED).
2. Refus strict des appels publics pour numéros non activés (aucun démarrage Realtime, aucune donnée).
3. Mode test administrateur pour READY_FOR_TEST distinct du public.
4. Menu IVR configurable :
   - Touche 1 : Employés avec vérification NIP personnel, rate-limiting, protection brute-force, révocation à la fin.
   - Touche 2 : Clients publics sans NIP, outils publics uniquement, zéro accès privé.
5. Intelligence conversationnelle et grounding :
   - Requête hors catalogue (« J'ai faim, je veux manger. As-tu des recommandations ? ») : refus poli sans argumentaire snowboard.
   - Réponses directes oui/non avec explication naturelle.
   - Compréhension d'intention avant requête d'outils métier.
6. Isolation stricte multi-tenant.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Generator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.ai.chat.chat_service import SYSTEM_INSTRUCTION, _localized_system_instruction
from backend.app.config.settings import Settings
from backend.app.models.billing import BillingAccount
from backend.app.models.company import Company
from backend.app.models.user import User, UserRole
from backend.app.models.company_membership import CompanyMembership
from backend.app.models.voice import (
    VoiceAuthSession,
    VoiceBusinessConfig,
    VoiceCall,
    VoiceCallerCredential,
    VoicePhoneNumber,
)
from backend.app.models.base import Base
from backend.app.services.voice_lifecycle_service import (
    VoiceLifecycleService,
    VoiceLifecycleStatus,
)
from backend.app.voice.auth import VoiceCallerAuth, redact_voice_secrets, validate_voice_pin
from backend.app.voice.caller_scope import (
    PUBLIC_VOICE_BASE_TOOLS,
    PUBLIC_VOICE_CRM_TOOLS,
    PUBLIC_VOICE_CALLER_PERMISSIONS,
    is_public_voice_caller,
    public_voice_tool_allowed,
)
from shared.ai_engine.contracts import TenantContext


# ==============================================================================
# Fixtures & Helpers
# ==============================================================================

@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def mock_settings() -> Settings:
    settings = Settings()
    settings.auth_jwt_secret = "media-test-secret-at-least-32-characters"
    settings.voice_pin_max_attempts = 3
    settings.voice_pin_lockout_seconds = 300
    settings.telnyx_media_enabled = True
    settings.telnyx_media_inbound_enabled = True
    return settings


def make_company(
    id: UUID,
    name: str = "Produits_Ero",
    slug: str = "produits-ero",
    email: str = "contact@produitsero.com",
) -> Company:
    return Company(
        id=id,
        name=name,
        slug=slug,
        email=email,
        country="Canada",
        timezone="America/Toronto",
        industry="sporting_goods",
        subscription_plan="professional",
    )


def make_user(
    id: UUID,
    company_id: UUID,
    email: str,
    role: UserRole,
    phone: str | None = None,
) -> User:
    return User(
        id=id,
        company_id=company_id,
        first_name="Test",
        last_name="User",
        email=email,
        password_hash="fakehash",
        phone=phone,
        role=role,
        is_active=True,
    )


def make_voice_config(
    company_id: UUID,
    business_name: str = "Produits_Ero",
    greeting_message: str = "Bienvenue chez Produits_Ero.",
    telnyx_phone_number: str | None = None,
    enabled: bool = False,
    call_policy: dict | None = None,
    preferred_language: str = "fr-CA",
    voice_id: str = "coral",
) -> VoiceBusinessConfig:
    key_hash = hashlib.sha256(f"test-voice-key-{company_id}-{uuid4()}".encode()).hexdigest()
    return VoiceBusinessConfig(
        id=uuid4(),
        company_id=company_id,
        business_name=business_name,
        greeting_message=greeting_message,
        telnyx_phone_number=telnyx_phone_number,
        preferred_language=preferred_language,
        voice_id=voice_id,
        voice_api_key_hash=key_hash,
        voice_api_key_last4="1234",
        enabled=enabled,
        call_policy=call_policy or {},
    )


# ==============================================================================
# 1. P2 : Cycle de Vie Fail-Closed et Activation par Entreprise
# ==============================================================================

def test_p2_lifecycle_status_draft_and_configuring(db_session: Session):
    """Vérifie que sans configuration complète, le statut est DRAFT ou CONFIGURING."""
    company_id = uuid4()
    company = make_company(id=company_id)
    db_session.add(company)
    db_session.commit()

    service = VoiceLifecycleService(db_session)
    status_info = service.get_status(company_id)
    assert status_info["status"] == VoiceLifecycleStatus.DRAFT.value
    assert status_info["can_activate"] is False
    assert status_info["enabled"] is False

    # Ajout d'une configuration partielle -> passe à CONFIGURING
    config = make_voice_config(
        company_id=company_id,
        business_name="Produits_Ero",
        greeting_message="Bienvenue chez Produits_Ero.",
        enabled=False,
    )
    db_session.add(config)
    db_session.commit()

    status_info = service.get_status(company_id)
    assert status_info["status"] == VoiceLifecycleStatus.CONFIGURING.value
    assert status_info["can_activate"] is False


def test_p2_fail_closed_admissibility_refuses_non_active_public_call(db_session: Session):
    """Exigence absolue : un numéro réservé non actif REFUSE les appels publics sans Realtime."""
    company_id = uuid4()
    company = make_company(id=company_id)
    config = make_voice_config(
        company_id=company_id,
        business_name="Produits_Ero",
        greeting_message="Bonjour.",
        telnyx_phone_number="+14386075438",
        enabled=False,
        call_policy={"lifecycle_status": VoiceLifecycleStatus.CONFIGURING.value},
    )
    db_session.add_all([company, config])
    db_session.commit()

    service = VoiceLifecycleService(db_session)
    admitted, reason = service.is_call_admissible(company_id, caller_phone="+15145550100")
    assert admitted is False
    assert reason == "CONFIGURING"


def test_p2_ready_for_test_allows_admin_refuses_public(db_session: Session):
    """READY_FOR_TEST permet l'appel des administrateurs du tenant mais bloque le public."""
    company_id = uuid4()
    admin_id = uuid4()
    admin_phone = "+15149998877"
    public_phone = "+15141112233"

    company = make_company(id=company_id)
    admin_user = make_user(
        id=admin_id,
        company_id=company_id,
        email="gauffy95@gmail.com",
        phone=admin_phone,
        role=UserRole.ADMIN,
    )
    config = make_voice_config(
        company_id=company_id,
        business_name="Produits_Ero",
        greeting_message="Bonjour.",
        telnyx_phone_number="+14386075438",
        enabled=False,
        call_policy={"lifecycle_status": VoiceLifecycleStatus.READY_FOR_TEST.value},
    )
    db_session.add_all([company, admin_user, config])
    db_session.commit()

    service = VoiceLifecycleService(db_session)

    # Appel administrateur -> admis en mode test
    admin_admitted, admin_reason = service.is_call_admissible(company_id, caller_phone=admin_phone)
    assert admin_admitted is True
    assert admin_reason == "ADMIN_TEST_CALL"

    # Appel public anonyme -> refusé
    pub_admitted, pub_reason = service.is_call_admissible(company_id, caller_phone=public_phone)
    assert pub_admitted is False
    assert pub_reason == "NOT_ACTIVE_PUBLIC_BLOCKED"


def test_p2_activate_and_suspend_lifecycle(db_session: Session):
    """Vérifie l'activation explicite avec audit log et la suspension immédiate."""
    company_id = uuid4()
    actor_id = uuid4()
    company = make_company(id=company_id)
    account = BillingAccount(id=uuid4(), company_id=company_id, status="active", plan_code="professional")
    number = VoicePhoneNumber(
        id=uuid4(),
        company_id=company_id,
        phone_number="+14386075438",
        country_code="CA",
        number_type="local",
        provider="telnyx",
        status="ACTIVE",
        capabilities=["voice"],
    )
    config = make_voice_config(
        company_id=company_id,
        business_name="Produits_Ero",
        greeting_message="Bienvenue chez Produits_Ero.",
        telnyx_phone_number="+14386075438",
        voice_id="coral",
        preferred_language="fr-CA",
        enabled=False,
        call_policy={"ivr_enabled": True},
    )
    db_session.add_all([company, account, number, config])
    db_session.commit()

    service = VoiceLifecycleService(db_session)
    status_info = service.get_status(company_id)
    assert status_info["can_activate"] is True

    # Activation
    activated = service.activate(company_id, actor_id)
    assert activated["status"] == VoiceLifecycleStatus.ACTIVE.value
    assert activated["enabled"] is True
    assert config.enabled is True

    # Vérification d'admissibilité pour appel public après activation
    admitted, reason = service.is_call_admissible(company_id, caller_phone="+15145550100")
    assert admitted is True
    assert reason == "ACTIVE"

    # Suspension
    suspended = service.suspend(company_id, actor_id, reason="Maintenance annuelle")
    assert suspended["status"] == VoiceLifecycleStatus.SUSPENDED.value
    assert suspended["enabled"] is False
    assert config.enabled is False

    # Admissibilité après suspension -> bloqué
    susp_admitted, susp_reason = service.is_call_admissible(company_id, caller_phone="+15145550100")
    assert susp_admitted is False
    assert susp_reason == "SUSPENDED"


# ==============================================================================
# 2. P1 : Routage Téléphonique IVR (Touche 1 Employés vs Touche 2 Clients)
# ==============================================================================

def test_p1_ivr_settings_update_and_customization(db_session: Session):
    """Vérifie la configuration du menu d'accueil IVR personnalisé."""
    company_id = uuid4()
    actor_id = uuid4()
    company = make_company(id=company_id)
    config = make_voice_config(
        company_id=company_id,
        business_name="Produits_Ero",
        greeting_message="Accueil",
        enabled=True,
    )
    db_session.add_all([company, config])
    db_session.commit()

    service = VoiceLifecycleService(db_session)
    updated = service.update_ivr_settings(
        company_id,
        actor_id,
        ivr_enabled=True,
        ivr_greeting="Bienvenue chez Produits_Ero. 1 pour l'équipe, 2 pour les clients.",
    )
    assert updated["ivr"]["enabled"] is True
    assert updated["ivr"]["greeting"] == "Bienvenue chez Produits_Ero. 1 pour l'équipe, 2 pour les clients."


def test_p1_employee_pin_authentication_and_brute_force_lockout(
    db_session: Session, mock_settings: Settings
):
    """Touche 1 : NIP personnel employé avec hachage sécurisé, rate-limiting et verrouillage."""
    company_id = uuid4()
    user_id = uuid4()
    employee_phone = "+15148887766"

    company = make_company(id=company_id)
    user = make_user(
        id=user_id,
        company_id=company_id,
        email="employe@produitsero.com",
        phone=employee_phone,
        role=UserRole.USER,
    )
    membership = CompanyMembership(
        id=uuid4(),
        company_id=company_id,
        user_id=user_id,
        role=UserRole.USER,
        is_active=True,
    )
    config = make_voice_config(
        company_id=company_id,
        business_name="Produits_Ero",
        greeting_message="Bonjour.",
        enabled=True,
    )
    call = VoiceCall(
        id=uuid4(),
        company_id=company_id,
        config_id=config.id,
        telnyx_call_control_id="v2:call-control-p2-test-001",
        caller_phone=employee_phone,
        status="in_progress",
        verification_attempts=0,
    )
    db_session.add_all([company, user, membership, config, call])
    db_session.commit()

    auth = VoiceCallerAuth(db_session, mock_settings)
    tenant = TenantContext(company_id=company_id, user_id=user_id)

    # 1. Configuration sécurisée du NIP personnel (6 chiffres non triviaux)
    with pytest.raises(ValueError, match="nontrivial"):
        validate_voice_pin("123456")  # rejet NIP trivial

    valid_pin = "849206"
    cred = auth.set_pin(tenant, "USER", user_id, valid_pin, phone_number=employee_phone)
    assert cred.enabled is True
    assert cred.pin_hash != valid_pin  # NIP salé et poivré, jamais en clair
    db_session.commit()

    # 2. Échec avec mauvais NIP -> incrémente failed_attempts
    fail_res = auth.verify_gather(call, pin="112233")
    assert fail_res["authenticated"] is False
    assert cred.failed_attempts == 1

    # 3. Échecs répétés jusqu'au verrouillage brute-force (max = 3)
    auth.verify_gather(call, pin="445566")
    lock_res = auth.verify_gather(call, pin="778899")
    assert lock_res["authenticated"] is False
    assert cred.failed_attempts >= 3
    assert cred.locked_until is not None

    # Tentative avec le bon NIP alors que le compte est verrouillé -> refusé
    assert auth.verify_gather(call, pin=valid_pin)["authenticated"] is False


def test_p1_customer_key2_public_scope_and_zero_private_access():
    """Touche 2 : L'appelant client public n'a aucun NIP requis et n'accède à AUCUN outil privé."""
    assert is_public_voice_caller(PUBLIC_VOICE_CALLER_PERMISSIONS) is True
    assert is_public_voice_caller(frozenset({"ai:use", "modules:read"})) is False

    # Outils publics autorisés
    assert public_voice_tool_allowed("get_business_info", has_crm_booking=True) is True
    assert public_voice_tool_allowed("check_availability", has_crm_booking=True) is True
    assert public_voice_tool_allowed("list_available_slots", has_crm_booking=True) is True
    assert public_voice_tool_allowed("create_appointment", has_crm_booking=True) is True

    # Outils privés strictement INTERDITS pour les clients publics
    assert public_voice_tool_allowed("get_sales_summary") is False
    assert public_voice_tool_allowed("get_top_products") is False
    assert public_voice_tool_allowed("get_unpaid_invoices") is False
    assert public_voice_tool_allowed("get_financial_overview") is False
    assert public_voice_tool_allowed("get_product_detail") is False


# ==============================================================================
# 3. P0 : Intelligence Conversationnelle et Requêtes Hors Catalogue
# ==============================================================================

def test_p0_system_instruction_out_of_domain_and_hunger_handling():
    """P0 Root Cause Fix : « J'ai faim, je veux manger » ne doit JAMAIS proposer de snowboards."""
    instruction = _localized_system_instruction(
        SYSTEM_INSTRUCTION,
        user_language="fr-CA",
        company_country="Canada",
        company_currency="CAD",
        company_timezone="America/Toronto",
        is_voice_call=True,
    )

    # 1. L'instruction système générale interdit de transformer la faim en vente d'équipement
    assert "Understand the user's real intent before querying business tools." in instruction
    assert "never pitch products (such as sporting goods or equipment) as food or in response to hunger." in instruction

    # 2. L'instruction vocale temps réel guide explicitement le comportement conversationnel
    assert "Conversational Intelligence & Real Intent Understanding" in instruction
    assert "DO NOT turn every remark into a sales pitch or product catalog lookup!" in instruction
    assert "J'ai faim, je veux manger. As-tu des recommandations ?" in instruction
    assert "NEVER pitch sporting goods, equipment, or catalog products when the caller asks about food or dining!" in instruction
    assert "Answer yes/no questions directly with yes or no and a natural explanation." in instruction


def test_p0_redact_voice_secrets_protects_pins_and_secrets():
    """Vérifie qu'aucun NIP ou secret à 6-12 chiffres ne fuite dans les journaux ou le LLM."""
    clean_text = redact_voice_secrets("L'appelant a composé le NIP 849206 pour s'authentifier.")
    assert "849206" not in clean_text
    assert "[REDACTED]" in clean_text


# ==============================================================================
# 4. Isolation Stricte Multi-Tenant
# ==============================================================================

def test_multi_tenant_isolation_credential_access(
    db_session: Session, mock_settings: Settings
):
    """Vérifie que les identifiants et NIP d'une entreprise sont inaccessibles par une autre."""
    company_a = uuid4()
    company_b = uuid4()
    user_a = uuid4()
    user_b = uuid4()

    db_session.add_all([
        make_company(id=company_a, name="Entreprise A", slug="ent-a", email="a@a.com"),
        make_company(id=company_b, name="Entreprise B", slug="ent-b", email="b@b.com"),
        make_user(id=user_a, company_id=company_a, email="user.a@a.com", role=UserRole.OWNER, phone="+15141110001"),
        make_user(id=user_b, company_id=company_b, email="user.b@b.com", role=UserRole.OWNER, phone="+15141110002"),
        CompanyMembership(id=uuid4(), company_id=company_a, user_id=user_a, role=UserRole.OWNER, is_active=True),
        CompanyMembership(id=uuid4(), company_id=company_b, user_id=user_b, role=UserRole.OWNER, is_active=True),
    ])
    db_session.commit()

    auth = VoiceCallerAuth(db_session, mock_settings)
    auth.set_pin(TenantContext(company_id=company_a, user_id=user_a), "USER", user_a, "582910", phone_number="+15141110001")
    db_session.commit()

    # Tentative d'authentification sur un appel de l'entreprise B avec le numéro/NIP de A -> échec
    config_b = make_voice_config(company_id=company_b)
    call_b = VoiceCall(
        id=uuid4(),
        company_id=company_b,
        config_id=config_b.id,
        caller_phone="+15141110001",
        status="in_progress",
        verification_attempts=0,
    )
    db_session.add_all([config_b, call_b])
    db_session.commit()

    res = auth.verify_gather(call_b, pin="582910")
    assert res["authenticated"] is False


def test_voice_lifecycle_action_request_confirmed_contract_strict():
    """Vérifie le contrat Pydantic strict : default=False (fail-closed), alias supporté, contradiction rejetée, extra interdit."""
    from pydantic import ValidationError
    from backend.app.schemas.voice import VoiceLifecycleActionRequest

    # 1. Par défaut, confirmed doit STRICTEMENT être False (sécurité fail-closed)
    req_default = VoiceLifecycleActionRequest()
    assert req_default.confirmed is False

    # 2. Payload canonique standard avec confirmed=True explicite
    req1 = VoiceLifecycleActionRequest(confirmed=True, reason="Activation standard")
    assert req1.confirmed is True
    assert req1.reason == "Activation standard"

    # 3. Payload avec alias rétrocompatible confirm=True (converti en confirmed=True)
    req2 = VoiceLifecycleActionRequest.model_validate({"confirm": True, "reason": "Alias test"})
    assert req2.confirmed is True
    assert req2.confirm is True

    # 4. Payload avec alias confirm=False
    req_alias_false = VoiceLifecycleActionRequest.model_validate({"confirm": False})
    assert req_alias_false.confirmed is False

    # 5. Payload explicite avec confirmed=False
    req3 = VoiceLifecycleActionRequest(confirmed=False)
    assert req3.confirmed is False

    # 6. Rejet STRICT des valeurs contradictoires entre confirmed et confirm
    with pytest.raises(ValidationError, match="Valeurs contradictoires"):
        VoiceLifecycleActionRequest.model_validate({"confirmed": True, "confirm": False})

    with pytest.raises(ValidationError, match="Valeurs contradictoires"):
        VoiceLifecycleActionRequest.model_validate({"confirmed": False, "confirm": True})

    # 7. Refus strict de tout champ non contractuel (extra="forbid")
    with pytest.raises(ValidationError):
        VoiceLifecycleActionRequest.model_validate({"confirmed": True, "unexpected_field": "hacked"})


def test_activate_voice_lifecycle_endpoint_requires_explicit_confirmed():
    """Vérifie que l'endpoint d'activation refuse strictement toute requête non confirmée avec HTTP 400."""
    from unittest.mock import MagicMock
    from fastapi import HTTPException
    from backend.app.routers.voice import activate_voice_lifecycle
    from backend.app.schemas.voice import VoiceLifecycleActionRequest

    mock_identity = MagicMock()
    mock_identity.user.company_id = uuid4()
    mock_identity.user.id = uuid4()
    mock_db = MagicMock()

    # Tentative avec confirmed=False
    with pytest.raises(HTTPException) as exc_info:
        activate_voice_lifecycle(
            payload=VoiceLifecycleActionRequest(confirmed=False),
            identity=mock_identity,
            db=mock_db,
        )
    assert exc_info.value.status_code == 400
    assert "Confirmation explicite requise" in exc_info.value.detail
