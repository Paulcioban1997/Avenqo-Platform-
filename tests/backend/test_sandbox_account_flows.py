"""Sandbox account flows: mail is not claimed, and stored keys are not Connected."""

from __future__ import annotations

import re
from types import SimpleNamespace
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.base import Base
from backend.app.models.company import Company
from backend.app.models.contract_signing_challenge import ContractSigningChallenge
from backend.app.models.user import User, UserRole
from backend.app.models.workspace import EmployeeInvitation, SandboxMailboxMessage
from backend.app.routers.commerce import platform_credentials
from backend.app.routers.contracts import create_signing_challenge
from backend.app.services.account_notifications import (
    LoggingAccountNotifier,
    SandboxCaptureAccountNotifier,
    mailbox_delivery,
    missing_mailbox_settings,
)
from backend.app.services.commerce_connection_service import CommerceConnectionService
from backend.app.services.connector_secret_cipher import ConnectorSecretCipher
from backend.app.services.onboarding_service import OnboardingService
from backend.app.services.workspace_service import MailNotConfigured, WorkspaceService
from shared.ai_engine.contracts import TenantContext


def _sandbox_settings() -> SimpleNamespace:
    return SimpleNamespace(
        environment="sandbox",
        sandbox_allow_external_email=False,
        is_external_email_allowed=False,
        email_provider="smtp",
        email_api_key=None,
        email_from_email="",
        smtp_host=None,
        smtp_username=None,
        smtp_password=None,
        smtp_from_email="",
    )


def test_sandbox_mail_reports_missing_settings_without_values():
    missing = missing_mailbox_settings(_sandbox_settings())
    assert missing == [
        "SANDBOX_ALLOW_EXTERNAL_EMAIL",
        "SMTP_HOST",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM_EMAIL",
    ]
    ready, reported = mailbox_delivery(LoggingAccountNotifier(), _sandbox_settings())
    assert ready is False
    assert reported == missing


def test_platform_credential_report_lists_names_only(monkeypatch):
    monkeypatch.delenv("BIGCOMMERCE_CLIENT_ID", raising=False)
    monkeypatch.delenv("BIGCOMMERCE_CLIENT_SECRET", raising=False)
    report = platform_credentials(object())
    assert "BIGCOMMERCE_CLIENT_ID" in report["bigcommerce"]["missing"]
    assert report["bigcommerce"]["oauth_ready"] is False
    serialized = str(report)
    assert "SECRET_VALUE" not in serialized


def test_tenant_api_key_stays_unverified():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session: Session = sessionmaker(bind=engine)()
    company = Company(
        id=uuid4(),
        name="Produits Ero",
        slug="produits-ero",
        email="owner@example.test",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
        preferred_language="fr",
    )
    session.add(company)
    session.commit()
    cipher = ConnectorSecretCipher([Fernet.generate_key().decode()])
    service = CommerceConnectionService(session, object(), cipher)
    connection = service.store_unverified_api_credentials(
        TenantContext(company_id=company.id),
        provider="prestashop",
        account_id="sandbox-shop.example",
        api_key="tenant-key",
        api_secret=None,
    )
    assert connection.status == "CONNECTING"
    assert connection.company_id == company.id
    assert "tenant-key" not in (connection.encrypted_credentials or "")
    session.close()


def _company(session: Session, slug: str) -> tuple[Company, User]:
    company = Company(
        id=uuid4(),
        name=slug,
        slug=slug,
        email=f"{slug}@example.test",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
        preferred_language="fr",
    )
    owner = User(
        id=uuid4(),
        company_id=company.id,
        email=f"owner-{slug}@example.test",
        password_hash="not-a-secret",
        first_name="Ada",
        last_name="Owner",
        role=UserRole.OWNER,
        is_active=True,
    )
    session.add(company)
    session.add(owner)
    session.commit()
    return company, owner


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class _RaisingMail:
    email_delivery_configured = True
    delivers_to_mailbox = True
    test_transport = True

    def send_transactional(self, recipient: str, subject: str, body: str) -> None:
        raise RuntimeError("sandbox transport refused the message")


def test_failed_mail_does_not_keep_an_invitation_or_challenge():
    session = _session()
    company, owner = _company(session, "produits-ero-mail")
    service = WorkspaceService(session, LoggingAccountNotifier())
    with pytest.raises(MailNotConfigured) as blocked:
        service.invite(owner, "invitee@example.test", UserRole.USER, "Analyst", None)
    assert not re.search(r"\b\d{8}\b", str(blocked.value))
    assert session.scalar(select(func.count()).select_from(EmployeeInvitation)) == 0

    raising = WorkspaceService(session, _RaisingMail())
    with pytest.raises(MailNotConfigured):
        raising.invite(owner, "invitee@example.test", UserRole.USER, "Analyst", None)
    assert session.scalar(select(func.count()).select_from(EmployeeInvitation)) == 0

    with pytest.raises(HTTPException) as challenge_error:
        create_signing_challenge(
            "SAAS_SUBSCRIPTION",
            tenant=TenantContext(company_id=company.id),
            identity=SimpleNamespace(),
            db=session,
            notifier=LoggingAccountNotifier(),
            service=object(),
        )
    assert challenge_error.value.status_code == 503
    assert not re.search(r"\b\d{8}\b", str(challenge_error.value.detail))
    assert session.scalar(select(func.count()).select_from(ContractSigningChallenge)) == 0
    session.close()


def test_sandbox_mailbox_stores_the_code_for_one_company_only():
    session = _session()
    company, owner = _company(session, "mailbox-tenant")
    other, _other_owner = _company(session, "mailbox-other")
    notifier = SandboxCaptureAccountNotifier()
    ready, _missing = mailbox_delivery(notifier, _sandbox_settings())
    assert ready is True
    row = WorkspaceService(session, notifier).invite(
        owner, "invitee@example.test", UserRole.USER, "Analyst", None
    )
    public = {"id": str(row.id), "email": row.email, "delivery": "sandbox_mailbox"}
    stored = session.scalars(
        select(SandboxMailboxMessage).where(SandboxMailboxMessage.company_id == company.id)
    ).all()
    assert len(stored) == 1
    assert re.search(r"\b\d{8}\b", stored[0].body)
    assert not re.search(r"\b\d{8}\b", str(public))
    assert "invitation-token:" not in str(public)
    hidden = session.scalars(
        select(SandboxMailboxMessage).where(SandboxMailboxMessage.company_id == other.id)
    ).all()
    assert hidden == []
    session.close()


def test_theme_and_logo_persist_for_one_tenant_only():
    session = _session()
    company_a, _owner_a = _company(session, "tenant-a")
    company_b, _owner_b = _company(session, "tenant-b")
    service = OnboardingService(session)
    tenant_a = TenantContext(company_id=company_a.id)
    service.update_tenant_branding(
        tenant_a,
        {
            "theme_id": "emerald_enterprise",
            "primary_color": "#00AA88",
            "secondary_color": "#06281F",
            "accent_color": "#B6F2D8",
            "mode": "dark",
            "company_logo_url": "data:image/png;base64,AAAA",
            "logo_placement": "sidebar",
        },
    )
    reread = OnboardingService(session).get_tenant_branding(tenant_a)
    other = OnboardingService(session).get_tenant_branding(TenantContext(company_id=company_b.id))
    assert reread["theme_id"] == "emerald_enterprise"
    assert reread["logo_placement"] == "sidebar"
    assert reread["company_logo_url"] == "data:image/png;base64,AAAA"
    assert other["company_logo_url"] in ("", None)
    assert other["theme_id"] != "emerald_enterprise"
    session.close()
