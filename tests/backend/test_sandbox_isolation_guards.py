"""Automated tests for Sandbox isolation guards (Email and Shopify).

Validates:
1. Sandbox email blocking: Live Resend and SMTP fail closed in Sandbox environment.
2. Deterministic email capture: SandboxCaptureAccountNotifier captures outbound notifications
   and extracts 8-digit OTP signing challenge codes without leaking them to public HTTP responses.
3. Shopify isolation guard: Outbound API execution, OAuth authorization, and scheduled
   commerce sync are strictly blocked by default in isolated Sandbox mode.
4. Fail-closed behavior: Fallback to live credentials is prevented.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from backend.app.config.settings import Settings
from backend.app.connectors.shopify import (
    ShopifyAuthenticationError,
    ShopifyConnector,
)
from backend.app.services.account_notifications import (
    ResendHTTPSEmailTransport,
    SMTPEmailTransport,
    SandboxCaptureAccountNotifier,
    get_sandbox_capture_notifier,
)
from backend.app.services.commerce_sync_runner import CommerceSyncRunner
from backend.app.services.commerce_sync_service import (
    CommerceSyncError,
    CommerceSyncService,
)
from shared.ai_engine.contracts import TenantContext

SAFE_JWT = "test-jwt-secret-at-least-32-characters-long-safe"


def test_sandbox_email_blocking_resend_fails_closed():
    """Verify live Resend email dispatch raises an explicit error in Sandbox mode."""
    settings = Settings(
        ENVIRONMENT="sandbox",
        AUTH_JWT_SECRET=SAFE_JWT,
        EMAIL_PROVIDER="https_api",
        EMAIL_API_KEY="re_dummy_sandbox_key",
        EMAIL_FROM_EMAIL="noreply@avenqo.ca",
        SANDBOX_ALLOW_EXTERNAL_EMAIL=False,
    )
    transport = ResendHTTPSEmailTransport(settings)
    with pytest.raises(RuntimeError, match="External email dispatch blocked: live Resend transmission is prohibited"):
        transport.send(
            recipient="test@example.com",
            subject="Test Subject",
            text_body="Test message body",
            html_body="<p>Test message body</p>",
        )


def test_sandbox_email_blocking_smtp_fails_closed():
    """Verify live SMTP email dispatch raises an explicit error in Sandbox mode."""
    settings = Settings(
        ENVIRONMENT="sandbox",
        AUTH_JWT_SECRET=SAFE_JWT,
        EMAIL_PROVIDER="smtp",
        SMTP_HOST="smtp.example.com",
        SMTP_USERNAME="user",
        SMTP_PASSWORD="password",
        SMTP_FROM_EMAIL="noreply@avenqo.ca",
        SANDBOX_ALLOW_EXTERNAL_EMAIL=False,
    )
    transport = SMTPEmailTransport(settings)
    with pytest.raises(RuntimeError, match="External email dispatch blocked: live SMTP transmission is prohibited"):
        transport.send(
            recipient="test@example.com",
            subject="Test Subject",
            text_body="Test message body",
            html_body="<p>Test message body</p>",
        )


def test_sandbox_capture_notifier_records_and_extracts_challenge_otp():
    """Verify SandboxCaptureAccountNotifier captures email and extracts 8-digit OTP."""
    notifier = SandboxCaptureAccountNotifier()
    notifier.clear()
    
    assert notifier.email_delivery_configured is True
    
    # 1. Send transactional challenge email with 8-digit OTP
    recipient = "founder-test@pmc-solutions.ai"
    otp_code = "84729103"
    body = f"Votre code de confirmation de signature est {otp_code}. Il expire dans 15 minutes."
    
    notifier.send_transactional(recipient, "Code de signature Avenqo", body)
    
    # 2. Check capture
    captured = notifier.get_captured_emails(recipient)
    assert len(captured) == 1
    assert captured[0].recipient == recipient
    assert captured[0].subject == "Code de signature Avenqo"
    assert captured[0].verification_code == otp_code
    
    # 3. Retrieve latest code helper
    extracted = notifier.get_latest_code_for(recipient)
    assert extracted == otp_code
    
    # 4. Clear capture
    notifier.clear()
    assert len(notifier.get_captured_emails()) == 0


def test_auth_dependency_routes_to_sandbox_capture_in_sandbox():
    """Verify get_account_notifier() automatically resolves to Sandbox capture in Sandbox environment."""
    from backend.app.config.settings import get_settings
    from backend.app.dependencies.auth import get_account_notifier
    
    # Simulate Sandbox settings
    settings = get_settings()
    orig_env = settings.environment
    orig_ext = settings.sandbox_allow_external_email
    try:
        settings.environment = "sandbox"
        settings.sandbox_allow_external_email = False
        settings.sandbox_email_capture_enabled = True
        
        notifier = get_account_notifier()
        assert isinstance(notifier, SandboxCaptureAccountNotifier)
        assert notifier.email_delivery_configured is True
    finally:
        settings.environment = orig_env
        settings.sandbox_allow_external_email = orig_ext


def test_shopify_connector_isolation_blocks_network_in_sandbox():
    """Verify ShopifyConnector blocks network API calls when guard is active."""
    connector = ShopifyConnector(
        client_id="dummy_client_id",
        client_secret="dummy_client_secret",
        redirect_uri="https://api.avenqo.ca/callback",
        api_version="2026-07",
        scopes=["read_orders"],
        webhook_uri="https://api.avenqo.ca/webhook",
        blocked_by_sandbox_guard=True,
    )
    
    # 1. OAuth authenticate must be rejected
    with pytest.raises(ShopifyAuthenticationError, match="Shopify OAuth authorization is blocked by Sandbox isolation guard"):
        connector.authenticate(tenant_id=uuid4(), configuration={})
        
    # 2. Internal request must be rejected
    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(ShopifyAuthenticationError, match="Shopify API network execution is blocked by Sandbox isolation guard"):
            loop.run_until_complete(connector._request("GET", "https://avenqo-retail-test.myshopify.com/api/test"))
    finally:
        loop.close()


def test_commerce_reconciliation_cron_skips_when_isolated(monkeypatch):
    """Verify CommerceSyncRunner.reconcile_active skips cleanly without claiming connections."""
    fake_settings = Settings(
        ENVIRONMENT="sandbox",
        AUTH_JWT_SECRET=SAFE_JWT,
        SANDBOX_COMMERCE_SYNC_ENABLED=False,
    )
    monkeypatch.setattr("backend.app.config.settings.get_settings", lambda: fake_settings)
    
    runner = CommerceSyncRunner(
        session_factory=MagicMock(),
        service_factory=MagicMock(),
    )
    
    loop = asyncio.new_event_loop()
    try:
        claimed = loop.run_until_complete(runner.reconcile_active())
        assert claimed == 0
    finally:
        loop.close()


def test_commerce_sync_service_raises_when_isolated(monkeypatch):
    """Verify CommerceSyncService.synchronize rejects execution when isolated."""
    fake_settings = Settings(
        ENVIRONMENT="sandbox",
        AUTH_JWT_SECRET=SAFE_JWT,
        SANDBOX_COMMERCE_SYNC_ENABLED=False,
    )
    monkeypatch.setattr("backend.app.config.settings.get_settings", lambda: fake_settings)
    
    service = CommerceSyncService(
        db=MagicMock(),
        registry=MagicMock(),
        connections=MagicMock(),
        ingestion=MagicMock(),
    )
    
    tenant = TenantContext(company_id=uuid4())
    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(CommerceSyncError, match="Commerce synchronization disabled in isolated Sandbox mode"):
            loop.run_until_complete(service.synchronize(tenant, uuid4()))
    finally:
        loop.close()


def test_production_strictly_prohibits_sandbox_email_capture():
    """Verify that attempting to configure sandbox_capture in Production raises validation error."""
    with pytest.raises(ValueError, match="strictly prohibited in production"):
        Settings(
            ENVIRONMENT="production",
            AUTH_JWT_SECRET=SAFE_JWT,
            DATABASE_URL="postgresql://user:test-only-password@prod.db:5432/db",
            STRIPE_SECRET_KEY="sk_live_dummy",
            STRIPE_WEBHOOK_SECRET="whsec_dummy",
            STRIPE_PRICE_DEMO="price_1",
            STRIPE_PRICE_PROFESSIONAL="price_2",
            FRONTEND_URL="https://avenqo.ca",
            CORS_ORIGINS=["https://avenqo.ca"],
            ALLOWED_HOSTS=["api.avenqo.ca"],
            EMAIL_PROVIDER="sandbox_capture",
        )


def test_production_auth_dependency_raises_runtime_error_if_capture_configured():
    """Verify get_account_notifier() raises a critical error if capture is somehow set in production."""
    from backend.app.config.settings import get_settings
    from backend.app.dependencies.auth import get_account_notifier
    
    settings = get_settings()
    orig_env = settings.environment
    orig_prov = settings.email_provider
    try:
        settings.environment = "production"
        settings.email_provider = "sandbox_capture"
        with pytest.raises(RuntimeError, match="CRITICAL SECURITY ERROR: Sandbox email capture is strictly prohibited in Production"):
            get_account_notifier()
    finally:
        settings.environment = orig_env
        settings.email_provider = orig_prov


def test_sandbox_capture_tenant_scoping():
    """Verify multi-tenant isolation and zero leakage in captured emails."""
    notifier = SandboxCaptureAccountNotifier()
    notifier.clear()
    
    tenant_a = str(uuid4())
    tenant_b = str(uuid4())
    
    notifier._record("user_a@tenant-a.com", "Challenge A", "code 11112222", "", company_id=tenant_a)
    notifier._record("user_b@tenant-b.com", "Challenge B", "code 33334444", "", company_id=tenant_b)
    
    # Assert tenant A scoping
    emails_a = notifier.get_captured_emails(company_id=tenant_a)
    assert len(emails_a) == 1
    assert emails_a[0].verification_code == "11112222"
    assert notifier.get_latest_code_for("user_a@tenant-a.com", company_id=tenant_a) == "11112222"
    assert notifier.get_latest_code_for("user_a@tenant-a.com", company_id=tenant_b) is None
    
    # Assert tenant B scoping
    emails_b = notifier.get_captured_emails(company_id=tenant_b)
    assert len(emails_b) == 1
    assert emails_b[0].verification_code == "33334444"
    assert notifier.get_latest_code_for("user_b@tenant-b.com", company_id=tenant_b) == "33334444"


def test_async_background_task_run_reserved_blocked_in_sandbox(monkeypatch):
    """Verify CommerceSyncRunner.run_reserved immediately rejects async background execution."""
    fake_settings = Settings(
        ENVIRONMENT="sandbox",
        AUTH_JWT_SECRET=SAFE_JWT,
        SANDBOX_COMMERCE_SYNC_ENABLED=False,
    )
    monkeypatch.setattr("backend.app.config.settings.get_settings", lambda: fake_settings)
    
    mock_service_factory = MagicMock()
    runner = CommerceSyncRunner(
        session_factory=MagicMock(),
        service_factory=mock_service_factory,
    )
    
    tenant = TenantContext(company_id=uuid4())
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(runner.run_reserved(tenant, uuid4()))
        # Ensure service factory and synchronize were NEVER invoked
        mock_service_factory.assert_not_called()
    finally:
        loop.close()
