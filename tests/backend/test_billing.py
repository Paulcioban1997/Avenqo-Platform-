from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config.settings import get_settings
from backend.app.database import get_db
from backend.app.dependencies.auth import get_account_notifier
from backend.app.dependencies.billing import get_billing_provider
from backend.app.models import Base
from backend.main import create_application


class RecordingNotifier:
    def __init__(self) -> None:
        self.verification_tokens: dict[str, str] = {}

    def send_email_verification(self, email: str, token: str) -> None:
        self.verification_tokens[email] = token

    def send_password_reset(self, email: str, token: str) -> None:
        pass


class FakeStripeProvider:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.changed_prices: list[str] = []
        self.cancelled_subscriptions: list[str] = []
        self.credit_checkouts: list[str] = []

    def create_customer(self, email: str, name: str, company_id: str) -> str:
        return f"cus_{company_id}"

    def create_checkout(
        self,
        customer_id: str,
        price_id: str,
        company_id: str,
        success_url: str,
        cancel_url: str,
    ) -> str:
        return f"https://checkout.stripe.test/{price_id}"

    def create_credit_checkout(
        self,
        customer_id: str,
        company_id: str,
        pack_code: str,
        credits: int,
        price_usd: int,
        success_url: str,
        cancel_url: str,
    ) -> str:
        self.credit_checkouts.append(pack_code)
        return f"https://checkout.stripe.test/credits/{pack_code}"

    def change_subscription(self, subscription_id: str, price_id: str) -> None:
        self.changed_prices.append(price_id)

    def cancel_subscription(self, subscription_id: str) -> None:
        self.cancelled_subscriptions.append(subscription_id)

    def create_portal(self, customer_id: str, return_url: str) -> str:
        return "https://billing.stripe.test/session"

    def construct_event(self, payload: bytes, signature: str, secret: str) -> dict[str, Any]:
        if signature != "valid_signature":
            raise ValueError("Signature incorrecte")
        return self.events.pop(0)


@pytest.fixture
def billing_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, FakeStripeProvider, RecordingNotifier], None, None]:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_avenqo")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_avenqo")
    monkeypatch.setenv("STRIPE_PRICE_DEMO", "price_demo")
    monkeypatch.setenv("STRIPE_PRICE_PROFESSIONAL", "price_professional")
    monkeypatch.setenv("STRIPE_PRICE_ENTERPRISE", "price_enterprise")
    get_settings.cache_clear()
    engine = create_engine(
        f"sqlite:///{tmp_path / 'billing.db'}",
        connect_args={"check_same_thread": False},
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    provider = FakeStripeProvider()
    notifier = RecordingNotifier()
    app = create_application()

    def override_db() -> Generator[Session, None, None]:
        with testing_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_billing_provider] = lambda: provider
    app.dependency_overrides[get_account_notifier] = lambda: notifier
    with TestClient(app) as client:
        yield client, provider, notifier
    get_settings.cache_clear()


def create_owner(
    client: TestClient,
    notifier: RecordingNotifier,
    email: str = "owner@acme.ca",
    company_name: str = "Acme Retail",
) -> dict[str, Any]:
    payload = {
        "company_name": company_name,
        "company_email": f"billing+{email}",
        "first_name": "Alex",
        "last_name": "Martin",
        "email": email,
        "password": "Avenqo2026!",
        "country": "Canada",
        "timezone": "America/Toronto",
        "industry": "E-commerce",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    assert client.post(
        "/api/v1/auth/email/verify",
        json={"token": notifier.verification_tokens[email]},
    ).status_code == 200
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": payload["password"]},
    )
    assert login.status_code == 200
    return login.json()


def auth_headers(login: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {login['access_token']}"}


def subscription_event(company_id: str, event_id: str = "evt_subscription") -> dict[str, Any]:
    return {
        "id": event_id,
        "type": "customer.subscription.updated",
        "data": {"object": {
            "id": "sub_acme",
            "customer": f"cus_{company_id}",
            "status": "active",
            "cancel_at_period_end": False,
            "current_period_end": 1_800_000_000,
            "metadata": {"avenqo_company_id": company_id},
            "items": {"data": [{"price": {"id": "price_professional"}}]},
        }},
    }


def test_checkout_et_cycle_abonnement(billing_environment) -> None:
    client, provider, notifier = billing_environment
    login = create_owner(client, notifier)
    headers = auth_headers(login)

    plans = client.get("/api/v1/billing/plans")
    assert plans.status_code == 200
    catalog = plans.json()
    assert [plan["code"] for plan in catalog] == ["demo", "professional", "enterprise"]
    assert [plan["monthly_price_usd"] for plan in catalog] == [28, 49, None]
    assert [plan["included_ai_credits"] for plan in catalog] == [5000, 25000, None]
    assert [plan["requires_sales_contact"] for plan in catalog] == [False, False, True]

    packs = client.get("/api/v1/billing/credit-packs")
    assert packs.status_code == 200
    assert [(item["credits"], item["price_usd"]) for item in packs.json()] == [
        (5000, 10), (20000, 29), (50000, 59), (150000, 149)
    ]

    portal = client.post("/api/v1/billing/portal", headers=headers)
    assert portal.status_code == 200
    assert portal.json()["url"] == "https://billing.stripe.test/session"

    checkout = client.post(
        "/api/v1/billing/checkout",
        json={"plan_code": "professional"},
        headers=headers,
    )
    assert checkout.status_code == 200
    assert checkout.json()["url"].endswith("price_professional")

    assert client.post(
        "/api/v1/billing/checkout",
        json={"plan_code": "enterprise"},
        headers=headers,
    ).status_code == 400
    assert client.post(
        "/api/v1/billing/checkout",
        json={"plan_code": "custom_enterprise"},
        headers=headers,
    ).status_code == 400

    provider.events.append(subscription_event(login["company"]["id"]))
    webhook = client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid_signature"},
    )
    assert webhook.status_code == 200
    subscription = client.get("/api/v1/billing/subscription", headers=headers)
    assert subscription.json()["plan_code"] == "professional"
    assert subscription.json()["status"] == "active"

    credits = client.get("/api/v1/billing/credits", headers=headers)
    assert credits.status_code == 200
    assert credits.json()["monthly_allowance"] == 25000
    assert credits.json()["total_remaining"] == 25000

    assert client.post(
        "/api/v1/billing/change-plan",
        json={"plan_code": "enterprise"},
        headers=headers,
    ).status_code == 400
    changed = client.post(
        "/api/v1/billing/change-plan",
        json={"plan_code": "demo"},
        headers=headers,
    )
    assert changed.status_code == 200
    assert provider.changed_prices == ["price_demo"]

    assert client.post("/api/v1/billing/cancel", headers=headers).json()["cancel_at_period_end"] is True
    assert provider.cancelled_subscriptions == ["sub_acme"]


def test_pack_credits_est_un_achat_unique_et_idempotent(billing_environment) -> None:
    client, provider, notifier = billing_environment
    login = create_owner(client, notifier)
    headers = auth_headers(login)
    company_id = login["company"]["id"]

    # Les top-ups complètent un abonnement : ils ne remplacent jamais l'abonnement.
    inactive_checkout = client.post(
        "/api/v1/billing/credits/checkout",
        json={"pack_code": "credits_20k"},
        headers=headers,
    )
    assert inactive_checkout.status_code == 400
    assert provider.credit_checkouts == []

    provider.events.append(subscription_event(company_id, "evt_subscription_pack"))
    activated = client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid_signature"},
    )
    assert activated.json() == {"processed": True}

    checkout = client.post(
        "/api/v1/billing/credits/checkout",
        json={"pack_code": "credits_20k"},
        headers=headers,
    )
    assert checkout.status_code == 200
    assert provider.credit_checkouts == ["credits_20k"]

    event = {
        "id": "evt_credit_pack",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_credit_1",
            "payment_status": "paid",
            "metadata": {
                "avenqo_company_id": company_id,
                "avenqo_checkout_kind": "ai_credit_pack",
                "avenqo_credit_pack": "credits_20k",
            },
        }},
    }
    provider.events.extend([event, event])
    first = client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid_signature"},
    )
    second = client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid_signature"},
    )
    assert first.json() == {"processed": True}
    assert second.json() == {"processed": False}

    balance = client.get("/api/v1/billing/credits", headers=headers).json()
    assert balance["monthly_remaining"] == 25000
    assert balance["purchased_remaining"] == 20000
    assert balance["total_remaining"] == 45000


def test_factures_sont_isolees_et_webhooks_idempotents(billing_environment) -> None:
    client, provider, notifier = billing_environment
    acme = create_owner(client, notifier)
    nova = create_owner(client, notifier, "owner@nova.ca", "Nova Commerce")
    company_id = acme["company"]["id"]
    invoice_event = {
        "id": "evt_invoice",
        "type": "invoice.paid",
        "data": {"object": {
            "id": "in_acme",
            "customer": f"cus_{company_id}",
            "number": "NEX-0001",
            "status": "paid",
            "currency": "cad",
            "amount_due": 9900,
            "amount_paid": 9900,
            "hosted_invoice_url": "https://invoice.stripe.test/in_acme",
            "invoice_pdf": "https://invoice.stripe.test/in_acme.pdf",
            "created": 1_750_000_000,
            "metadata": {"avenqo_company_id": company_id},
        }},
    }
    provider.events.extend([invoice_event, invoice_event])
    first = client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid_signature"},
    )
    second = client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid_signature"},
    )
    assert first.json() == {"processed": True}
    assert second.json() == {"processed": False}
    assert len(client.get("/api/v1/billing/invoices", headers=auth_headers(acme)).json()) == 1
    assert client.get("/api/v1/billing/invoices", headers=auth_headers(nova)).json() == []
    assert client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "invalid"},
    ).status_code == 400
