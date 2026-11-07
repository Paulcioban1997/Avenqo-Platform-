"""HTTP regression coverage for the CEO Command Center's financial and audit APIs."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity
from backend.app.models import Base, Company, User
from backend.app.models.ai_usage import TenantAICreditLedgerEntry, TenantAIProviderAttempt
from backend.app.models.audit_log import AuditLogEntry
from backend.app.models.billing import BillingInvoice
from backend.app.models.base import CompanyStatus, UserRole
from backend.main import create_application


@pytest.fixture
def environment(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ceo-hotfix.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    company = Company(
        name="Synthetic CEO QA", slug=f"ceo-{uuid4().hex[:8]}", email="ceo@example.test",
        country="CA", timezone="America/Toronto", industry="Retail", subscription_plan="base",
        status=CompanyStatus.ACTIVE,
    )
    session.add(company)
    session.flush()
    user = User(
        company_id=company.id, first_name="Synthetic", last_name="Admin", email="ceo-user@example.test",
        password_hash="synthetic-test-hash", role=UserRole.OWNER, is_active=True,
        is_platform_admin=True, platform_role="PLATFORM_SUPER_ADMIN",
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.commit()
    app = create_application()
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_current_identity] = lambda: CurrentIdentity(
        auth_session=None, user=user, raw_token="synthetic-test-token"
    )
    try:
        yield TestClient(app), session, company, user
    finally:
        app.dependency_overrides.clear()
        session.close()
        engine.dispose()


def test_revenue_http_orders_real_invoice_fields_and_rejects_tenant_user(environment):
    client, db, company, user = environment
    now = datetime.now(timezone.utc)
    for offset, total in ((2, 2100), (1, 4200)):
        db.add(BillingInvoice(
            company_id=company.id, stripe_invoice_id=f"in_synthetic_{offset}",
            status="paid", currency="cad", subtotal=total, total=total,
            amount_due=total, amount_paid=total, issued_at=now - timedelta(days=offset),
        ))
    db.commit()
    response = client.get("/api/v1/ceo/revenue")
    assert response.status_code == 200
    invoices = response.json()["recent_invoices"]
    assert [row["amount"] for row in invoices] == [42.0, 21.0]
    assert [row["currency"] for row in invoices] == ["CAD", "CAD"]
    assert all(row["created_at"] for row in invoices)

    user.is_platform_admin = False
    db.commit()
    assert client.get("/api/v1/ceo/revenue").status_code == 403


def test_security_audit_http_empty_populated_redacted_and_authorized(environment):
    client, db, company, user = environment
    empty = client.get("/api/v1/ceo/security-audit")
    assert empty.status_code == 200 and empty.json() == {"events_count": 0, "events": []}

    db.add(AuditLogEntry(
        actor_user_id=user.id, company_id=company.id, action="security.synthetic",
        target_type="company", target_id=str(company.id),
        safe_metadata={"event": "synthetic", "api_key": "must-not-leak", "nested": {"password": "must-not-leak"}},
    ))
    db.commit()
    response = client.get("/api/v1/ceo/security-audit")
    assert response.status_code == 200
    assert response.json()["events_count"] == 1
    metadata = response.json()["events"][0]["metadata"]
    assert metadata == {"event": "synthetic", "api_key": "[REDACTED]", "nested": {"password": "[REDACTED]"}}
    assert "must-not-leak" not in response.text

    user.platform_role = "PLATFORM_FINANCE"
    db.commit()
    assert client.get("/api/v1/ceo/security-audit").status_code == 403


def _provider_attempt(company_id, request_id: str, cost: str, created_at: datetime):
    return TenantAIProviderAttempt(
        company_id=company_id, avenqo_request_id=request_id, operation="generate",
        attempt_number=1, provider="openai", model="synthetic-model", success=True,
        latency_ms=10, provider_cost_usd=Decimal(cost), input_cost_per_million_usd=Decimal("0"),
        cached_input_cost_per_million_usd=Decimal("0"), output_cost_per_million_usd=Decimal("0"),
        tool_call_cost_usd=Decimal("0"), created_at=created_at,
    )


def test_ai_usage_http_reads_ledger_and_provider_cost_with_date_filter(environment):
    client, db, company, user = environment
    now = datetime.now(timezone.utc)
    for suffix, age, credits, cost in (("new", 2, 7, "0.0123"), ("older", 10, 4, "0.0021")):
        recorded_at = now - timedelta(days=age)
        db.add(TenantAICreditLedgerEntry(
            company_id=company.id, idempotency_key=f"synthetic-{suffix}",
            transaction_type="ai_settlement", billing_period=recorded_at.strftime("%Y-%m"),
            included_delta=-credits, purchased_delta=0, monthly_used_after=credits,
            purchased_balance_after=0, included_reserved_after=0, purchased_reserved_after=0,
            created_at=recorded_at,
        ))
        db.add(_provider_attempt(company.id, f"synthetic-{suffix}", cost, recorded_at))
    db.commit()

    recent = client.get("/api/v1/ceo/ai-usage?range=7d")
    broader = client.get("/api/v1/ceo/ai-usage?range=30d")
    assert recent.status_code == broader.status_code == 200
    assert recent.json()["credits_consumed_in_range"] == 7
    assert broader.json()["credits_consumed_in_range"] == 11
    assert recent.json()["recorded_provider_cost_usd"] == pytest.approx(0.0123)
    assert broader.json()["recorded_provider_cost_usd"] == pytest.approx(0.0144)
    assert broader.json()["model_tier_distribution"] is None
    assert broader.json()["provider_cost_cad"] is None
    assert broader.json()["anomalies_detected_count"] is None

    user.is_platform_admin = False
    db.commit()
    assert client.get("/api/v1/ceo/ai-usage").status_code == 403
