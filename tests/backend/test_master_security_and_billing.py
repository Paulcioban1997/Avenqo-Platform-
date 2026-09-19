"""Test suite de sécurité absolue et d'isolation multi-tenant pour Avenqo.

Vérifie l'ensemble des exigences P0 et P1 :
- Absence totale de porte dérobée de développement (401 strict pour requêtes non authentifiées).
- Identité réelle de l'utilisateur authentifié (Lucia vs Mircea).
- Isolation stricte des adhésions d'entreprises (organization switcher).
- Blocage strict des attaques cross-tenant (switch de tenant non autorisé -> 403).
- Audit trail pour les switchs de tenant par SUPER_ADMIN.
- Téléchargement sécurisé des factures PDF avec blocage cross-tenant (404/403).
- Isolation complète des métriques de facturation et crédits IA.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.security import hash_password
from backend.app.database import get_db
from backend.app.dependencies.auth import get_account_notifier
from backend.app.models import (
    AuditLogEntry,
    Base,
    BillingAccount,
    BillingInvoice,
    Company,
    CompanyMembership,
    CompanyModule,
    CompanyOnboarding,
    CompanyStatus,
    CRMClient,
    OnboardingStatus,
    TenantAIProviderAttempt,
    User,
    UserRole,
)
from backend.main import create_application


class MockNotifier:
    def __init__(self) -> None:
        self.verification_tokens: dict[str, str] = {}

    email_delivery_configured = True

    def send_email_verification(self, email: str, token: str) -> None:
        self.verification_tokens[email] = token

    def send_password_reset(self, email: str, token: str) -> None:
        pass


@pytest.fixture
def sec_env(tmp_path: Path) -> Generator[tuple[TestClient, sessionmaker[Session], MockNotifier], None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'security_test.db'}",
        connect_args={"check_same_thread": False},
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    notifier = MockNotifier()
    app = create_application()

    def override_db() -> Generator[Session, None, None]:
        session = testing_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_account_notifier] = lambda: notifier
    with TestClient(app) as client:
        yield client, testing_session, notifier


def _register_and_login(client: TestClient, notifier: MockNotifier, first_name: str, email: str, company_name: str) -> str:
    res = client.post(
        "/api/v1/auth/register",
        json={
            "company_name": company_name,
            "company_email": f"billing_{email}",
            "first_name": first_name,
            "last_name": "Testeur",
            "email": email,
            "password": "Password123!",
            "country": "Canada",
            "timezone": "America/Toronto",
            "industry": "Retail",
        },
    )
    assert res.status_code == 201
    tok = notifier.verification_tokens[email]
    v_res = client.post("/api/v1/auth/email/verify", json={"token": tok})
    assert v_res.status_code == 200

    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    assert login_res.status_code == 200
    return login_res.json()["access_token"]


def test_unauthenticated_requests_strictly_rejected(sec_env) -> None:
    client, _, _ = sec_env

    # Les requêtes sans jeton d'authentification doivent impérativement retourner 401 Unauthorized
    # Aucune usurpation automatique en compte dev_user n'est permise.
    r1 = client.get("/api/v1/auth/me")
    assert r1.status_code == 401

    r2 = client.get("/api/v1/crm/summary")
    assert r2.status_code == 401

    r3 = client.get("/api/v1/billing/subscription")
    assert r3.status_code == 401

    r4 = client.get("/api/v1/billing/ai-credits")
    assert r4.status_code == 401


def test_authenticated_user_identity_real_names_and_organizations(sec_env) -> None:
    client, _, notifier = sec_env

    # Compte A : Lucia chez Lucia Boutique
    token_lucia = _register_and_login(client, notifier, "Lucia", "lucia@boutique.ca", "Lucia Boutique Inc")

    # Compte B : Mircea chez Produits Miro
    token_mircea = _register_and_login(client, notifier, "Mircea", "mircea@produits.ca", "Produits Miro Inc")

    # Vérification identité Lucia
    me_lucia = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_lucia}"})
    assert me_lucia.status_code == 200
    data_lucia = me_lucia.json()
    assert data_lucia["user"]["first_name"] == "Lucia"
    assert data_lucia["company"]["name"] == "Lucia Boutique Inc"

    # Vérification identité Mircea
    me_mircea = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_mircea}"})
    assert me_mircea.status_code == 200
    data_mircea = me_mircea.json()
    assert data_mircea["user"]["first_name"] == "Mircea"
    assert data_mircea["company"]["name"] == "Produits Miro Inc"

    # Lucia ne voit QUE son entreprise dans /organizations
    orgs_lucia = client.get("/api/v1/auth/organizations", headers={"Authorization": f"Bearer {token_lucia}"}).json()
    assert len(orgs_lucia) == 1
    assert orgs_lucia[0]["name"] == "Lucia Boutique Inc"

    # Mircea ne voit QUE son entreprise dans /organizations
    orgs_mircea = client.get("/api/v1/auth/organizations", headers={"Authorization": f"Bearer {token_mircea}"}).json()
    assert len(orgs_mircea) == 1
    assert orgs_mircea[0]["name"] == "Produits Miro Inc"


def test_cross_tenant_switch_attack_prevented(sec_env) -> None:
    client, session_factory, notifier = sec_env

    token_lucia = _register_and_login(client, notifier, "Lucia", "lucia@boutique.ca", "Lucia Boutique Inc")
    token_mircea = _register_and_login(client, notifier, "Mircea", "mircea@produits.ca", "Produits Miro Inc")

    with session_factory() as session:
        mircea_company = session.scalar(select(Company).where(Company.name == "Produits Miro Inc"))
        assert mircea_company is not None
        mircea_company_id = str(mircea_company.id)

    # Attaque : Lucia tente de changer de tenant vers l'entreprise de Mircea
    hack_res = client.post(
        "/api/v1/auth/switch-tenant",
        headers={"Authorization": f"Bearer {token_lucia}"},
        json={"company_id": mircea_company_id},
    )

    # DOIT ÊTRE REFUSÉ : 403 Forbidden
    assert hack_res.status_code == 403
    err_body = hack_res.json()
    err_msg = err_body.get("error", {}).get("message", "") or err_body.get("detail", "")
    assert "non autorisé" in err_msg.lower()


def test_super_admin_tenant_switch_and_audit_trail(sec_env) -> None:
    client, session_factory, notifier = sec_env

    # Création d'une entreprise cible
    token_lucia = _register_and_login(client, notifier, "Lucia", "lucia@boutique.ca", "Lucia Boutique Inc")
    with session_factory() as session:
        target_company = session.scalar(select(Company).where(Company.name == "Lucia Boutique Inc"))
        target_company_id = target_company.id

        # Création d'un SUPER_ADMIN Avenqo
        admin_company = Company(
            name="Avenqo Platform Ops",
            slug=f"avenqo-platform-{uuid4().hex[:6]}",
            email="platform.admin@avenqo.ca",
            country="Canada",
            timezone="America/Toronto",
            industry="Technology",
            subscription_plan="enterprise",
            status=CompanyStatus.ACTIVE,
        )
        session.add(admin_company)
        session.flush()

        admin_user = User(
            company_id=admin_company.id,
            email="platform.admin@avenqo.ca",
            password_hash=hash_password("SuperSecretAvenqo2026!"),
            first_name="Platform",
            last_name="SuperAdmin",
            role=UserRole.ADMIN,
            is_platform_admin=True,
            is_active=True,
            email_verified_at=datetime.now(timezone.utc),
        )
        session.add(admin_user)
        session.commit()

    # Connexion du SUPER_ADMIN
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "platform.admin@avenqo.ca", "password": "SuperSecretAvenqo2026!"},
    )
    assert login_res.status_code == 200
    admin_token = login_res.json()["access_token"]

    # Le SUPER_ADMIN commute vers Lucia Boutique Inc
    switch_res = client.post(
        "/api/v1/auth/switch-tenant",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"company_id": str(target_company_id)},
    )
    assert switch_res.status_code == 200
    assert switch_res.json()["company"]["name"] == "Lucia Boutique Inc"

    # Vérification que l'événement d'audit immuable a bien été consigné
    with session_factory() as session:
        audit = session.scalar(
            select(AuditLogEntry).where(
                AuditLogEntry.action == "super_admin_tenant_switch",
                AuditLogEntry.target_id == str(target_company_id),
            )
        )
        assert audit is not None
        assert audit.safe_metadata["admin_email"] == "platform.admin@avenqo.ca"


def test_cross_tenant_invoice_pdf_download_denied(sec_env) -> None:
    client, session_factory, notifier = sec_env

    token_lucia = _register_and_login(client, notifier, "Lucia", "lucia@boutique.ca", "Lucia Boutique Inc")
    token_mircea = _register_and_login(client, notifier, "Mircea", "mircea@produits.ca", "Produits Miro Inc")

    with session_factory() as session:
        mircea_company = session.scalar(select(Company).where(Company.name == "Produits Miro Inc"))
        # Création d'une facture pour Mircea
        invoice_mircea = BillingInvoice(
            company_id=mircea_company.id,
            stripe_invoice_id="in_test_mircea_123",
            number="AVQ-2026-MIRCEA-01",
            status="paid",
            currency="CAD",
            total=4900,
            amount_paid=4900,
            amount_due=0,
            plan_code="professional",
            issued_at=datetime.now(timezone.utc),
        )
        session.add(invoice_mircea)
        session.commit()
        invoice_id = str(invoice_mircea.id)

    # Lucia tente de télécharger la facture PDF de Mircea
    steal_res = client.get(
        f"/api/v1/billing/invoices/{invoice_id}/pdf",
        headers={"Authorization": f"Bearer {token_lucia}"},
    )

    # DOIT ÊTRE 404 (Introuvable pour ce tenant)
    assert steal_res.status_code in (403, 404)


def test_billing_subscription_and_ai_credits_scoped_to_tenant(sec_env) -> None:
    from decimal import Decimal

    client, session_factory, notifier = sec_env

    token_lucia = _register_and_login(client, notifier, "Lucia", "lucia@boutique.ca", "Lucia Boutique Inc")

    with session_factory() as session:
        lucia_company = session.scalar(select(Company).where(Company.name == "Lucia Boutique Inc"))

        # Création d'une tentative IA pour Lucia
        attempt = TenantAIProviderAttempt(
            company_id=lucia_company.id,
            avenqo_request_id=f"req_{uuid4().hex[:12]}",
            attempt_number=1,
            operation="retail_demand_forecast",
            provider="google_gemini",
            model="gemini-2.0-flash",
            success=True,
            latency_ms=320,
            provider_cost_usd=Decimal("0.001"),
            input_cost_per_million_usd=Decimal("0.5"),
            cached_input_cost_per_million_usd=Decimal("0.25"),
            output_cost_per_million_usd=Decimal("1.5"),
            tool_call_cost_usd=Decimal("0.0"),
            avenqo_credits=42,
        )
        session.add(attempt)
        session.commit()

    # Vérification subscription
    sub_res = client.get("/api/v1/billing/subscription", headers={"Authorization": f"Bearer {token_lucia}"})
    assert sub_res.status_code == 200
    sub_data = sub_res.json()
    assert sub_data["company_name"] == "Lucia Boutique Inc"

    # Vérification breakdown
    bd_res = client.get("/api/v1/billing/ai-credits/breakdown", headers={"Authorization": f"Bearer {token_lucia}"})
    assert bd_res.status_code == 200
    bd_data = bd_res.json()
    assert bd_data["total_used"] == 42
    retail_item = next((item for item in bd_data["items"] if item["module"] == "Retail AI"), None)
    assert retail_item is not None
    assert retail_item["credits_used"] == 42

    # Vérification history
    hist_res = client.get("/api/v1/billing/ai-credits/history", headers={"Authorization": f"Bearer {token_lucia}"})
    assert hist_res.status_code == 200
    hist_data = hist_res.json()
    assert hist_data["total"] == 1
    assert hist_data["items"][0]["credits_used"] == 42
    assert "Lucia" in hist_data["items"][0]["user"]
