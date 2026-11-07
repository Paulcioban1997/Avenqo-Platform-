"""Tests unitaires et d'intégration pour le parcours contractuel Enterprise Avenqo et le CEO Command Center.

Couvre :
1. Profil juridique d'entreprise (CompanyLegalProfile) & validation conditionnelle NEQ
2. Réconciliation commerciale (CommercialReconciler) & blocage COMMERCIAL_CONFIG_MISMATCH
3. Défis de signature à usage unique (anti-rejeu)
4. Cycle de vie contractuel & distinction Customer Signed vs Fully Executed
5. RBAC plateforme à moindre privilège & 10 modules CEO Command Center
6. Cloisonnement strict multi-tenant
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config.settings import Settings, get_settings
from backend.app.dependencies.auth import CurrentIdentity, require_platform_role
from backend.app.models.base import Base, CompanyStatus, UserRole


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test_enterprise.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
from backend.app.models.company import Company
from backend.app.models.company_contract import (
    CompanyContract,
    ContractExecutionPartyState,
    ContractLifecycleStatus,
)
from backend.app.models.company_legal_profile import CompanyLegalProfile
from backend.app.models.company_module import CompanyModule
from backend.app.models.module import Module
from backend.app.models.user import User
from backend.app.services.commercial_reconciler import CommercialReconciler
from backend.app.services.company_legal_profile_service import (
    CompanyLegalProfileService,
    LegalProfileValidationError,
)
from backend.app.services.contract_signature_service import (
    CommercialConfigMismatchError,
    ContractAuthorityError,
    ContractSignatureService,
)
from backend.app.services.signing_challenge_service import SigningChallengeService
from backend.app.routers.contracts import create_signing_challenge
from backend.app.routers.ceo_command_center import get_executive_overview, get_connectors_health
from backend.app.models.billing import BillingAccount
from backend.app.models.contract_signing_challenge import ContractSigningChallenge
from shared.ai_engine.contracts import TenantContext
from payments.plans import PlanCode


def _create_company(db: Session, name: str = "Acme Corp", country: str = "Canada", plan: str = "base") -> Company:
    uid = uuid4().hex[:6]
    company = Company(
        name=name,
        slug=f"acme-{uid}",
        email=f"contact-{uid}@acme.com",
        billing_email=f"billing-{uid}@acme.com",
        country=country,
        currency_code="CAD" if country == "Canada" else "USD",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan=plan,
        status=CompanyStatus.ACTIVE,
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def _create_user(
    db: Session,
    company: Company,
    role: UserRole = UserRole.OWNER,
    is_platform_admin: bool = False,
    platform_role: str | None = None,
) -> User:
    uid = uuid4().hex[:6]
    user = User(
        company_id=company.id,
        first_name="Jean",
        last_name="Dupont",
        email=f"user-{uid}@example.com",
        password_hash="argon2_hashed_pw",
        role=role,
        is_platform_admin=is_platform_admin,
        platform_role=platform_role,
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ==========================================================================
# 1. TESTS DU PROFIL JURIDIQUE D'ENTREPRISE (CompanyLegalProfile)
# ==========================================================================

def test_legal_profile_validation_quebec_neq_enforced_if_present(db_session: Session):
    """Vérifie que pour une entreprise au Québec, si le NEQ est renseigné, il doit faire 10 chiffres."""
    company = _create_company(db_session, country="Canada")
    svc = CompanyLegalProfileService(db_session)

    # NEQ invalide (9 chiffres)
    invalid_data = {
        "legal_name": "Québec Tech Inc.",
        "country": "Canada",
        "province_state": "Québec",
        "registration_number": "123456789",  # 9 chiffres -> invalide
        "registered_address_street": "1000 Rue de la Gauchetière O",
        "registered_address_city": "Montréal",
        "registered_address_state_province": "Québec",
        "registered_address_postal_code": "H3B 4W5",
        "registered_address_country": "Canada",
        "phone": "+1-514-555-0100",
        "general_email": "admin@quebectech.ca",
        "billing_email": "facturation@quebectech.ca",
        "authorized_representative_first_name": "Marc",
        "authorized_representative_last_name": "Tremblay",
        "authorized_representative_email": "marc@quebectech.ca",
        "authorized_representative_title": "Président",
        "authorized_representative_capacity": "President",
        "authorized_representative_authority_confirmed": True,
    }

    with pytest.raises(LegalProfileValidationError) as exc:
        svc.upsert_profile(company.id, invalid_data)
    errors = exc.value.errors
    assert any(e["field"] == "registration_number" for e in errors)

    # NEQ valide (10 chiffres)
    invalid_data["registration_number"] = "1178945612"
    profile = svc.upsert_profile(company.id, invalid_data)
    assert profile.registration_number == "1178945612"
    assert profile.legal_name == "Québec Tech Inc."


def test_legal_profile_validation_outside_quebec_never_imposes_neq(db_session: Session):
    """Vérifie qu'une entreprise étrangère (ex: France, USA) ne se voit jamais imposer de NEQ québécois."""
    company = _create_company(db_session, country="France", plan="professional")
    svc = CompanyLegalProfileService(db_session)

    data_france = {
        "legal_name": "Paris Solutions SAS",
        "country": "France",
        "province_state": "Île-de-France",
        "registration_number": "RCS PARIS B 512 890 123",  # Numéro local valide hors Québec
        "registered_address_street": "15 Rue de la Paix",
        "registered_address_city": "Paris",
        "registered_address_state_province": "Île-de-France",
        "registered_address_postal_code": "75002",
        "registered_address_country": "France",
        "phone": "+33-1-42-68-55-00",
        "general_email": "contact@paris-solutions.fr",
        "billing_email": "compta@paris-solutions.fr",
        "authorized_representative_first_name": "Claire",
        "authorized_representative_last_name": "Dubois",
        "authorized_representative_email": "claire.dubois@paris-solutions.fr",
        "authorized_representative_title": "Directrice Générale",
        "authorized_representative_capacity": "CEO",
        "authorized_representative_authority_confirmed": True,
    }

    profile = svc.upsert_profile(company.id, data_france)
    assert profile.id is not None
    assert profile.country == "France"
    assert profile.registration_number == "RCS PARIS B 512 890 123"


def test_legal_profile_authority_declaration_required(db_session: Session):
    """Vérifie que la case d'affirmation d'autorité légale est obligatoire."""
    company = _create_company(db_session)
    svc = CompanyLegalProfileService(db_session)

    data = {
        "legal_name": "Alpha Corp",
        "country": "Canada",
        "province_state": "Ontario",
        "registered_address_street": "100 Bay St",
        "registered_address_city": "Toronto",
        "registered_address_state_province": "ON",
        "registered_address_postal_code": "M5J 2R8",
        "registered_address_country": "Canada",
        "phone": "+1-416-555-0199",
        "general_email": "info@alpha.ca",
        "billing_email": "billing@alpha.ca",
        "authorized_representative_first_name": "John",
        "authorized_representative_last_name": "Doe",
        "authorized_representative_email": "john@alpha.ca",
        "authorized_representative_title": "Director",
        "authorized_representative_capacity": "Authorized Director",
        "authorized_representative_authority_confirmed": False,  # NON COCHÉ
    }

    with pytest.raises(LegalProfileValidationError) as exc:
        svc.upsert_profile(company.id, data)
    assert any(e["field"] == "authorized_representative_authority_confirmed" for e in exc.value.errors)


# ==========================================================================
# 2. TESTS DE RÉCONCILIATION COMMERCIALE (CommercialReconciler)
# ==========================================================================

def test_commercial_reconciler_baseline_plans(db_session: Session):
    """Vérifie la concordance exacte des prix et limites canoniques pour Base et Professional."""
    company_base = _create_company(db_session, plan="base")
    schedule_base = CommercialReconciler.reconcile(company_base)
    assert schedule_base.reconciliation_status == "RECONCILED"
    assert not schedule_base.is_blocked
    assert schedule_base.monthly_price == 29.99
    assert schedule_base.max_selectable_modules == 2
    assert schedule_base.included_ai_credits == 6_500
    assert "Aucun dépassement" in schedule_base.extra_credits_terms
    assert "25 000 crédits" not in schedule_base.extra_credits_terms

    company_pro = _create_company(db_session, plan="professional")
    schedule_pro = CommercialReconciler.reconcile(company_pro)
    assert schedule_pro.reconciliation_status == "RECONCILED"
    assert not schedule_pro.is_blocked
    assert schedule_pro.monthly_price == 49.99
    assert schedule_pro.max_selectable_modules == 5
    assert schedule_pro.included_ai_credits == 20_000


def test_commercial_reconciler_detects_module_overrun_and_blocks(db_session: Session):
    """Vérifie qu'un dépassement de quota de modules bloque la réconciliation (COMMERCIAL_CONFIG_MISMATCH)."""
    company = _create_company(db_session, plan="base")  # Max 2 modules autorisés

    # Ajout fictif de 3 modules actifs
    m1 = Module(code="crm", name="CRM", description="CRM Suite", is_active=True)
    m2 = Module(code="retail", name="Retail", description="Retail Suite", is_active=True)
    m3 = Module(code="marketing", name="Marketing", description="Marketing Suite", is_active=True)
    db_session.add_all([m1, m2, m3])
    db_session.commit()

    now = datetime.now(timezone.utc)
    cm1 = CompanyModule(company_id=company.id, module_id=m1.id, activated_at=now, status="active")
    cm2 = CompanyModule(company_id=company.id, module_id=m2.id, activated_at=now, status="active")
    cm3 = CompanyModule(company_id=company.id, module_id=m3.id, activated_at=now, status="active")
    db_session.add_all([cm1, cm2, cm3])
    db_session.commit()
    db_session.refresh(company)

    schedule = CommercialReconciler.reconcile(company)
    assert schedule.is_blocked
    assert schedule.reconciliation_status == "COMMERCIAL_CONFIG_MISMATCH"
    assert any("Dépassement du quota de modules" in m for m in schedule.mismatches)


# ==========================================================================
# 3. TESTS DE DÉFI DE SIGNATURE & ANTI-REJEU (SigningChallengeService)
# ==========================================================================

def test_signing_challenge_lifecycle_and_replay_protection(db_session: Session):
    """Vérifie l'émission, la validation et l'interdiction de rejeu d'un défi de signature."""
    company = _create_company(db_session)
    user = _create_user(db_session, company)
    contract = ContractSignatureService(db_session).ensure_contracts_for_company(company)[0]
    challenge_service = SigningChallengeService(db_session)
    challenge, code = challenge_service.create_challenge(
        company_id=company.id, user_id=user.id, contract_id=contract.id,
        contract_version=contract.version, content_hash="content", commercial_hash="terms",
    )
    db_session.commit()
    arguments = dict(challenge_id=challenge.id, code=code, company_id=company.id,
                     user_id=user.id, contract_id=contract.id, contract_version=contract.version,
                     content_hash="content", commercial_hash="terms")
    assert len(code) == 8 and code.isdigit()
    assert challenge.used_at is None

    # 1. Échec avec mauvais code
    assert not challenge_service.verify_and_consume_challenge(**{**arguments, "code": "00000000"})
    assert not challenge_service.verify_and_consume_challenge(**{**arguments, "company_id": uuid4()})
    assert not challenge_service.verify_and_consume_challenge(**{**arguments, "commercial_hash": "changed"})

    # 2. Succès avec code valide
    assert challenge_service.verify_and_consume_challenge(**arguments)
    db_session.commit()

    # 3. Rejet immédiat au rejeu (jeton déjà consommé)
    assert not SigningChallengeService(db_session).verify_and_consume_challenge(**arguments)

    expired, expired_code = challenge_service.create_challenge(
        company_id=company.id, user_id=user.id, contract_id=contract.id,
        contract_version=contract.version, content_hash="content", commercial_hash="terms",
    )
    from datetime import timedelta
    expired.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert not challenge_service.verify_and_consume_challenge(**{
        **arguments, "challenge_id": expired.id, "code": expired_code,
    })

    locked, locked_code = challenge_service.create_challenge(
        company_id=company.id, user_id=user.id, contract_id=contract.id,
        contract_version=contract.version, content_hash="content", commercial_hash="terms",
    )
    db_session.commit()
    for _ in range(SigningChallengeService.MAX_ATTEMPTS):
        assert not challenge_service.verify_and_consume_challenge(**{
            **arguments, "challenge_id": locked.id, "code": "00000000" if locked_code != "00000000" else "11111111",
        })
    assert not challenge_service.verify_and_consume_challenge(**{
        **arguments, "challenge_id": locked.id, "code": locked_code,
    })


# ==========================================================================
# 4. TESTS DU CYCLE CONTRACTUEL ET CONTRESEING FOURNISSEUR
# ==========================================================================

def test_full_contract_lifecycle_customer_to_provider_countersign(db_session: Session):
    """Vérifie le cycle complet : provisionnement -> signature client -> contreseing fournisseur (FULLY_EXECUTED)."""
    company = _create_company(db_session, name="FinTech Corp")
    owner = _create_user(db_session, company, role=UserRole.OWNER)

    settings = get_settings().model_copy(update={"legal_signing_enabled": True, "provider_incorporation_verified": True, "provider_contracts_published": True,
                                                "provider_incorporation_status": "VERIFIED"})
    service = ContractSignatureService(db_session, settings=settings)
    service.ensure_contracts_for_company(company)

    contract = service.get_contract(company.id, "MUTUAL_NDA")
    assert contract.status == "PENDING_SIGNATURE"
    assert contract.execution_state == "PENDING_CUSTOMER"
    assert contract.provider_signed_at is None

    # Signature client
    schedule = CommercialReconciler.reconcile(company, settings)
    challenge, code = SigningChallengeService(db_session).create_challenge(
        company_id=company.id, user_id=owner.id, contract_id=contract.id,
        contract_version=contract.version, content_hash=service.compute_sha256(contract.content_text),
        commercial_hash=SigningChallengeService.snapshot_hash(schedule.to_dict()),
    )
    res = service.sign_contract_electronic(
        company=company,
        user=owner,
        contract_type="MUTUAL_NDA",
        signatory_title="Chef de la Direction",
        declared_authority=True,
        consent_checkbox=True,
        challenge_id=str(challenge.id), challenge_code=code,
    )
    assert res["status"] == "CUSTOMER_SIGNED"
    assert res["execution_state"] == "PENDING_PROVIDER"
    assert res["transaction_id"].startswith("TX-")

    db_session.refresh(contract)
    assert contract.provider_signed_at is None
    assert contract.completion_record_json["execution_party_states"]["provider"] == "PENDING_COUNTERSIGNATURE"

    # Contreseing par le fondateur / super admin de plateforme
    admin_user = _create_user(db_session, company, role=UserRole.ADMIN, is_platform_admin=True,
                              platform_role="PLATFORM_SUPER_ADMIN")
    executed = service.countersign_contract_provider(
        company_id=company.id,
        contract_type="MUTUAL_NDA",
        provider_user=admin_user,
        provider_name="Mircea Paul Cioban",
        provider_title="Président Fondateur",
    )

    assert executed.status == "FULLY_EXECUTED"
    assert executed.execution_state == "COMPLETED"
    assert executed.provider_signed_at is not None
    assert executed.provider_signatory_name == "Mircea Paul Cioban"
    assert executed.provider_signature_hash is not None
    assert executed.completion_record_json["execution_party_states"]["provider"] == "COMPLETED"


# ==========================================================================
# 5. TESTS DU CEO COMMAND CENTER & RBAC PLATEFORME
# ==========================================================================

def test_ceo_command_center_rbac_matrix(db_session: Session):
    """Vérifie que la matrice de permissions par rôle plateforme est strictement respectée."""
    company = _create_company(db_session)

    # 1. Utilisateur standard d'entreprise -> REJETÉ (403)
    normal_user = _create_user(db_session, company, role=UserRole.OWNER, is_platform_admin=False)
    normal_identity = CurrentIdentity(auth_session=None, user=normal_user, raw_token="token")
    dep_super = require_platform_role("PLATFORM_SUPER_ADMIN")

    with pytest.raises(Exception) as exc:
        dep_super(normal_identity)
    assert exc.value.status_code == 403

    # 2. Utilisateur Finance -> autorisé sur Finance, rejeté sur Sécurité
    finance_user = _create_user(
        db_session, company, role=UserRole.ADMIN, is_platform_admin=True, platform_role="PLATFORM_FINANCE"
    )
    finance_identity = CurrentIdentity(auth_session=None, user=finance_user, raw_token="token")

    dep_fin = require_platform_role("PLATFORM_SUPER_ADMIN", "PLATFORM_FINANCE")
    assert dep_fin(finance_identity) == finance_identity

    dep_sec = require_platform_role("PLATFORM_SUPER_ADMIN", "PLATFORM_SECURITY_AUDITOR")
    with pytest.raises(Exception) as exc_sec:
        dep_sec(finance_identity)
    assert exc_sec.value.status_code == 403

    # 3. Super Admin -> autorisé partout
    super_user = _create_user(
        db_session, company, role=UserRole.ADMIN, is_platform_admin=True, platform_role="PLATFORM_SUPER_ADMIN"
    )
    super_identity = CurrentIdentity(auth_session=None, user=super_user, raw_token="token")
    assert dep_sec(super_identity) == super_identity
    assert dep_fin(super_identity) == super_identity


def test_platform_admin_without_explicit_role_cannot_use_executive_endpoints(db_session: Session):
    company = _create_company(db_session)
    legacy_admin = _create_user(
        db_session, company, role=UserRole.OWNER, is_platform_admin=True, platform_role=None
    )
    identity = CurrentIdentity(auth_session=None, user=legacy_admin, raw_token="test-token")
    with pytest.raises(Exception) as exc:
        require_platform_role("PLATFORM_SUPER_ADMIN")(identity)
    assert exc.value.status_code == 403


def test_unpublished_provider_and_absent_challenge_fail_closed(db_session: Session):
    company = _create_company(db_session)
    owner = _create_user(db_session, company)
    unpublished = ContractSignatureService(db_session)
    unpublished.ensure_contracts_for_company(company)
    with pytest.raises(ContractAuthorityError, match="validation juridique"):
        unpublished.sign_contract_electronic(
            company=company, user=owner, contract_type="MUTUAL_NDA",
            signatory_title="Président", declared_authority=True, consent_checkbox=True,
        )

    verified_but_disabled = get_settings().model_copy(update={
        "provider_incorporation_verified": True,
        "provider_contracts_published": True,
        "provider_incorporation_status": "VERIFIED",
        "legal_signing_enabled": False,
    })
    with pytest.raises(ContractAuthorityError, match="validation juridique"):
        ContractSignatureService(db_session, settings=verified_but_disabled).sign_contract_electronic(
            company=company, user=owner, contract_type="MUTUAL_NDA",
            signatory_title="Président", declared_authority=True, consent_checkbox=True,
        )

    approved_in_synthetic_test = get_settings().model_copy(update={
        "legal_signing_enabled": True, "provider_incorporation_verified": True, "provider_contracts_published": True,
        "provider_incorporation_status": "VERIFIED",
    })
    service = ContractSignatureService(db_session, settings=approved_in_synthetic_test)
    with pytest.raises(ValueError, match="défi de signature"):
        service.sign_contract_electronic(
            company=company, user=owner, contract_type="MUTUAL_NDA",
            signatory_title="Président", declared_authority=True, consent_checkbox=True,
        )


def test_challenge_is_sent_out_of_band_and_not_returned_to_browser(db_session: Session):
    company = _create_company(db_session)
    owner = _create_user(db_session, company)
    settings = get_settings().model_copy(update={
        "legal_signing_enabled": True, "provider_incorporation_verified": True, "provider_contracts_published": True,
        "provider_incorporation_status": "VERIFIED",
    })
    service = ContractSignatureService(db_session, settings=settings)
    service.ensure_contracts_for_company(company)

    class FakeNotifier:
        email_delivery_configured = True
        deliveries: list[tuple[str, str, str]] = []

        def send_transactional(self, recipient: str, subject: str, body: str) -> None:
            self.deliveries.append((recipient, subject, body))

    notifier = FakeNotifier()
    result = create_signing_challenge(
        contract_type="MUTUAL_NDA", tenant=TenantContext(company_id=company.id),
        identity=CurrentIdentity(auth_session=None, user=owner, raw_token="synthetic"),
        db=db_session, notifier=notifier, service=service,
    )
    assert set(result) == {"challenge_id", "contract_type", "expires_at", "delivery"}
    assert result["delivery"] == "email"
    assert len(notifier.deliveries) == 1
    assert notifier.deliveries[0][0] == owner.email
    challenge = db_session.get(ContractSigningChallenge, UUID(result["challenge_id"]))
    assert challenge is not None and challenge.code_hash not in notifier.deliveries[0][2]


def test_ceo_financials_do_not_invent_paid_customers_or_mrr(db_session: Session):
    company = _create_company(db_session, plan="base")
    db_session.add(BillingAccount(company_id=company.id, plan_code="base", status="inactive"))
    db_session.commit()
    overview = get_executive_overview(range_filter="30d", db=db_session, settings=get_settings())
    assert overview["kpis"]["active_paid_customers"]["value"] == 0
    assert overview["kpis"]["mrr_cad"]["value"] is None
    assert overview["kpis"]["arr_cad"]["value"] is None
    assert overview["kpis"]["churn_rate_pct"]["value"] is None

    connectors = get_connectors_health(db=db_session)
    assert len(connectors["connectors"]) == 22
    assert all(c["heartbeat"] == "UNKNOWN" for c in connectors["connectors"])
    assert all(c["status"] != "OPERATIONAL" for c in connectors["connectors"])
