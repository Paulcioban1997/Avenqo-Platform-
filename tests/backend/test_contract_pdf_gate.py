"""PDF text, review lock, download without a code, and the onboarding gate."""

from datetime import datetime, timedelta, timezone
from io import BytesIO
from uuid import uuid4

import pytest
from pypdf import PdfReader
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.dependencies.auth import CurrentIdentity
from backend.app.models.base import Base, CompanyStatus, UserRole
from backend.app.models.billing import BillingAccount
from backend.app.models.company import Company
from backend.app.models.company_contract import CompanyContract
from backend.app.models.contract_signing_challenge import ContractSigningChallenge
from backend.app.models.user import User
from backend.app.routers.contracts import assert_contract_reader, download_contract_pdf
from backend.app.services.commercial_reconciler import CommercialReconciler
from backend.app.services.contract_pdf_generator import ContractPdfGenerator, contract_markup
from backend.app.services.contract_signature_service import (
    ContractAuthorityError,
    ContractSignatureService,
)
from backend.app.services.onboarding_service import OnboardingService
from backend.app.services.signing_challenge_service import SigningChallengeService
from fastapi import HTTPException
from payments.plans import PLANS_BY_CODE, PlanCode
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gate.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


def _settings(tmp_path):
    from backend.app.config.settings import get_settings

    return get_settings().model_copy(update={
        "environment": "sandbox",
        "legal_signing_enabled": False,
        "provider_incorporation_verified": False,
        "provider_contracts_published": False,
        "provider_incorporation_status": "UNVERIFIED_PENDING_INCORPORATION",
        "artifact_root": str(tmp_path),
    })


def _company(session, *, plan="base") -> Company:
    company = Company(
        name="Nouvelle Société",
        slug=f"co-{uuid4().hex[:8]}",
        email=f"co-{uuid4().hex[:6]}@example.com",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan=plan,
        status=CompanyStatus.ACTIVE,
        currency_code="CAD",
    )
    session.add(company)
    session.commit()
    return company


def _user(session, company, role=UserRole.OWNER) -> User:
    user = User(
        company_id=company.id,
        first_name="Ada",
        last_name="Martin",
        email=f"{role.value}-{uuid4().hex[:6]}@example.com",
        password_hash="hashed",
        role=role,
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.commit()
    return user


def _sign(service, company, user, contract_type):
    contract = service.get_contract(company.id, contract_type)
    schedule = CommercialReconciler.reconcile(company, service._settings)
    challenge, code = SigningChallengeService(service._db).create_challenge(
        company_id=company.id,
        user_id=user.id,
        contract_id=contract.id,
        contract_version=contract.version,
        content_hash=service.compute_sha256(contract.content_text),
        commercial_hash=SigningChallengeService.snapshot_hash(schedule.to_dict()),
    )
    return service.sign_contract_electronic(
        company=company,
        user=user,
        contract_type=contract_type,
        signatory_title="Présidente",
        declared_authority=True,
        consent_checkbox=True,
        challenge_id=str(challenge.id),
        challenge_code=code,
    )


def test_pdf_generation_has_no_markdown_markers():
    marked = "### **Article 1**\n\nLe client **Nouvelle Société** accepte le service."
    assert "###" not in contract_markup(marked)
    assert "**" not in contract_markup(marked)
    pdf_bytes = ContractPdfGenerator.generate_pdf(
        contract_title="Contrat SaaS",
        contract_type="SAAS_SUBSCRIPTION",
        contract_version="2026-V1",
        company_name="Nouvelle Société",
        company_id=str(uuid4()),
        signatory_name="Ada Martin",
        signatory_title="Présidente",
        signatory_email="ada@example.com",
        plan_code="base",
        plan_price="29,99 CAD / mois",
        active_modules=["crm"],
        content_text=marked,
        sha256_hash="ab" * 32,
        is_draft=True,
        is_sandbox=True,
    )
    text = "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(pdf_bytes)).pages)
    assert "###" not in text
    assert "**" not in text
    assert "Nouvelle Société" in text
    assert "Article 1" in text


def test_unapproved_documents_cannot_be_signed(db_session, tmp_path):
    company = _company(db_session)
    owner = _user(db_session, company)
    service = ContractSignatureService(db_session, settings=_settings(tmp_path))
    service.ensure_contracts_for_company(company)

    with pytest.raises(ContractAuthorityError, match="révision juridique"):
        _sign(service, company, owner, "MUTUAL_NDA")
    nda = service.get_contract(company.id, "MUTUAL_NDA")
    assert nda.status == "PENDING_SIGNATURE"
    assert nda.signed_at is None
    assert service.approval_status_of(nda) == "LEGAL_REVIEW_REQUIRED"

    saas = service.get_contract(company.id, "SAAS_SUBSCRIPTION")
    saas.metadata_json = {"approval_status": "UNDER_REVIEW"}
    db_session.commit()
    with pytest.raises(ContractAuthorityError, match="révision juridique"):
        _sign(service, company, owner, "SAAS_SUBSCRIPTION")
    assert service.get_contract(company.id, "SAAS_SUBSCRIPTION").signed_at is None


def test_download_does_not_require_a_code_and_checks_permission(db_session, tmp_path):
    company = _company(db_session)
    owner = _user(db_session, company)
    member = _user(db_session, company, UserRole.USER)
    other = _company(db_session, plan="professional")
    outsider = _user(db_session, other)
    service = ContractSignatureService(db_session, settings=_settings(tmp_path))
    service.ensure_contracts_for_company(company)
    before = db_session.scalar(select(ContractSigningChallenge).limit(1))
    response = download_contract_pdf(
        "SAAS_SUBSCRIPTION",
        TenantContext(company_id=company.id),
        db_session,
        service,
    )
    assert response.status_code == 200
    assert response.body.startswith(b"%PDF-")
    assert "2026-V1" in response.headers["content-disposition"]
    assert db_session.scalar(select(ContractSigningChallenge).limit(1)) is before

    owner_identity = CurrentIdentity(None, owner, "token")
    assert_contract_reader(owner_identity, TenantContext(company_id=company.id))

    member_identity = CurrentIdentity(None, member, "token")
    with pytest.raises(HTTPException) as denied:
        assert_contract_reader(member_identity, TenantContext(company_id=company.id))
    assert denied.value.status_code == 403

    outsider_identity = CurrentIdentity(None, outsider, "token")
    with pytest.raises(HTTPException) as crossed:
        assert_contract_reader(outsider_identity, TenantContext(company_id=company.id))
    assert crossed.value.status_code == 403


def test_invalid_expired_and_reused_codes_do_not_sign(db_session, tmp_path):
    company = _company(db_session)
    owner = _user(db_session, company)
    service = ContractSignatureService(db_session, settings=_settings(tmp_path))
    service.ensure_contracts_for_company(company)
    contract = service.get_contract(company.id, "DATA_PROCESSING_ADDENDUM")
    schedule = CommercialReconciler.reconcile(company, service._settings)
    challenges = SigningChallengeService(db_session)
    content_hash = service.compute_sha256(contract.content_text)
    commercial_hash = SigningChallengeService.snapshot_hash(schedule.to_dict())

    wrong, _code = challenges.create_challenge(
        company_id=company.id, user_id=owner.id, contract_id=contract.id,
        contract_version=contract.version, content_hash=content_hash, commercial_hash=commercial_hash,
    )
    assert challenges.verify_and_consume_challenge(
        challenge_id=wrong.id, code="00000000", company_id=company.id, user_id=owner.id,
        contract_id=contract.id, contract_version=contract.version,
        content_hash=content_hash, commercial_hash=commercial_hash,
    ) is False

    expired, expired_code = challenges.create_challenge(
        company_id=company.id, user_id=owner.id, contract_id=contract.id,
        contract_version=contract.version, content_hash=content_hash, commercial_hash=commercial_hash,
    )
    expired.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    assert challenges.verify_and_consume_challenge(
        challenge_id=expired.id, code=expired_code, company_id=company.id, user_id=owner.id,
        contract_id=contract.id, contract_version=contract.version,
        content_hash=content_hash, commercial_hash=commercial_hash,
    ) is False

    fresh, fresh_code = challenges.create_challenge(
        company_id=company.id, user_id=owner.id, contract_id=contract.id,
        contract_version=contract.version, content_hash=content_hash, commercial_hash=commercial_hash,
    )
    assert challenges.verify_and_consume_challenge(
        challenge_id=fresh.id, code=fresh_code, company_id=company.id, user_id=owner.id,
        contract_id=contract.id, contract_version=contract.version,
        content_hash=content_hash, commercial_hash=commercial_hash,
    ) is True
    assert challenges.verify_and_consume_challenge(
        challenge_id=fresh.id, code=fresh_code, company_id=company.id, user_id=owner.id,
        contract_id=contract.id, contract_version=contract.version,
        content_hash=content_hash, commercial_hash=commercial_hash,
    ) is False

    other = _company(db_session)
    isolated, isolated_code = challenges.create_challenge(
        company_id=company.id, user_id=owner.id, contract_id=contract.id,
        contract_version=contract.version, content_hash=content_hash, commercial_hash=commercial_hash,
    )
    assert challenges.verify_and_consume_challenge(
        challenge_id=isolated.id, code=isolated_code, company_id=other.id, user_id=owner.id,
        contract_id=contract.id, contract_version=contract.version,
        content_hash=content_hash, commercial_hash=commercial_hash,
    ) is False
    assert service.get_contract(company.id, "DATA_PROCESSING_ADDENDUM").signed_at is None


def test_private_license_is_not_required_and_prices_stay_put(db_session, tmp_path):
    assert PLANS_BY_CODE[PlanCode.BASE].monthly_price_cad == 29.99
    assert PLANS_BY_CODE[PlanCode.PROFESSIONAL].monthly_price_cad == 49.99
    company = _company(db_session, plan="base")
    owner = _user(db_session, company)
    service = ContractSignatureService(db_session, settings=_settings(tmp_path))
    service.ensure_contracts_for_company(company)
    _sign(service, company, owner, "SAAS_SUBSCRIPTION")
    _sign(service, company, owner, "DATA_PROCESSING_ADDENDUM")
    assert service.get_contract(company.id, "PRIVATE_LICENSE").status == "PENDING_SIGNATURE"
    assert service.required_saas_accepted(company.id) is True
    assert service.sandbox_saas_accepted(company.id) is True


def test_new_company_gate_and_legacy_session_stay_distinct(db_session, tmp_path):
    company = _company(db_session)
    owner = _user(db_session, company)
    service = ContractSignatureService(db_session, settings=_settings(tmp_path))
    onboarding = OnboardingService(db_session)
    tenant = TenantContext(company_id=company.id, user_id=owner.id)
    onboarding.update_step(tenant, "modules", {"selected_modules": ["crm"]})
    onboarding.update_step(tenant, "contracts", {"accepted_contract_types": ["SAAS_SUBSCRIPTION"], "accepted_by_name": "Ada"})
    saas = service.get_contract(company.id, "SAAS_SUBSCRIPTION")
    assert saas.status == "PENDING_SIGNATURE"
    assert saas.signed_at is None
    access = onboarding.workspace_access(tenant)
    assert access["workspace_open"] is False
    assert access["invited_member"] is False
    assert access["private_license_required"] is False
    assert access["saas_accepted"] is False
    assert access["next_path"] == "/settings/contracts"
    with pytest.raises(ValueError, match="accords SaaS"):
        onboarding.finalize_onboarding(tenant)

    onboarding.activate_selected_modules(tenant, ("crm",))
    account = db_session.scalar(select(BillingAccount).where(BillingAccount.company_id == company.id))
    if account is None:
        account = BillingAccount(company_id=company.id, plan_code="base", status="active", stripe_customer_id="cus_reconcile")
        db_session.add(account)
    account.status = "active"
    account.stripe_customer_id = "cus_reconcile"
    account.stripe_subscription_id = None
    db_session.commit()
    legacy = onboarding.workspace_access(tenant)
    assert legacy["legacy_session"] is True
    assert legacy["workspace_open"] is True
    assert legacy["stripe_confirmed"] is False
    assert legacy["checkout_path"] == "/onboarding/checkout"


def test_invited_employee_skips_commercial_gate(db_session, tmp_path):
    company = _company(db_session)
    _user(db_session, company)
    employee = _user(db_session, company, UserRole.USER)
    ContractSignatureService(db_session, settings=_settings(tmp_path)).ensure_contracts_for_company(company)
    access = OnboardingService(db_session).workspace_access(
        TenantContext(company_id=company.id, user_id=employee.id)
    )
    assert access["invited_member"] is True
    assert access["workspace_open"] is True
    assert access["saas_accepted"] is False
    assert access["stripe_confirmed"] is False
    assert access["next_path"] == "/dashboard"
    assert access["private_license_required"] is False


def test_signed_saas_stays_accepted_when_other_docs_are_under_review(db_session, tmp_path):
    company = _company(db_session)
    owner = _user(db_session, company)
    service = ContractSignatureService(db_session, settings=_settings(tmp_path))
    service.ensure_contracts_for_company(company)
    _sign(service, company, owner, "SAAS_SUBSCRIPTION")
    _sign(service, company, owner, "DATA_PROCESSING_ADDENDUM")
    nda = service.get_contract(company.id, "MUTUAL_NDA")
    nda.metadata_json = {"approval_status": "UNDER_REVIEW"}
    saas = service.get_contract(company.id, "SAAS_SUBSCRIPTION")
    saas.metadata_json = {**(saas.metadata_json or {}), "approval_status": "UNDER_REVIEW"}
    db_session.commit()
    assert service.required_saas_accepted(company.id) is True
    assert service.get_contract(company.id, "SAAS_SUBSCRIPTION").status in {
        "CUSTOMER_SIGNED", "SIGNED", "FULLY_EXECUTED",
    }
    with pytest.raises(ContractAuthorityError, match="révision juridique"):
        _sign(service, company, owner, "MUTUAL_NDA")
