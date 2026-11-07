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
from backend.app.config.settings import get_settings
from backend.app.services.commercial_reconciler import CommercialReconciler
from backend.app.services.signing_challenge_service import SigningChallengeService
from backend.app.routers.contracts import download_contract_pdf
from backend.app.dependencies.subscription import require_signed_mandatory_contracts
from backend.app.services.contract_pdf_generator import ContractPdfGenerator
from backend.app.services.contract_signature_service import (
    ContractSignatureService,
    ContractAlreadySignedError,
    ContractAuthorityError,
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
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.commit()
    return user


def _synthetic_sign(service, company, user, contract_type):
    contract = service.get_contract(company.id, contract_type)
    schedule = CommercialReconciler.reconcile(company, service._settings)
    challenge, code = SigningChallengeService(service._db).create_challenge(
        company_id=company.id, user_id=user.id, contract_id=contract.id,
        contract_version=contract.version, content_hash=service.compute_sha256(contract.content_text),
        commercial_hash=SigningChallengeService.snapshot_hash(schedule.to_dict()),
    )
    return service.sign_contract_electronic(
        company=company, user=user, contract_type=contract_type,
        signatory_title="Chef de la Direction", declared_authority=True, consent_checkbox=True,
        challenge_id=str(challenge.id), challenge_code=code,
    )


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
    priv_raw = service.get_template_raw("PRIVATE_LICENSE", language="fr")
    priv_interp = service.interpolate_contract_text(priv_raw["content"], company=company)
    assert "PMC SOLUTIONS AI" in priv_interp
    assert "entreprise en cours d'incorporation au Québec, Canada" in priv_interp
    assert "{{COMPANY_NAME}}" not in priv_interp


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

    settings = get_settings().model_copy(update={"legal_signing_enabled": True, "provider_incorporation_verified": True, "provider_contracts_published": True,
                                                "provider_incorporation_status": "VERIFIED",
                                                "artifact_root": str(tmp_path)})
    service = ContractSignatureService(db_session, settings=settings)
    service.ensure_contracts_for_company(company)

    res = _synthetic_sign(service, company, owner, "MUTUAL_NDA")

    assert res["status"] == "CUSTOMER_SIGNED"
    assert res["signature_mode"] == "ELECTRONIC"
    assert res["signatory_name"] == "Paul Gauffre"
    assert res["signatory_title"] == "Chef de la Direction"
    assert len(res["sha256_hash"]) == 64
    assert res["storage_path"] is not None

    contract_db = service.get_contract(company.id, "MUTUAL_NDA")
    assert contract_db.status == "CUSTOMER_SIGNED"
    assert contract_db.storage_path is not None
    assert contract_db.pdf_sha256 == service.compute_sha256((tmp_path / contract_db.storage_path).read_bytes())
    (tmp_path / contract_db.storage_path).write_bytes(b"tampered synthetic PDF")
    with pytest.raises(HTTPException) as integrity_error:
        download_contract_pdf("MUTUAL_NDA", TenantContext(company_id=company.id), db_session, service)
    assert integrity_error.value.status_code == 500

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
    """Vérifie le cycle complet d'un contrat manuscrit : rejet format, PENDING_VERIFICATION puis validation."""
    company = _create_test_company(db_session)
    owner = _create_user(db_session, company, role=UserRole.OWNER)

    settings = get_settings().model_copy(update={"legal_signing_enabled": True, "provider_incorporation_verified": True, "provider_contracts_published": True,
                                                "provider_incorporation_status": "VERIFIED"})
    service = ContractSignatureService(db_session, settings=settings)
    service.ensure_contracts_for_company(company)

    # 1. Rejet fail-closed sur format non autorisé
    with pytest.raises(ValueError, match="Format de fichier non supporté"):
        service.upload_wet_ink_signature(
            company=company,
            user=owner,
            contract_type="SAAS_SUBSCRIPTION",
            signatory_title="Président",
            file_bytes=b"invalid plain text document that is not pdf or image" * 4,
            filename="contrat.txt",
        )

    # 2. Upload valide avec magic bytes PDF
    mock_pdf_bytes = b"%PDF-1.4 Mock manuscript scan signed with wet ink and verified signature block" + (b"0" * 100)

    res = service.upload_wet_ink_signature(
        company=company,
        user=owner,
        contract_type="SAAS_SUBSCRIPTION",
        signatory_title="Président",
        file_bytes=mock_pdf_bytes,
        filename="contrat_signe_scan.pdf",
    )

    assert res["status"] == "PENDING_VERIFICATION"
    assert res["signature_mode"] == "MANUSCRIPT_WET_INK"

    contract_db = service.get_contract(company.id, "SAAS_SUBSCRIPTION")
    assert contract_db.status == "PENDING_VERIFICATION"
    assert contract_db.signature_mode == "MANUSCRIPT_WET_INK"
    assert contract_db.storage_path is not None

    # 3. Le signataire ne peut jamais approuver sa propre pièce.
    with pytest.raises(ContractAuthorityError):
        service.verify_wet_ink_signature(
            company_id=company.id, contract_type="SAAS_SUBSCRIPTION", approved=True,
            verifier_user=owner,
        )
    verifier = _create_user(db_session, company, role=UserRole.ADMIN)
    verifier.is_platform_admin = True
    verifier.platform_role = "PLATFORM_SUPER_ADMIN"
    db_session.commit()
    with pytest.raises(ValueError, match="non encore signé"):
        service.countersign_contract_provider(
            company_id=company.id, contract_type="SAAS_SUBSCRIPTION", provider_user=verifier,
        )
    verified = service.verify_wet_ink_signature(
        company_id=company.id,
        contract_type="SAAS_SUBSCRIPTION",
        approved=True,
        verifier_user=verifier,
    )
    assert verified.status == "CUSTOMER_SIGNED"
    assert verified.execution_state == "PENDING_PROVIDER"


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
    """An established paid tenant keeps access; new contract onboarding has its own gate."""
    company = _create_test_company(db_session, name="Entreprise Gate Test", plan="professional")
    service = ContractSignatureService(db_session)
    service.ensure_contracts_for_company(company)

    tenant = TenantContext(company_id=company.id)

    # 1. Avant signature: has_signed_mandatory_contracts est FAUX
    assert service.has_signed_mandatory_contracts(company.id) is False

    # The historical subscription is not silently canceled by a new legal workflow.
    assert require_active_subscription(tenant, db_session) is tenant

    # Explicit prospective onboarding remains fail closed until complete execution.
    with pytest.raises(HTTPException) as exc_info:
        require_signed_mandatory_contracts(tenant, db_session)
    assert exc_info.value.status_code == 403
    assert isinstance(exc_info.value.detail, dict)
    assert exc_info.value.detail.get("code") == "contract_governance_unavailable"


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
