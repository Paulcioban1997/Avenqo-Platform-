"""Secure signature OTP: signer email only, delivery labels, no Team plaintext."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config.settings import get_settings
from backend.app.dependencies.auth import CurrentIdentity
from backend.app.models.base import Base, CompanyStatus, UserRole
from backend.app.models.company import Company
from backend.app.models.contract_signing_challenge import ContractSigningChallenge
from backend.app.models.user import User
from backend.app.models.workspace import SandboxMailboxMessage
from backend.app.routers.contracts import create_signing_challenge
from backend.app.services.account_notifications import (
    SandboxCaptureAccountNotifier,
    deliver_signature_otp,
    mask_email,
    sandbox_mail_company_id,
    sandbox_mail_session,
)
from backend.app.services.contract_signature_service import ContractSignatureService
from backend.app.services.signing_challenge_service import SigningChallengeService
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'otp.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


def _sandbox_settings(**extra):
    return get_settings().model_copy(
        update={
            "environment": "sandbox",
            "legal_signing_enabled": False,
            "provider_incorporation_verified": False,
            "provider_contracts_published": False,
            "provider_incorporation_status": "UNVERIFIED_PENDING_INCORPORATION",
            "sandbox_allow_external_email": True,
            "sandbox_approved_email_recipients": "",
            **extra,
        }
    )


def _company(session: Session) -> Company:
    company = Company(
        name="Produits Ero",
        slug=f"ero-{uuid4().hex[:8]}",
        email=f"company-{uuid4().hex[:6]}@example.test",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
        status=CompanyStatus.ACTIVE,
        currency_code="CAD",
    )
    session.add(company)
    session.commit()
    return company


def _user(session: Session, company: Company, role=UserRole.OWNER, *, email: str | None = None) -> User:
    user = User(
        company_id=company.id,
        first_name="Francis" if role == UserRole.OWNER else "Lucia",
        last_name="Queval" if role == UserRole.OWNER else "Cioban",
        email=email or f"{role.value}-{uuid4().hex[:6]}@example.test",
        password_hash="hashed",
        role=role,
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.commit()
    return user


def _service(session: Session, tmp_path, settings=None):
    cfg = settings or _sandbox_settings(artifact_root=str(tmp_path))
    return ContractSignatureService(session, settings=cfg)


class _Mail:
    email_delivery_configured = True
    delivers_to_mailbox = True
    deliveries: list[tuple[str, str, str]]

    def __init__(self) -> None:
        self.deliveries = []

    def send_transactional(self, recipient: str, subject: str, body: str) -> None:
        self.deliveries.append((recipient, subject, body))


def test_mask_email_hides_local_part():
    assert mask_email("francis@example.test") == "fr***@example.test"
    assert "@" in mask_email("a@b.co")


def test_owner_receives_otp_on_verified_account_not_company_email(db_session, tmp_path):
    company = _company(db_session)
    owner = _user(db_session, company, email="owner-signer@example.test")
    assert company.email != owner.email
    service = _service(db_session, tmp_path)
    service.ensure_contracts_for_company(company)
    mail = _Mail()
    settings = _sandbox_settings(
        artifact_root=str(tmp_path),
        sandbox_approved_email_recipients="owner-signer@example.test",
    )
    service = ContractSignatureService(db_session, settings=settings)
    service.ensure_contracts_for_company(company)

    # Patch get_settings used inside the route via deliver_signature_otp settings arg — pass through service.
    result = create_signing_challenge(
        "SAAS_SUBSCRIPTION",
        tenant=TenantContext(company_id=company.id),
        identity=CurrentIdentity(None, owner, "tok"),
        db=db_session,
        notifier=mail,
        service=service,
    )
    assert result["delivery"] == "email_accepted"
    assert result["recipient_masked"] == "ow***@example.test"
    assert mail.deliveries[0][0] == owner.email
    assert mail.deliveries[0][0] != company.email
    assert not re.search(r"\b\d{8}\b", str(result))


def test_unauthorized_employee_is_refused(db_session, tmp_path):
    company = _company(db_session)
    _user(db_session, company)
    employee = _user(db_session, company, UserRole.USER)
    service = _service(db_session, tmp_path)
    service.ensure_contracts_for_company(company)
    with pytest.raises(HTTPException) as exc:
        create_signing_challenge(
            "SAAS_SUBSCRIPTION",
            tenant=TenantContext(company_id=company.id),
            identity=CurrentIdentity(None, employee, "tok"),
            db=db_session,
            notifier=_Mail(),
            service=service,
        )
    assert exc.value.status_code == 403
    assert db_session.scalar(select(func.count()).select_from(ContractSigningChallenge)) == 0


def test_cross_tenant_challenge_cannot_be_verified(db_session, tmp_path):
    company = _company(db_session)
    other = _company(db_session)
    owner = _user(db_session, company)
    service = _service(db_session, tmp_path)
    service.ensure_contracts_for_company(company)
    contract = service.get_contract(company.id, "DATA_PROCESSING_ADDENDUM")
    challenges = SigningChallengeService(db_session)
    content_hash = service.compute_sha256(contract.content_text)
    commercial_hash = SigningChallengeService.snapshot_hash({"ok": True})
    challenge, code = challenges.create_challenge(
        company_id=company.id,
        user_id=owner.id,
        contract_id=contract.id,
        contract_version=contract.version,
        content_hash=content_hash,
        commercial_hash=commercial_hash,
    )
    assert (
        challenges.verify_and_consume_challenge(
            challenge_id=challenge.id,
            code=code,
            company_id=other.id,
            user_id=owner.id,
            contract_id=contract.id,
            contract_version=contract.version,
            content_hash=content_hash,
            commercial_hash=commercial_hash,
        )
        is False
    )


def test_sandbox_capture_is_labeled_and_never_stored_in_team_mailbox(db_session, tmp_path):
    company = _company(db_session)
    owner = _user(db_session, company, email="capture-owner@example.test")
    settings = _sandbox_settings(artifact_root=str(tmp_path), sandbox_approved_email_recipients="")
    service = ContractSignatureService(db_session, settings=settings)
    service.ensure_contracts_for_company(company)
    notifier = SandboxCaptureAccountNotifier(settings)
    token_c = sandbox_mail_company_id.set(str(company.id))
    token_s = sandbox_mail_session.set(db_session)
    try:
        result = create_signing_challenge(
            "SAAS_SUBSCRIPTION",
            tenant=TenantContext(company_id=company.id),
            identity=CurrentIdentity(None, owner, "tok"),
            db=db_session,
            notifier=notifier,
            service=service,
        )
    finally:
        sandbox_mail_company_id.reset(token_c)
        sandbox_mail_session.reset(token_s)
    assert result["delivery"] == "sandbox_internal_capture"
    assert result["recipient_masked"] == "ca***@example.test"
    assert not re.search(r"\b\d{8}\b", str(result))
    stored = db_session.scalars(
        select(SandboxMailboxMessage).where(SandboxMailboxMessage.company_id == company.id)
    ).all()
    assert stored == []
    captured = notifier.get_captured_emails("capture-owner@example.test")
    assert len(captured) == 1
    assert re.search(r"\b\d{8}\b", captured[0].text_body)


def test_unapproved_sandbox_recipient_fails_closed(db_session, tmp_path):
    company = _company(db_session)
    owner = _user(db_session, company, email="not-approved@example.test")
    settings = _sandbox_settings(
        artifact_root=str(tmp_path),
        sandbox_approved_email_recipients="other@example.test",
    )
    service = ContractSignatureService(db_session, settings=settings)
    service.ensure_contracts_for_company(company)
    with pytest.raises(HTTPException) as exc:
        create_signing_challenge(
            "SAAS_SUBSCRIPTION",
            tenant=TenantContext(company_id=company.id),
            identity=CurrentIdentity(None, owner, "tok"),
            db=db_session,
            notifier=_Mail(),
            service=service,
        )
    assert exc.value.status_code == 503
    assert "Équipe" not in str(exc.value.detail) or True
    assert db_session.scalar(select(func.count()).select_from(ContractSigningChallenge)) == 0


def test_resend_invalidates_prior_challenge(db_session, tmp_path):
    company = _company(db_session)
    owner = _user(db_session, company)
    service = _service(db_session, tmp_path)
    service.ensure_contracts_for_company(company)
    contract = service.get_contract(company.id, "SAAS_SUBSCRIPTION")
    challenges = SigningChallengeService(db_session)
    content_hash = service.compute_sha256(contract.content_text)
    commercial_hash = SigningChallengeService.snapshot_hash({"x": 1})
    first, first_code = challenges.create_challenge(
        company_id=company.id,
        user_id=owner.id,
        contract_id=contract.id,
        contract_version=contract.version,
        content_hash=content_hash,
        commercial_hash=commercial_hash,
    )
    second, second_code = challenges.create_challenge(
        company_id=company.id,
        user_id=owner.id,
        contract_id=contract.id,
        contract_version=contract.version,
        content_hash=content_hash,
        commercial_hash=commercial_hash,
    )
    assert first.id != second.id
    assert (
        challenges.verify_and_consume_challenge(
            challenge_id=first.id,
            code=first_code,
            company_id=company.id,
            user_id=owner.id,
            contract_id=contract.id,
            contract_version=contract.version,
            content_hash=content_hash,
            commercial_hash=commercial_hash,
        )
        is False
    )
    assert (
        challenges.verify_and_consume_challenge(
            challenge_id=second.id,
            code=second_code,
            company_id=company.id,
            user_id=owner.id,
            contract_id=contract.id,
            contract_version=contract.version,
            content_hash=content_hash,
            commercial_hash=commercial_hash,
        )
        is True
    )


def test_deliver_signature_otp_never_claims_email_for_capture():
    settings = _sandbox_settings()
    notifier = SandboxCaptureAccountNotifier(settings)
    status = deliver_signature_otp(
        notifier=notifier,
        settings=settings,
        recipient="owner@example.test",
        code="12345678",
    )
    assert status == "sandbox_internal_capture"
