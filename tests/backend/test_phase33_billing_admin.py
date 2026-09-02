"""Phase 33 — Billing lifecycle, Enterprise overrides & Avenqo Admin Command Center.

Couvre : accès `platform_admin` (jamais accordé automatiquement à un
`tenant_admin`), tableau de bord et répertoire d'entreprises cross-tenant,
dérogations Enterprise (quotas/capacités), journal d'audit, intégration des
dérogations dans `AIUsageService`/`resolve_tenant_capabilities`, et réponses
du Support AI aux questions de facturation (lecture seule, jamais de secrets).

Ne duplique pas les tests déjà couverts par `test_billing.py` (checkout,
webhook, idempotence, isolation des factures) : Phase 33 réutilise cette
architecture Stripe telle quelle.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.ai.tools.base import ToolArguments
from backend.app.ai.tools.support.support_tools import GetBillingStatusTool
from backend.app.ai.usage.policy import AIQuotaPolicy
from backend.app.ai.usage.service import AIUsageService
from backend.app.config.settings import Settings, get_settings
from backend.app.database import get_db
from backend.app.dependencies.auth import get_account_notifier
from backend.app.dependencies.tenant_business import get_tenant_sales_service
from backend.app.models import (
    Base,
    BillingAccount,
    BillingInvoice,
    Company,
    EnterpriseOverride,
    User,
    UserRole,
    TenantAICreditBalance,
)
from backend.app.services.audit_log_service import AuditLogService
from backend.main import create_application
from shared.ai_engine.contracts import TenantContext


class _NullNotifier:
    def send_email_verification(self, email: str, token: str) -> None:
        pass

    def send_password_reset(self, email: str, token: str) -> None:
        pass


def _settings() -> Settings:
    return Settings(AUTH_JWT_SECRET="a" * 32)


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'phase33.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


def _company(session, *, plan: str = "enterprise", slug: str = "acme") -> Company:
    company = Company(
        name="Acme", slug=slug, email=f"{slug}@example.com", country="CA",
        timezone="America/Toronto", industry="Retail", subscription_plan=plan,
    )
    session.add(company)
    session.flush()
    return company


def _user(session, company: Company, *, platform_admin: bool = False, role: UserRole = UserRole.OWNER) -> User:
    user = User(
        company_id=company.id, first_name="Ana", last_name="Lyst",
        email=f"user-{uuid4()}@example.com", password_hash="hash", role=role,
        is_platform_admin=platform_admin,
    )
    session.add(user)
    session.flush()
    return user


# ---------------------------------------------------------------------------
# 1. Enterprise overrides — quota + capability resolution
# ---------------------------------------------------------------------------


def test_enterprise_override_replaces_plan_quota_limit(db_session) -> None:
    company = _company(db_session, plan="enterprise")
    db_session.add(EnterpriseOverride(
        company_id=company.id,
        quota_overrides={"monthly_ai_requests": 42},
        capability_overrides={},
    ))
    db_session.commit()

    service = AIUsageService(db_session, AIQuotaPolicy(Settings(
        AUTH_JWT_SECRET="a" * 32,
        AI_QUOTA_LIMITS={"enterprise": {"monthly_ai_requests": 5000}},
    )))

    assert service.limit_for(company.id, "enterprise", "monthly_ai_requests") == 42


def test_no_override_falls_back_to_plan_policy(db_session) -> None:
    company = _company(db_session, plan="enterprise")
    service = AIUsageService(db_session, AIQuotaPolicy(Settings(
        AUTH_JWT_SECRET="a" * 32,
        AI_QUOTA_LIMITS={"enterprise": {"monthly_ai_requests": 5000}},
    )))

    assert service.limit_for(company.id, "enterprise", "monthly_ai_requests") == 5000


def test_enterprise_capability_override_forces_capability_on_and_off(db_session) -> None:
    from backend.app.ai.tools.business.registry_factory import resolve_tenant_capabilities

    company = _company(db_session, plan="enterprise")
    db_session.add(EnterpriseOverride(
        company_id=company.id,
        quota_overrides={},
        capability_overrides={"segmentation": True, "churn": False},
    ))
    db_session.commit()

    class _FakePredictionService:
        pass

    capabilities = resolve_tenant_capabilities(
        db_session, TenantContext(company_id=company.id), _FakePredictionService()
    )

    assert "segmentation" in capabilities
    assert "churn" not in capabilities


# ---------------------------------------------------------------------------
# 2. Audit log
# ---------------------------------------------------------------------------


def test_audit_log_records_actor_action_and_safe_metadata_only(db_session) -> None:
    company = _company(db_session)
    admin = _user(db_session, company, platform_admin=True)
    audit_log = AuditLogService(db_session)

    entry = audit_log.record(
        actor_user_id=admin.id,
        action="enterprise_override.set",
        target_type="company",
        target_id=str(company.id),
        company_id=company.id,
        metadata={"quota_metrics": ["monthly_ai_requests"]},
    )

    recent = audit_log.recent()
    assert entry.id in {item.id for item in recent}
    assert entry.actor_user_id == admin.id
    assert "sk-" not in str(entry.safe_metadata)


# ---------------------------------------------------------------------------
# 3. Support AI billing tool — read-only, never exposes secrets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_billing_status_tool_reports_own_plan_and_quota_state(db_session) -> None:
    company = _company(db_session, plan="demo")
    user = _user(db_session, company)
    db_session.add(BillingAccount(
        company_id=company.id, plan_code="demo", status="active", cancel_at_period_end=False,
    ))
    db_session.commit()

    usage_service = AIUsageService(db_session, AIQuotaPolicy(Settings(
        AUTH_JWT_SECRET="a" * 32,
        AI_QUOTA_LIMITS={"demo": {"monthly_ai_requests": 0}},
    )))
    tool = GetBillingStatusTool(db_session, usage_service)
    context = ToolExecutionContext(
        tenant=TenantContext(company_id=company.id), user_id=user.id,
        permissions=frozenset({"ai:use"}), request_id="req-1",
    )

    result = await tool.run(context, ToolArguments())

    assert result.success is True
    assert result.data["plan_code"] == "demo"
    assert result.data["subscription_status"] == "active"
    assert result.data["monthly_ai_quota_reached"] is True
    assert "sk-" not in str(result.data)
    assert "stripe" not in str(result.data).lower()


# ---------------------------------------------------------------------------
# 4. Avenqo Admin Command Center — platform_admin only, never automatic
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_client(db_session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", "a" * 32)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_admin")
    monkeypatch.setenv(
        "AI_QUOTA_LIMITS",
        '{"professional":{"monthly_ai_requests":1000},"enterprise":{"monthly_ai_requests":5000}}',
    )
    get_settings.cache_clear()
    app = create_application()

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_account_notifier] = lambda: _NullNotifier()
    with TestClient(app) as client:
        yield client
    get_settings.cache_clear()


def _access_token(db_session, user: User) -> str:
    from datetime import datetime, timedelta, timezone

    from backend.app.core.security import create_access_token
    from backend.app.models import AuthSession

    session_id = uuid4()
    now = datetime.now(timezone.utc)
    db_session.add(AuthSession(
        id=session_id, user_id=user.id, token_hash=f"hash-{session_id}",
        created_at=now, expires_at=now + timedelta(days=1),
    ))
    db_session.commit()
    token, _ = create_access_token(user.id, user.company_id, session_id)
    return token


class _TenantEchoSalesService:
    def __init__(self, revenues: dict) -> None:
        self.revenues = revenues

    def build(self, tenant, **_) -> dict:
        revenue = self.revenues[tenant.company_id]
        return {
            "status": "ready",
            "available": True,
            "currency": "USD",
            "capabilities": ["sales"],
            "period": {
                "key": "last_30_days",
                "start": None,
                "end": None,
                "comparison_start": None,
                "comparison_end": None,
                "date_filter_available": False,
                "granularity": "day",
            },
            "summary": {
                "revenue": revenue,
                "orders": 1,
                "average_order_value": revenue,
                "rows_considered": 1,
                "previous_revenue": None,
                "previous_orders": None,
                "revenue_change_percent": None,
                "orders_change_percent": None,
            },
            "trend": {"granularity": "day", "points": []},
            "strongest_period": None,
            "weakest_period": None,
            "forecast": None,
        }


def test_tenant_owner_is_denied_admin_access(db_session, admin_client: TestClient) -> None:
    company = _company(db_session, slug="tenant-co")
    owner = _user(db_session, company, platform_admin=False, role=UserRole.OWNER)
    db_session.commit()
    token = _access_token(db_session, owner)

    response = admin_client.get(
        "/api/v1/admin/dashboard", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code in (401, 403)


def test_admin_retail_context_requires_platform_admin_and_existing_company(
    db_session,
    admin_client: TestClient,
) -> None:
    tenant = _company(db_session, slug="retail-context-target")
    owner = _user(db_session, tenant)
    admin_company = _company(db_session, slug="retail-context-admin")
    admin = _user(db_session, admin_company, platform_admin=True)
    db_session.commit()

    owner_headers = {"Authorization": f"Bearer {_access_token(db_session, owner)}"}
    denied = admin_client.post(
        f"/api/v1/admin/companies/{tenant.id}/retail/context",
        headers=owner_headers,
    )
    assert denied.status_code == 403
    denied_data = admin_client.get(
        f"/api/v1/admin/companies/{tenant.id}/retail/sales/summary",
        headers=owner_headers,
    )
    assert denied_data.status_code == 403

    admin_headers = {"Authorization": f"Bearer {_access_token(db_session, admin)}"}
    missing = admin_client.post(
        f"/api/v1/admin/companies/{uuid4()}/retail/context",
        headers=admin_headers,
    )
    assert missing.status_code == 404

    selected = admin_client.post(
        f"/api/v1/admin/companies/{tenant.id}/retail/context",
        headers=admin_headers,
    )
    assert selected.status_code == 200
    assert selected.json() == {"company_id": str(tenant.id), "company_name": tenant.name}
    entered = AuditLogService(db_session).recent(limit=1)[0]
    assert entered.action == "admin_retail_context_entered"
    assert entered.actor_user_id == admin.id
    assert entered.company_id == tenant.id

    exited = admin_client.post(
        f"/api/v1/admin/companies/{tenant.id}/retail/context/exit",
        headers=admin_headers,
    )
    assert exited.status_code == 204
    assert AuditLogService(db_session).recent(limit=1)[0].action == "admin_retail_context_exited"

    mutation = admin_client.post(
        f"/api/v1/admin/companies/{tenant.id}/retail/sales/summary",
        headers=admin_headers,
    )
    assert mutation.status_code == 405


def test_admin_retail_data_is_explicit_and_switching_never_leaks_previous_tenant(
    db_session,
    admin_client: TestClient,
) -> None:
    tenant_a = _company(db_session, slug="retail-admin-a")
    tenant_b = _company(db_session, slug="retail-admin-b")
    admin_company = _company(db_session, slug="retail-admin-platform")
    admin = _user(db_session, admin_company, platform_admin=True)
    db_session.commit()
    admin_client.app.dependency_overrides[get_tenant_sales_service] = lambda: _TenantEchoSalesService(
        {tenant_a.id: 101.0, tenant_b.id: 202.0}
    )
    headers = {"Authorization": f"Bearer {_access_token(db_session, admin)}"}

    no_context = admin_client.get("/api/v1/admin/retail/sales/summary", headers=headers)
    assert no_context.status_code == 404

    response_a = admin_client.get(
        f"/api/v1/admin/companies/{tenant_a.id}/retail/sales/summary",
        headers=headers,
    )
    response_b = admin_client.get(
        f"/api/v1/admin/companies/{tenant_b.id}/retail/sales/summary",
        headers=headers,
    )
    assert response_a.status_code == response_b.status_code == 200
    assert response_a.json()["summary"]["revenue"] == 101.0
    assert response_b.json()["summary"]["revenue"] == 202.0


def test_normal_sales_route_still_uses_authenticated_client_tenant(
    db_session,
    admin_client: TestClient,
) -> None:
    tenant = _company(db_session, slug="normal-retail-tenant", plan="professional")
    owner = _user(db_session, tenant)
    db_session.add(BillingAccount(company_id=tenant.id, plan_code="professional", status="active"))
    db_session.commit()
    admin_client.app.dependency_overrides[get_tenant_sales_service] = lambda: _TenantEchoSalesService(
        {tenant.id: 303.0}
    )
    headers = {"Authorization": f"Bearer {_access_token(db_session, owner)}"}

    response = admin_client.get("/api/v1/sales/summary", headers=headers)
    assert response.status_code == 200
    assert response.json()["summary"]["revenue"] == 303.0


def test_platform_admin_can_view_dashboard_and_company_directory(db_session, admin_client: TestClient) -> None:
    company = _company(db_session, slug="admin-view-co", plan="professional")
    current_period = AIUsageService(
        db_session,
        AIQuotaPolicy(Settings(AUTH_JWT_SECRET="a" * 32)),
    ).current_billing_period()
    db_session.add(BillingAccount(company_id=company.id, plan_code="professional", status="active"))
    db_session.add(TenantAICreditBalance(
        company_id=company.id,
        monthly_period=current_period,
        monthly_used=250,
        purchased_balance=500,
    ))
    db_session.commit()
    admin_company = _company(db_session, slug="avenqo-hq")
    admin_user = _user(db_session, admin_company, platform_admin=True)
    db_session.commit()

    token = _access_token(db_session, admin_user)
    headers = {"Authorization": f"Bearer {token}"}

    dashboard = admin_client.get("/api/v1/admin/dashboard", headers=headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["total_companies"] >= 2

    directory = admin_client.get("/api/v1/admin/companies", headers=headers)
    assert directory.status_code == 200
    names = {entry["name"] for entry in directory.json()}
    assert "Acme" in names
    company_entry = next(entry for entry in directory.json() if entry["id"] == str(company.id))
    assert company_entry["monthly_credits"] == 1000
    assert company_entry["monthly_credits_remaining"] == 750
    assert company_entry["purchased_credits_remaining"] == 500
    assert company_entry["total_credits_remaining"] == 1250


def test_platform_admin_can_view_company_invoices_but_tenant_owner_cannot(
    db_session,
    admin_client: TestClient,
) -> None:
    tenant = _company(db_session, slug="invoice-tenant")
    owner = _user(db_session, tenant)
    admin_company = _company(db_session, slug="invoice-admin")
    admin = _user(db_session, admin_company, platform_admin=True)
    db_session.add(BillingInvoice(
        company_id=tenant.id,
        stripe_invoice_id="in_admin_visible",
        number="AVQ-1001",
        plan_code="professional",
        status="paid",
        currency="cad",
        amount_due=6700,
        amount_paid=6700,
        hosted_invoice_url="https://invoice.stripe.test/in_admin_visible",
        invoice_pdf="https://invoice.stripe.test/in_admin_visible.pdf",
        period_start=datetime(2026, 8, 1, tzinfo=timezone.utc),
        period_end=datetime(2026, 9, 1, tzinfo=timezone.utc),
        issued_at=datetime.now(timezone.utc),
    ))
    db_session.commit()
    path = f"/api/v1/admin/companies/{tenant.id}/billing/invoices"

    denied = admin_client.get(
        path,
        headers={"Authorization": f"Bearer {_access_token(db_session, owner)}"},
    )
    allowed = admin_client.get(
        path,
        headers={"Authorization": f"Bearer {_access_token(db_session, admin)}"},
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert [invoice["number"] for invoice in allowed.json()] == ["AVQ-1001"]


def test_platform_admin_can_set_enterprise_override_and_it_is_audited(db_session, admin_client: TestClient) -> None:
    company = _company(db_session, slug="enterprise-co", plan="enterprise")
    admin_company = _company(db_session, slug="avenqo-hq-2")
    admin_user = _user(db_session, admin_company, platform_admin=True)
    db_session.commit()

    token = _access_token(db_session, admin_user)
    headers = {"Authorization": f"Bearer {token}"}

    response = admin_client.put(
        f"/api/v1/admin/companies/{company.id}/enterprise-override",
        headers=headers,
        json={"quota_overrides": {"monthly_ai_requests": 9999}, "capability_overrides": {"segmentation": True}, "notes": "Contrat spécial"},
    )
    assert response.status_code == 200
    assert response.json()["enterprise_override"]["quota_overrides"]["monthly_ai_requests"] == 9999

    audit = admin_client.get("/api/v1/admin/audit-log", headers=headers)
    assert audit.status_code == 200
    actions = [entry["action"] for entry in audit.json()]
    assert "enterprise_override.set" in actions
