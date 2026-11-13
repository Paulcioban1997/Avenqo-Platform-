"""Sandbox account flows: mail is not claimed, and stored keys are not Connected."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.base import Base
from backend.app.models.company import Company
from backend.app.routers.commerce import platform_credentials
from backend.app.services.account_notifications import LoggingAccountNotifier, mailbox_delivery, missing_mailbox_settings
from backend.app.services.commerce_connection_service import CommerceConnectionService
from backend.app.services.connector_secret_cipher import ConnectorSecretCipher
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
