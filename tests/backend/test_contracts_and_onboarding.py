"""Tests de conformité et de non-régression pour les contrats juridiques obligatoires et l'onboarding entreprise."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.dependencies.subscription import require_active_subscription, CONTRACT_SIGNATURE_REQUIRED_CODE
from backend.app.models.base import Base, UserRole, CompanyStatus
from backend.app.models.billing import BillingAccount
from backend.app.models.company import Company
from backend.app.models.company_contract import CompanyContract
from backend.app.models.company_onboarding import CompanyOnboarding
from backend.app.models.user import User
from backend.app.services.contract_pdf_generator import ContractPdfGenerator
from backend.app.services.contract_signature_service import (
    ContractSignatureService,
    ContractNotFoundError,
    ContractAlreadySignedError,
    ContractAuthorityError,
    InvalidSignatureModeError,
)
from backend.app.services.onboarding_service import OnboardingService
from backend.app.schemas.onboarding import OnboardingDraftRequest, OnboardingSubmitRequest
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test_contracts.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


def _create_test_company(session, name="Produits_Ero Inc.", plan="professional"):
    company_id = uuid4()
    company = Company(
        id=company_id,
        name=name,
        slug=f"{name.lower().replace(' ', '-').replace('.', '')}-{uuid4().hex[:6]}",
        email=f"contact-{uuid4().hex[:6]}@example.com",
        billing_email=f"billing-{uuid4().hex[:6]}@example.com",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan=plan,
        status=CompanyStatus.ACTIVE,
    )
    session.add(company)
    session.flush()

    account = BillingAccount(
        company_id=company_id,
        plan_code=plan,
        status="active",
        stripe_customer_id=f"cus_{uuid4().hex[:12]}",
        stripe_subscription_id=f"sub_{uuid4().hex[:12]}",
    )
    session.add(account)

    onboarding = CompanyOnboarding(
        company_id=company_id,
        draft_payload={},
    )
    session.add(onboarding)
    session.commit()
    return company


def _create_user(session, company, role=UserRole.OWNER):
    user = User(
        id=uuid4(),
        company_id=company.id,
        email=f"{role.value}-{uuid4().hex[:6]}@example.com",
        first_name="Paul",
        last_name="Gauffre",
        password_hash="hashed_pw_test",
        role=role,
    )
    session.add(user)
    session.commit()
    return user


def test_contract_templates_dynamic_interpolation(db_session):
    """Vérifie que les variables {{...}} sont interpolées avec des données réelles et que PMC Solutions AI est qualifiée légalement."""
    company = _create_test_company(db_session, name="Produits_Ero Canada")
    service = ContractSignatureService(db_session)
    contracts = service.ensure_contracts_for_company(company)

    assert len(contracts) >= 3  # NDA, MSA, DPA
    nda = next(c for c in contracts if c.contract_type == "MUTUAL_NDA")

    assert "Produits_Ero Canada" in nda.content_text
    assert "PMC SOLUTIONS AI" in nda.content_text
    assert "entreprise en cours d'incorporation au Québec, Canada" in nda.content_text
    assert "{{COMPANY_NAME}}" not in nda.content_text
    assert "{{EFFECTIVE_DATE}}" not in nda.content_text


def test_certified_pdf_generation(tmp_path):
    """Vérifie que le générateur ReportLab produit un PDF certifié valide avec métadonnées et sceau d'audit."""
    content_md = """# ACCORD DE CONFIDENTIALITÉ RÉCIPROQUE (MUTUAL NDA)

Cet accord est conclu entre PMC SOLUTIONS AI et **Test Client Inc.**

## 1. DÉFINITIONS
Les informations confidentielles comprennent l'ensemble des données d'entreprise et algorithmes.

## 2. OBLIGATIONS
Chaque partie s'engage à protéger les informations de l'autre."""

    pdf_bytes = ContractPdfGenerator.generate_pdf(
        contract_title="Mutual NDA",
        contract_type="MUTUAL_NDA",
        contract_version="1.0",
        company_name="Test Client Inc.",
        company_id=str(uuid4()),
        signatory_name="Paul Gauffre",
        signatory_title="Président & Directeur Général",
        signatory_email="paul@example.com",
        plan_code="professional",
        plan_price="49,99 CAD / mois",
        active_modules=["crm", "retail"],
        content_text=content_md,
        sha256_hash="a1b2c3d4e5f678901234567890abcdef1234567890abcdef1234567890abcdef",
        signed_at=datetime.now(timezone.utc),
        signature_mode="ELECTRONIC",
        audit_receipt_id="AVQ-AUDIT-TEST-1234",
    )

    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-")


def test_signatory_authority_enforcement(db_session):
    """Vérifie que seuls OWNER et ADMIN peuvent engager l'entreprise et que MEMBER est strictement rejeté."""
    company = _create_test_company(db_session)
    service = ContractSignatureService(db_session)
    service.ensure_contracts_for_company(company)

    owner = _create_user(db_session, company, role=UserRole.OWNER)
    member = _create_user(db_session, company, role=UserRole.USER)

    # Membre sans autorité légale -> rejet immédiat
    with pytest.raises(ContractAuthorityError) as exc_info:
        service.verify_signatory_authority(member, company.id, declared_authority=True)
    assert "Autorité insuffisante" in str(exc_info.value)

    # Propriétaire avec déclaration explicite -> accepté
    service.verify_signatory_authority(owner, company.id, declared_authority=True)

    # Propriétaire qui omet de cocher l'engagement -> rejet
    with pytest.raises(ContractAuthorityError) as exc_info:
        service.verify_signatory_authority(owner, company.id, declared_authority=False)
    assert "pouvoir d'engagement légal" in str(exc_info.value)


def test_electronic_signature_flow(db_session, tmp_path):
    """Vérifie le cycle complet de signature électronique: hash SHA-256, reçu d'audit, PDF archivé et statut SIGNED."""
    company = _create_test_company(db_session)
    owner = _create_user(db_session, company, role=UserRole.OWNER)

    service = ContractSignatureService(db_session)
    service.ensure_contracts_for_company(company)

    res = service.sign_contract_electronic(
        company=company,
        user=owner,
        contract_type="MUTUAL_NDA",
        signatory_title="Chef de la Direction",
        declared_authority=True,
        consent_checkbox=True,
    )

    assert res["status"] == "SIGNED"
    assert res["signature_mode"] == "ELECTRONIC"
    assert res["signatory_name"] == "Paul Gauffre"
    assert res["signatory_title"] == "Chef de la Direction"
    assert len(res["sha256_hash"]) == 64
    assert res["storage_path"] is not None

    contract_db = service.get_contract(company.id, "MUTUAL_NDA")
    assert contract_db.status == "SIGNED"
    assert contract_db.storage_path is not None

    # Tentative de re-signature d'un contrat déjà signé -> rejet
    with pytest.raises(ContractAlreadySignedError):
        service.sign_contract_electronic(
            company=company,
            user=owner,
            contract_type="MUTUAL_NDA",
            signatory_title="Chef de la Direction",
            declared_authority=True,
            consent_checkbox=True,
        )


def test_wet_ink_manuscript_flow(db_session):
    """Vérifie l'archivage d'un contrat signé manuscritement (wet-ink)."""
    company = _create_test_company(db_session)
    owner = _create_user(db_session, company, role=UserRole.OWNER)

    service = ContractSignatureService(db_session)
    service.ensure_contracts_for_company(company)

    mock_pdf_bytes = b"%PDF-1.4 Mock manuscript scan signed with wet ink"

    res = service.upload_wet_ink_signature(
        company=company,
        user=owner,
        contract_type="SAAS_SUBSCRIPTION",
        signatory_title="Président",
        file_bytes=mock_pdf_bytes,
        filename="contrat_signe_scan.pdf",
    )

    assert res["status"] == "SIGNED"
    assert res["signature_mode"] == "MANUSCRIPT_WET_INK"

    contract_db = service.get_contract(company.id, "SAAS_SUBSCRIPTION")
    assert contract_db.status == "SIGNED"
    assert contract_db.signature_mode == "MANUSCRIPT_WET_INK"
    assert contract_db.storage_path is not None


def test_contracts_multi_tenant_isolation(db_session):
    """Vérifie l'étanchéité multi-tenant absolue: Entreprise B ne peut ni consulter ni signer les contrats de l'Entreprise A."""
    company_a = _create_test_company(db_session, name="Entreprise A")
    company_b = _create_test_company(db_session, name="Entreprise B")

    owner_b = _create_user(db_session, company_b, role=UserRole.OWNER)

    service = ContractSignatureService(db_session)
    service.ensure_contracts_for_company(company_a)
    service.ensure_contracts_for_company(company_b)

    contracts_a = service.list_contracts(company_a.id)
    assert all(c.company_id == company_a.id for c in contracts_a)

    # Propriétaire B tente d'engager le contrat de l'Entreprise A
    with pytest.raises(ContractAuthorityError) as exc_info:
        service.verify_signatory_authority(owner_b, company_a.id, declared_authority=True)
    assert "Violation multi-tenant" in str(exc_info.value)


def test_mandatory_contracts_gate_blocks_and_activates(db_session):
    """Vérifie que les services payants sont bloqués (403 contract_signature_required) tant que les contrats ne sont pas signés."""
    company = _create_test_company(db_session, name="Entreprise Gate Test", plan="professional")
    owner = _create_user(db_session, company, role=UserRole.OWNER)

    service = ContractSignatureService(db_session)
    service.ensure_contracts_for_company(company)

    tenant = TenantContext(company_id=company.id)

    # 1. Avant signature: has_signed_mandatory_contracts est FAUX
    assert service.has_signed_mandatory_contracts(company.id) is False

    # 2. require_active_subscription lève HTTP 403 avec code explicite
    with pytest.raises(HTTPException) as exc_info:
        require_active_subscription(tenant, db_session)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == CONTRACT_SIGNATURE_REQUIRED_CODE

    # 3. Signature du Mutual NDA seulement: toujours pas complet
    service.sign_contract_electronic(
        company=company,
        user=owner,
        contract_type="MUTUAL_NDA",
        signatory_title="CEO",
        declared_authority=True,
        consent_checkbox=True,
    )
    assert service.has_signed_mandatory_contracts(company.id) is False

    # 4. Signature du SaaS Subscription: désormais complet
    service.sign_contract_electronic(
        company=company,
        user=owner,
        contract_type="SAAS_SUBSCRIPTION",
        signatory_title="CEO",
        declared_authority=True,
        consent_checkbox=True,
    )
    assert service.has_signed_mandatory_contracts(company.id) is True

    # 5. require_active_subscription passe avec succès !
    assert require_active_subscription(tenant, db_session) is tenant


def test_onboarding_customization_and_checklist(db_session):
    """Vérifie que l'onboarding enregistre la personnalisation white-label (logo, thème, couleur) et suit les contrats."""
    company = _create_test_company(db_session, name="WhiteLabel Shop")
    owner = _create_user(db_session, company, role=UserRole.OWNER)
    tenant = TenantContext(company_id=company.id)

    onboarding_service = OnboardingService(db_session)

    # Mise à jour du brouillon d'onboarding avec personnalisation white-label
    update_req = OnboardingDraftRequest(
        current_step="customization",
        company_logo_url="https://whitelabel.test/assets/logo.png",
        theme_mode="dark",
        brand_color="#7B2CBF",
        selected_modules=("crm", "retail"),
    )

    resp = onboarding_service.save_draft(tenant, update_req)

    assert resp.company_logo_url == "https://whitelabel.test/assets/logo.png"
    assert resp.theme_mode == "dark"
    assert resp.brand_color == "#7B2CBF"

    # Checklist vérification
    checklist_keys = [item["key"] for item in resp.checklist]
    assert "space" in checklist_keys
    assert "customization" in checklist_keys
    assert "contracts" in checklist_keys

    # Étape personnalisation validée
    custom_item = next(item for item in resp.checklist if item["key"] == "customization")
    assert custom_item["done"] is True
