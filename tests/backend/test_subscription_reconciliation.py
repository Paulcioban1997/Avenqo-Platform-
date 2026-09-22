from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.app.services.subscription_reconciliation import reconcile_subscription
from tests.backend.test_subscription_gate import db_session, _tenant
from backend.app.models import BillingAccount
from sqlalchemy import select


def example():
    account = SimpleNamespace(company_id=uuid4(), stripe_customer_id="cus_own",
        stripe_subscription_id="sub_own", status="inactive", plan_code="demo",
        company=SimpleNamespace(subscription_plan="demo"))
    payload = {"id": "sub_own", "customer": "cus_own", "status": "active",
        "metadata": {"avenqo_company_id": str(account.company_id)},
        "items": {"data": [{"price": {"id": "price_pro"},
            "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=15)).timestamp())}]}}
    settings = SimpleNamespace(stripe_plan_code=lambda value: {"price_pro": "professional", "price_base": "demo"}.get(value))
    return account, payload, settings


@pytest.mark.parametrize("price,plan", [("price_pro", "professional"), ("price_base", "demo")])
def test_verified_subscription_repairs_local_denial(price, plan):
    account, payload, settings = example()
    payload["items"]["data"][0]["price"]["id"] = price
    provider = SimpleNamespace(retrieve_subscription=lambda identifier: payload)
    assert reconcile_subscription(account, provider, settings)
    assert account.status == "active"
    assert account.plan_code == account.company.subscription_plan == plan


@pytest.mark.parametrize("failure", ["customer", "tenant", "id", "price", "status", "expired", "missing_link"])
def test_unverified_subscription_never_grants_access(failure):
    account, payload, settings = example()
    if failure == "customer": payload["customer"] = "cus_other"
    if failure == "tenant": payload["metadata"]["avenqo_company_id"] = str(uuid4())
    if failure == "id": payload["id"] = "sub_other"
    if failure == "price": payload["items"]["data"][0]["price"]["id"] = "unknown"
    if failure == "status": payload["status"] = "unpaid"
    if failure == "expired": payload["items"]["data"][0]["current_period_end"] = 1
    if failure == "missing_link": account.stripe_subscription_id = None
    before = deepcopy(account.__dict__)
    assert not reconcile_subscription(account, SimpleNamespace(retrieve_subscription=lambda identifier: payload), settings)
    assert account.__dict__ == before


def test_gate_persists_verified_plan_for_only_the_current_tenant(db_session, monkeypatch):
    from backend.app.dependencies import subscription as gate
    tenant = _tenant(db_session, plan="demo", subscription_status="inactive")
    other = _tenant(db_session, plan="professional", subscription_status="inactive")
    account = db_session.scalar(select(BillingAccount).where(BillingAccount.company_id == tenant.company_id))
    account.stripe_customer_id = "cus_own"
    account.stripe_subscription_id = "sub_own"
    db_session.commit()
    _, payload, settings = example()
    payload["metadata"]["avenqo_company_id"] = str(tenant.company_id)
    settings.stripe_secret_key = "test-not-a-real-key"
    monkeypatch.setattr(gate, "get_settings", lambda: settings)
    monkeypatch.setattr(gate, "StripeGateway", lambda key: SimpleNamespace(retrieve_subscription=lambda identifier: payload))
    assert gate.require_active_subscription(tenant, db_session) is tenant
    db_session.expire_all()
    assert account.status == "active"
    assert account.plan_code == "professional"
    other_account = db_session.scalar(select(BillingAccount).where(BillingAccount.company_id == other.company_id))
    assert other_account.status == "inactive"
