"""NDA stays under legal review until an authorized platform reviewer approves the version."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.dependencies.auth import CurrentIdentity, require_platform_role
from backend.app.models.audit_log import AuditLogEntry
from backend.app.models.base import Base, CompanyStatus, UserRole
from backend.app.models.company import Company
from backend.app.models.user import User
from backend.app.routers.contracts import (
    create_signing_challenge,
    list_company_contracts,
)
from backend.app.services.commercial_reconciler import CommercialReconciler
from backend.app.services.contract_signature_service import (
    APPROVED_FOR_CUSTOMER_SIGNING,
    ContractAuthorityError,
    ContractSignatureService,
)
from backend.app.services.signing_challenge_service import SigningChallengeService
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'nda_legal.db'}")
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
        "sandbox_allow_external_email": True,
        "sandbox_approved_email_recipients": "owner@example.test",
    })


def _company(session) -> Company:
    company = Company(
        name="NDA Tenant",
        slug=f"nda-{uuid4().hex[:8]}",
        email=f"co-{uuid4().hex[:6]}@example.com",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="base",
        status=CompanyStatus.ACTIVE,
        currency_code="CAD",
    )
    session.add(company)
    session.commit()
    return company


def _user(session, company, *, role=UserRole.OWNER, email=None, is_platform_admin=False, platform_role=None) -> User:
    user = User(
        company_id=company.id,
        first_name="Ada",
        last_name="Martin",
        email=email or f"{role.value}-{uuid4().hex[:6]}@example.test",
        password_hash="hashed",
        role=role,
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
        is_platform_admin=is_platform_admin,
        platform_role=platform_role,
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


def test_nda_defaults_to_legal_review_and_is_not_signable(db_session, tmp_path):
    company = _company(db_session)
    owner = _user(db_session, company, email="owner@example.test")
    service = ContractSignatureService(db_session, settings=_settings(tmp_path))
    service.ensure_contracts_for_company(company)

    nda = service.get_contract(company.id, "MUTUAL_NDA")
    saas = service.get_contract(company.id, "SAAS_SUBSCRIPTION")
    dpa = service.get_contract(company.id, "DATA_PROCESSING_ADDENDUM")

    assert service.approval_status_of(nda) == "LEGAL_REVIEW_REQUIRED"
    assert service.signature_blocked(nda) is True
    assert service.signature_blocked(saas) is False
    assert service.signature_blocked(dpa) is False

    with pytest.raises(ContractAuthorityError, match="révision juridique"):
        _sign(service, company, owner, "MUTUAL_NDA")

    items = list_company_contracts(
        TenantContext(company_id=company.id),
        db_session,
        service,
    )
    by_type = {row.contract_type: row for row in items}
    assert by_type["MUTUAL_NDA"].signable is False
    assert by_type["MUTUAL_NDA"].approval_status == "LEGAL_REVIEW_REQUIRED"
    assert by_type["SAAS_SUBSCRIPTION"].signable is True
    assert by_type["DATA_PROCESSING_ADDENDUM"].signable is True


def test_legal_reviewer_can_approve_nda_then_customer_may_sign(db_session, tmp_path):
    company = _company(db_session)
    owner = _user(db_session, company, email="owner@example.test")
    reviewer = _user(
        db_session,
        company,
        role=UserRole.ADMIN,
        email="legal@example.test",
        is_platform_admin=True,
        platform_role="PLATFORM_LEGAL_REVIEWER",
    )
    service = ContractSignatureService(db_session, settings=_settings(tmp_path))
    service.ensure_contracts_for_company(company)

    updated = service.approve_contract_version_for_signing(
        company_id=company.id,
        contract_type="MUTUAL_NDA",
        reviewer=reviewer,
        notes="Sandbox version review",
    )
    assert service.approval_status_of(updated) == APPROVED_FOR_CUSTOMER_SIGNING
    assert service.signature_blocked(updated) is False
    meta = updated.metadata_json
    assert meta["legal_approved_by_email"] == reviewer.email
    assert meta["legal_approved_version"] == updated.version
    assert meta["legal_approved_content_hash"] == service.compute_sha256(updated.content_text)
    assert meta["provider_countersigned"] is False

    audit = db_session.scalars(
        select(AuditLogEntry).where(AuditLogEntry.action == "contract.legal_version_approved")
    ).first()
    assert audit is not None
    assert audit.company_id == company.id
    assert audit.actor_user_id == reviewer.id

    receipt = _sign(service, company, owner, "MUTUAL_NDA")
    assert receipt["status"] == "CUSTOMER_SIGNED"
    assert receipt["signature_mode"] == "SANDBOX_PILOT"
    assert receipt["signature_label"] == "pilot/test"
    signed = service.get_contract(company.id, "MUTUAL_NDA")
    assert signed.completion_record_json["legal_approved_by_email"] == reviewer.email
    assert signed.completion_record_json["consent_recorded"] is True
    assert signed.completion_record_json["provider_countersigned"] is False


def test_tenant_owner_and_finance_role_cannot_approve_nda(db_session, tmp_path):
    company = _company(db_session)
    owner = _user(db_session, company, email="owner@example.test")
    finance = _user(
        db_session,
        company,
        role=UserRole.ADMIN,
        email="finance@example.test",
        is_platform_admin=True,
        platform_role="PLATFORM_FINANCE",
    )
    support = _user(
        db_session,
        company,
        role=UserRole.ADMIN,
        email="support@example.test",
        is_platform_admin=True,
        platform_role="PLATFORM_SUPPORT_READONLY",
    )
    service = ContractSignatureService(db_session, settings=_settings(tmp_path))
    service.ensure_contracts_for_company(company)

    with pytest.raises(ContractAuthorityError, match="réviseur légal"):
        service.approve_contract_version_for_signing(
            company_id=company.id,
            contract_type="MUTUAL_NDA",
            reviewer=owner,
        )

    dep = require_platform_role("PLATFORM_SUPER_ADMIN", "PLATFORM_LEGAL_REVIEWER")
    for identity in (
        CurrentIdentity(None, owner, "token"),
        CurrentIdentity(None, finance, "token"),
        CurrentIdentity(None, support, "token"),
    ):
        with pytest.raises(HTTPException) as denied:
            dep(identity)
        assert denied.value.status_code == 403

    legal = _user(
        db_session,
        company,
        role=UserRole.ADMIN,
        email="legal-ok@example.test",
        is_platform_admin=True,
        platform_role="PLATFORM_LEGAL_REVIEWER",
    )
    assert dep(CurrentIdentity(None, legal, "token")).user.id == legal.id


def test_legal_approval_is_tenant_scoped(db_session, tmp_path):
    company_a = _company(db_session)
    company_b = _company(db_session)
    reviewer = _user(
        db_session,
        company_a,
        role=UserRole.ADMIN,
        email="legal@example.test",
        is_platform_admin=True,
        platform_role="PLATFORM_SUPER_ADMIN",
    )
    service = ContractSignatureService(db_session, settings=_settings(tmp_path))
    service.ensure_contracts_for_company(company_a)
    service.ensure_contracts_for_company(company_b)

    service.approve_contract_version_for_signing(
        company_id=company_a.id,
        contract_type="MUTUAL_NDA",
        reviewer=reviewer,
    )
    assert service.signature_blocked(service.get_contract(company_a.id, "MUTUAL_NDA")) is False
    assert service.signature_blocked(service.get_contract(company_b.id, "MUTUAL_NDA")) is True
    assert service.approval_status_of(service.get_contract(company_b.id, "MUTUAL_NDA")) == "LEGAL_REVIEW_REQUIRED"


def test_msa_dpa_otp_challenge_blocked_while_nda_under_review(db_session, tmp_path):
    company = _company(db_session)
    owner = _user(db_session, company, email="owner@example.test")
    settings = _settings(tmp_path)
    service = ContractSignatureService(db_session, settings=settings)

    class FakeNotifier:
        email_delivery_configured = True
        delivers_to_mailbox = True
        deliveries: list[tuple[str, str, str]] = []

        def send_transactional(self, recipient: str, subject: str, body: str) -> None:
            self.deliveries.append((recipient, subject, body))

    notifier = FakeNotifier()
    service.ensure_contracts_for_company(company)

    # NDA OTP must fail while under legal review.
    with pytest.raises(HTTPException) as nda_challenge:
        create_signing_challenge(
            contract_type="MUTUAL_NDA",
            tenant=TenantContext(company_id=company.id),
            identity=CurrentIdentity(None, owner, "token"),
            db=db_session,
            notifier=notifier,
            service=service,
        )
    assert nda_challenge.value.status_code == 403

    # MSA remains available for the existing OTP path.
    result = create_signing_challenge(
        contract_type="SAAS_SUBSCRIPTION",
        tenant=TenantContext(company_id=company.id),
        identity=CurrentIdentity(None, owner, "token"),
        db=db_session,
        notifier=notifier,
        service=service,
    )
    assert "challenge_id" in result
    assert "code" not in result
    assert result["recipient_masked"]
    assert len(notifier.deliveries) == 1
    assert notifier.deliveries[0][0] == owner.email

    _sign(service, company, owner, "SAAS_SUBSCRIPTION")
    _sign(service, company, owner, "DATA_PROCESSING_ADDENDUM")
    assert service.required_saas_accepted(company.id) is True
    signed_saas = service.get_contract(company.id, "SAAS_SUBSCRIPTION")
    assert signed_saas.completion_record_json["legal_effect"] == "sandbox_pilot"
    assert signed_saas.completion_record_json["provider_countersigned"] is False
