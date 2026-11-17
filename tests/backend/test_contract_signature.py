from datetime import datetime, timezone
from uuid import UUID, uuid4
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.config.settings import Settings
from backend.app.models.audit_log import AuditLogEntry
from backend.app.models.base import Base, CompanyStatus, UserRole
from backend.app.models.company import Company
from backend.app.models.company_contract import (
    ContractExecutionPartyState,
    ContractLifecycleStatus,
)
from backend.app.models.user import User
from backend.app.services.commercial_reconciler import CommercialReconciler
from backend.app.services.contract_signature_service import (
    APPROVED_FOR_CUSTOMER_SIGNING,
    ContractAuthorityError,
    ContractSignatureService,
)
from backend.app.services.signing_challenge_service import SigningChallengeService


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _sandbox_settings(tmp_path) -> Settings:
    return Settings(
        environment="sandbox",
        auth_jwt_secret="test-sandbox-jwt-secret-key-32-chars-minimum",
        artifact_root=str(tmp_path),
        provider_incorporation_status="UNVERIFIED_PENDING_INCORPORATION",
        legal_signing_enabled=False,
        provider_contracts_published=False,
    )


def _company_and_owner(db_session):
    company = Company(
        name="Produits Ero",
        slug=f"ero-{uuid4().hex[:8]}",
        email=f"ero-{uuid4().hex[:6]}@example.com",
        country="CA",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
        status=CompanyStatus.ACTIVE,
        currency_code="CAD",
    )
    db_session.add(company)
    db_session.flush()
    owner = User(
        company_id=company.id,
        first_name="Francis",
        last_name="Queval",
        email=f"francis-{uuid4().hex[:6]}@produits-ero.ca",
        password_hash="hashed",
        role=UserRole.OWNER,
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(owner)
    db_session.commit()
    return company, owner


def test_get_contract_templates_fr_and_en(db_session, tmp_path):
    service = ContractSignatureService(db_session, settings=_sandbox_settings(tmp_path))

    # SaaS Contract FR & EN
    saas_fr = service.get_template_raw("SAAS_SUBSCRIPTION", language="fr")
    assert saas_fr["contract_type"] == "SAAS_SUBSCRIPTION"
    assert saas_fr["language"] == "fr"
    assert "PMC Solutions AI" in saas_fr["content"]
    assert len(service.compute_sha256(saas_fr["content"])) == 64

    saas_en = service.get_template_raw("SAAS_SUBSCRIPTION", language="en")
    assert saas_en["language"] == "en"
    assert "PMC Solutions AI" in saas_en["content"]
    assert service.compute_sha256(saas_en["content"]) != service.compute_sha256(saas_fr["content"])

    # Private License Contract FR & EN (Non-Exclusive by default)
    lic_fr = service.get_template_raw("PRIVATE_LICENSE", language="fr")
    assert "non exclusive" in lic_fr["content"].lower()
    assert lic_fr["contract_type"] == "PRIVATE_LICENSE"

    lic_en = service.get_template_raw("PRIVATE_LICENSE", language="en")
    assert "non-exclusive" in lic_en["content"].lower()
    assert lic_en["contract_type"] == "PRIVATE_LICENSE"


def test_sign_contract_requires_explicit_consent(db_session, tmp_path):
    company, owner = _company_and_owner(db_session)
    service = ContractSignatureService(db_session, settings=_sandbox_settings(tmp_path))
    service.ensure_contracts_for_company(company)

    with pytest.raises(ValueError, match="consentement exprès"):
        service.sign_contract_electronic(
            company=company,
            user=owner,
            contract_type="SAAS_SUBSCRIPTION",
            signatory_title="Président",
            declared_authority=True,
            consent_checkbox=False,
        )


def test_sign_msa_dpa_with_otp_and_keep_nda_blocked_until_legal_approval(db_session, tmp_path):
    settings = _sandbox_settings(tmp_path)
    company, owner = _company_and_owner(db_session)
    service = ContractSignatureService(db_session, settings=settings)
    service.ensure_contracts_for_company(company)

    # 1. NDA stays blocked until explicit legal reviewer approval
    nda = service.get_contract(company.id, "MUTUAL_NDA")
    assert service.signature_blocked(nda) is True
    with pytest.raises(ContractAuthorityError, match="révision juridique"):
        service.sign_contract_electronic(
            company=company,
            user=owner,
            contract_type="MUTUAL_NDA",
            signatory_title="Président",
            declared_authority=True,
            consent_checkbox=True,
        )

    # 2. MSA & DPA can be signed electronically in pilot/sandbox with valid OTP challenge
    schedule = CommercialReconciler.reconcile(company, settings).to_dict()
    for ctype in ("SAAS_SUBSCRIPTION", "DATA_PROCESSING_ADDENDUM"):
        contract = service.get_contract(company.id, ctype)
        challenge, otp_code = SigningChallengeService(db_session).create_challenge(
            company_id=company.id,
            user_id=owner.id,
            contract_id=contract.id,
            contract_version=contract.version,
            content_hash=service.compute_sha256(contract.content_text),
            commercial_hash=SigningChallengeService.snapshot_hash(schedule),
        )
        receipt = service.sign_contract_electronic(
            company=company,
            user=owner,
            contract_type=ctype,
            signatory_title="Président",
            declared_authority=True,
            consent_checkbox=True,
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0 TestBrowser",
            challenge_id=str(challenge.id),
            challenge_code=otp_code,
        )
        assert receipt["contract_type"] == ctype
        assert receipt["status"] == ContractLifecycleStatus.CUSTOMER_SIGNED.value
        assert receipt["execution_state"] == ContractExecutionPartyState.PENDING_PROVIDER.value
        assert len(receipt["sha256_hash"]) == 64
        assert receipt["receipt_id"]

        reloaded = service.get_contract(company.id, ctype)
        assert str(reloaded.audit_receipt_id) == receipt["receipt_id"]
        assert reloaded.completion_record_json is not None
        assert reloaded.completion_record_json["contract_sha256"] == receipt["sha256_hash"]
        assert reloaded.completion_record_json["signer_email"] == owner.email
        assert reloaded.completion_record_json["provider_countersigned"] is False

    assert service.sandbox_saas_accepted(company.id) is True

    # 3. Only a platform legal reviewer can unlock NDA; never fabricated automatically
    reviewer = User(
        company_id=company.id,
        first_name="Legal",
        last_name="Reviewer",
        email=f"legal-{uuid4().hex[:6]}@avenqo.ca",
        password_hash="hashed",
        role=UserRole.ADMIN,
        is_active=True,
        is_platform_admin=True,
        platform_role="PLATFORM_LEGAL_REVIEWER",
    )
    db_session.add(reviewer)
    db_session.commit()

    approved_nda = service.approve_contract_version_for_signing(
        company_id=company.id,
        contract_type="MUTUAL_NDA",
        reviewer=reviewer,
    )
    assert service.approval_status_of(approved_nda) == APPROVED_FOR_CUSTOMER_SIGNING
    assert service.signature_blocked(approved_nda) is False
