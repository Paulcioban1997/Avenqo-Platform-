from collections.abc import Generator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config.settings import get_settings
from backend.app.ai.usage.policy import AIQuotaPolicy, MONTHLY_AI_REQUESTS
from backend.app.database import get_db
from backend.app.dependencies.auth import get_account_notifier
from backend.app.dependencies.billing import get_billing_provider
from backend.app.models import Base, Company
from backend.app.services.stripe_gateway import StripeGateway
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
        self.credit_checkouts: list[dict[str, Any]] = []

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

    def change_subscription(self, subscription_id: str, price_id: str) -> None:
        self.changed_prices.append(price_id)

    def create_credit_checkout(
        self,
        customer_id: str,
        price_id: str,
        metadata: dict[str, str],
        success_url: str,
        cancel_url: str,
    ) -> str:
        self.credit_checkouts.append({
            "customer_id": customer_id,
            "price_id": price_id,
            "metadata": metadata,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "mode": "payment",
        })
        return "https://checkout.stripe.test/credits"

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
    monkeypatch.setenv("STRIPE_PRICE_CREDIT_DEMO", "price_credit_demo")
    monkeypatch.setenv("STRIPE_PRICE_CREDIT_PROFESSIONAL", "price_credit_professional")
    monkeypatch.setenv("STRIPE_PRICE_ENTERPRISE", "price_enterprise")
    monkeypatch.setenv(
        "AI_QUOTA_LIMITS",
        '{"demo":{"monthly_ai_requests":6500},"professional":{"monthly_ai_requests":25000}}',
    )
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


def subscription_event(
    company_id: str,
    event_id: str = "evt_subscription",
    plan_code: str = "professional",
) -> dict[str, Any]:
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
            "items": {"data": [{"price": {"id": f"price_{plan_code}"}}]},
        }},
    }


def invoice_event(
    company_id: str,
    *,
    event_id: str = "evt_invoice",
    event_type: str = "invoice.paid",
    billing_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "type": event_type,
        "data": {"object": {
            "id": "in_acme",
            "customer": f"cus_{company_id}",
            "number": "AVQ-0001",
            "status": "paid" if event_type == "invoice.paid" else "open",
            "billing_reason": billing_reason,
            "currency": "cad",
            "amount_due": 6700,
            "amount_paid": 6700 if event_type == "invoice.paid" else 0,
            "hosted_invoice_url": "https://invoice.stripe.test/in_acme",
            "invoice_pdf": "https://invoice.stripe.test/in_acme.pdf",
            "created": 1_750_000_000,
            "metadata": {"avenqo_company_id": company_id},
            "lines": {"data": [{
                "price": {"id": "price_professional"},
                "period": {"start": 1_749_000_000, "end": 1_751_000_000},
            }]},
        }},
    }


def test_checkout_et_cycle_abonnement(billing_environment) -> None:
    client, provider, notifier = billing_environment
    login = create_owner(client, notifier)
    headers = auth_headers(login)

    plans = client.get("/api/v1/billing/plans")
    assert plans.status_code == 200
    catalog = plans.json()
    assert [plan["code"] for plan in catalog] == [
        "demo", "professional", "enterprise"
    ]
    assert [plan["monthly_price_usd"] for plan in catalog] == [28, 49, None]
    assert [plan["requires_sales_contact"] for plan in catalog] == [False, False, True]

    # Un nouveau tenant peut ouvrir le portail : le Customer Stripe est créé à la demande.
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

    # Les offres nécessitant un contact commercial ne peuvent jamais contourner
    # cette règle en appelant directement l'API Checkout.
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

    # Même politique pour un changement d'offre existante.
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
    canceled = client.post("/api/v1/billing/cancel", headers=headers).json()
    assert canceled["cancel_at_period_end"] is True
    assert canceled["status"] == "canceling_at_period_end"
    assert canceled["current_period_end"] is not None
    assert provider.cancelled_subscriptions == ["sub_acme"]


def credit_checkout_event(
    company_id: str,
    *,
    event_id: str = "evt_credit_checkout",
    customer_id: str | None = None,
    payment_status: str = "paid",
    amount_total: int = 1_000,
    metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": f"cs_{event_id}",
            "customer": customer_id or f"cus_{company_id}",
            "payment_status": payment_status,
            "amount_total": amount_total,
            "currency": "usd",
            "metadata": metadata or {
                "avenqo_kind": "ai_credit_pack",
                "avenqo_company_id": company_id,
                "avenqo_credit_pack": "professional_extra",
                "avenqo_plan_code": "professional",
                "avenqo_credits": "25000",
            },
        }},
    }


def test_credit_pack_checkout_requires_subscription_and_fulfills_once(billing_environment) -> None:
    client, provider, notifier = billing_environment
    login = create_owner(client, notifier, email="credits@acme.ca", company_name="Credits Inc")
    headers = auth_headers(login)
    company_id = login["company"]["id"]

    packs = client.get("/api/v1/billing/credit-packs", headers=headers)
    assert packs.status_code == 200
    assert packs.json() == [
        {"code": "demo_extra", "credits": 6500, "price_usd": 10},
    ]
    assert "price_id" not in packs.text

    refused = client.post(
        "/api/v1/billing/credit-packs/checkout",
        json={"pack_code": "demo_extra"},
        headers=headers,
    )
    assert refused.status_code == 400

    provider.events.append(subscription_event(
        company_id,
        event_id="evt_credit_subscription",
        plan_code="demo",
    ))
    assert client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid_signature"},
    ).status_code == 200

    checkout = client.post(
        "/api/v1/billing/credit-packs/checkout",
        json={
            "pack_code": "demo_extra",
            "company_id": "00000000-0000-0000-0000-000000000000",
            "credits": 999_999_999,
            "price_usd": 1,
        },
        headers=headers,
    )
    assert checkout.status_code == 200
    assert provider.credit_checkouts == [{
        "customer_id": f"cus_{company_id}",
        "price_id": "price_credit_demo",
        "metadata": {
            "avenqo_kind": "ai_credit_pack",
            "avenqo_company_id": company_id,
            "avenqo_credit_pack": "demo_extra",
            "avenqo_plan_code": "demo",
            "avenqo_credits": "6500",
        },
        "success_url": "http://localhost:8080/billing?credits=success",
        "cancel_url": "http://localhost:8080/billing?credits=cancelled",
        "mode": "payment",
    }]

    event = credit_checkout_event(
        company_id,
        metadata={
            "avenqo_kind": "ai_credit_pack",
            "avenqo_company_id": company_id,
            "avenqo_credit_pack": "demo_extra",
            "avenqo_plan_code": "demo",
            "avenqo_credits": "6500",
        },
    )
    provider.events.extend([event, event])
    first = client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid_signature"},
    )
    duplicate = client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid_signature"},
    )
    assert first.json() == {"processed": True}
    assert duplicate.json() == {"processed": False}
    balance = client.get(
        "/api/v1/billing/ai-credits?company_id=00000000-0000-0000-0000-000000000000",
        headers=headers,
    )
    assert balance.status_code == 200
    assert balance.json()["monthly_included"] == 6500
    assert balance.json()["purchased_remaining"] == 6500
    assert balance.json()["total_remaining"] == 13000

    policy = AIQuotaPolicy(get_settings())
    assert policy.limit_for("demo", MONTHLY_AI_REQUESTS) == 6500
    assert policy.limit_for("professional", MONTHLY_AI_REQUESTS) == 25000
    assert policy.limit_for("enterprise", MONTHLY_AI_REQUESTS) is None


def test_active_demo_account_controls_wallet_when_company_plan_is_stale(
    billing_environment,
    tmp_path: Path,
) -> None:
    client, provider, notifier = billing_environment
    login = create_owner(client, notifier, email="demo-wallet@acme.ca")
    headers = auth_headers(login)
    company_id = login["company"]["id"]
    provider.events.append(subscription_event(company_id, plan_code="demo"))
    assert client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid_signature"},
    ).status_code == 200

    engine = create_engine(f"sqlite:///{tmp_path / 'billing.db'}")
    with Session(engine) as session:
        company = session.get(Company, UUID(company_id))
        assert company is not None
        company.subscription_plan = "enterprise"
        session.commit()
    engine.dispose()

    subscription = client.get("/api/v1/billing/subscription", headers=headers)
    balance = client.get("/api/v1/billing/ai-credits", headers=headers)

    assert subscription.json()["plan_code"] == "demo"
    assert subscription.json()["status"] == "active"
    assert balance.json() == {
        "billing_period": balance.json()["billing_period"],
        "monthly_included": 6500,
        "monthly_used": 0,
        "monthly_remaining": 6500,
        "purchased_remaining": 0,
        "total_remaining": 6500,
    }


def test_credit_webhook_rejects_unpaid_or_tenant_mismatched_metadata(billing_environment) -> None:
    client, provider, notifier = billing_environment
    login_a = create_owner(client, notifier, email="credits-a@acme.ca", company_name="Credits A")
    headers_a = auth_headers(login_a)
    company_a = login_a["company"]["id"]
    provider.events.append(subscription_event(company_a, event_id="evt_sub_a"))
    client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid_signature"},
    )

    login_b = create_owner(client, notifier, email="credits-b@acme.ca", company_name="Credits B")
    headers_b = auth_headers(login_b)
    company_b = login_b["company"]["id"]
    provider.events.append(subscription_event(company_b, event_id="evt_sub_b"))
    client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid_signature"},
    )

    provider.events.append(credit_checkout_event(
        company_a,
        event_id="evt_wrong_customer",
        customer_id=f"cus_{company_b}",
    ))
    wrong_customer = client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid_signature"},
    )
    assert wrong_customer.status_code == 400

    provider.events.append(credit_checkout_event(
        company_a,
        event_id="evt_unpaid",
        payment_status="unpaid",
    ))
    unpaid = client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid_signature"},
    )
    assert unpaid.status_code == 400

    provider.events.append(credit_checkout_event(
        company_a,
        event_id="evt_unknown_pack",
        metadata={
            "avenqo_kind": "ai_credit_pack",
            "avenqo_company_id": company_a,
            "avenqo_credit_pack": "forged",
            "avenqo_plan_code": "professional",
            "avenqo_credits": "999999999",
        },
    ))
    unknown_pack = client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid_signature"},
    )
    assert unknown_pack.status_code == 400

    provider.events.append(credit_checkout_event(
        company_a,
        event_id="evt_tampered_credits",
        metadata={
            "avenqo_kind": "ai_credit_pack",
            "avenqo_company_id": company_a,
            "avenqo_credit_pack": "professional_extra",
            "avenqo_plan_code": "professional",
            "avenqo_credits": "999999999",
        },
    ))
    tampered_credits = client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid_signature"},
    )
    assert tampered_credits.status_code == 400

    localized_event = credit_checkout_event(
        company_a,
        event_id="evt_localized_amount",
        amount_total=1400,
    )
    localized_event["data"]["object"]["currency"] = "cad"
    provider.events.append(localized_event)
    localized_amount = client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid_signature"},
    )
    assert localized_amount.status_code == 200

    balance_a = client.get("/api/v1/billing/ai-credits", headers=headers_a).json()
    balance_b = client.get("/api/v1/billing/ai-credits", headers=headers_b).json()
    assert balance_a["purchased_remaining"] == 25000
    assert balance_b["purchased_remaining"] == 0


def test_professional_packs_accumulate_then_expire_at_subscription_renewal(
    billing_environment,
) -> None:
    client, provider, notifier = billing_environment
    login = create_owner(
        client,
        notifier,
        email="renewal@acme.ca",
        company_name="Renewal Inc",
    )
    headers = auth_headers(login)
    company_id = login["company"]["id"]
    provider.events.append(subscription_event(company_id, event_id="evt_renewal_sub"))
    assert client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid_signature"},
    ).status_code == 200

    assert client.get("/api/v1/billing/credit-packs", headers=headers).json() == [
        {"code": "professional_extra", "credits": 25000, "price_usd": 25}
    ]
    assert client.post(
        "/api/v1/billing/credit-packs/checkout",
        json={"pack_code": "demo_extra"},
        headers=headers,
    ).status_code == 400

    first_pack = credit_checkout_event(company_id, event_id="evt_pack_one")
    second_pack = credit_checkout_event(company_id, event_id="evt_pack_two")
    provider.events.extend([first_pack, second_pack])
    for _ in range(2):
        assert client.post(
            "/api/v1/billing/webhook",
            content=b"{}",
            headers={"Stripe-Signature": "valid_signature"},
        ).json() == {"processed": True}

    accumulated = client.get("/api/v1/billing/ai-credits", headers=headers).json()
    assert accumulated["monthly_included"] == 25000
    assert accumulated["purchased_remaining"] == 50000
    assert accumulated["total_remaining"] == 75000

    renewal = invoice_event(
        company_id,
        event_id="evt_subscription_cycle",
        billing_reason="subscription_cycle",
    )
    provider.events.extend([renewal, renewal])
    reset = client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid_signature"},
    )
    duplicate = client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid_signature"},
    )
    assert reset.json() == {"processed": True}
    assert duplicate.json() == {"processed": False}

    renewed = client.get("/api/v1/billing/ai-credits", headers=headers).json()
    assert renewed["monthly_included"] == 25000
    assert renewed["monthly_used"] == 0
    assert renewed["purchased_remaining"] == 0
    assert renewed["total_remaining"] == 25000


def test_stripe_credit_checkout_uses_configured_price(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def create_session(**kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(url="https://checkout.stripe.test/inline")

    monkeypatch.setattr(
        "backend.app.services.stripe_gateway.stripe.checkout.Session.create",
        create_session,
    )
    metadata = {
        "avenqo_kind": "ai_credit_pack",
        "avenqo_company_id": "company-1",
        "avenqo_credit_pack": "professional_extra",
        "avenqo_plan_code": "professional",
        "avenqo_credits": "25000",
    }

    url = StripeGateway("sk_test").create_credit_checkout(
        "cus_company_1",
        "price_credit_professional",
        metadata,
        "https://app.test/success",
        "https://app.test/cancel",
    )

    assert url == "https://checkout.stripe.test/inline"
    assert captured["mode"] == "payment"
    assert captured["adaptive_pricing"] == {"enabled": True}
    assert captured["line_items"] == [
        {"price": "price_credit_professional", "quantity": 1}
    ]
    assert captured["metadata"] == metadata
    assert captured["payment_intent_data"] == {"metadata": metadata}


def test_stripe_subscription_checkout_uses_price_and_adaptive_pricing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def create_session(**kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(url="https://checkout.stripe.test/subscription")

    monkeypatch.setattr(
        "backend.app.services.stripe_gateway.stripe.checkout.Session.create",
        create_session,
    )

    url = StripeGateway("sk_test").create_checkout(
        "cus_company_1",
        "price_professional",
        "company-1",
        "https://app.test/success",
        "https://app.test/cancel",
    )

    assert url == "https://checkout.stripe.test/subscription"
    assert captured["mode"] == "subscription"
    assert captured["line_items"] == [{"price": "price_professional", "quantity": 1}]
    assert captured["adaptive_pricing"] == {"enabled": True}
    assert captured["subscription_data"] == {
        "metadata": {"avenqo_company_id": "company-1"},
    }

def test_factures_sont_isolees_et_webhooks_idempotents(billing_environment) -> None:
    client, provider, notifier = billing_environment
    acme = create_owner(client, notifier)
    nova = create_owner(client, notifier, "owner@nova.ca", "Nova Commerce")
    company_id = acme["company"]["id"]
    paid_event = invoice_event(company_id)
    provider.events.extend([paid_event, paid_event])
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
    invoices = client.get("/api/v1/billing/invoices", headers=auth_headers(acme)).json()
    assert len(invoices) == 1
    assert invoices[0] | {} == {
        **invoices[0],
        "plan_code": "professional",
        "currency": "cad",
        "amount_paid": 6700,
        "status": "paid",
    }
    assert invoices[0]["period_start"] is not None
    assert invoices[0]["period_end"] is not None
    provider.events.append(invoice_event(
        company_id,
        event_id="evt_invoice_failed",
        event_type="invoice.payment_failed",
    ))
    failed = client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid_signature"},
    )
    assert failed.json() == {"processed": True}
    assert client.get("/api/v1/billing/invoices", headers=auth_headers(acme)).json()[0]["status"] == "open"
    assert client.get("/api/v1/billing/invoices", headers=auth_headers(nova)).json() == []
    assert client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "invalid"},
    ).status_code == 400
