"""Guard monthly validation against the real SDK Price resource shape."""
from types import SimpleNamespace

import pytest
import stripe

from backend.app.services.stripe_gateway import StripeGateway


@pytest.mark.parametrize("interval", ["month", "year"])
@pytest.mark.parametrize("plan,amount", [("base", 2999), ("professional", 4999)])
def test_checkout_validates_real_stripe_price_resource(monkeypatch, interval, plan, amount):
    resource = stripe.Price.construct_from(
        {"recurring": {"interval": interval}, "currency": "cad", "unit_amount": amount},
        None,
    )
    monkeypatch.setattr(stripe.Price, "retrieve", lambda *args, **kwargs: resource)
    created = []

    def create(**params):
        created.append(params)
        return SimpleNamespace(url="https://checkout.stripe.com/test-fixture")

    monkeypatch.setattr(stripe.checkout.Session, "create", create)
    gateway = StripeGateway("fixture-not-a-credential")
    args = ("fixture-customer", f"fixture-price-{plan}", "fixture-tenant",
            "http://localhost:3000/billing", "http://localhost:3000/pricing")
    if interval == "year":
        with pytest.raises(ValueError, match="must recur monthly"):
            gateway.create_checkout(*args)
        assert created == []
    else:
        assert gateway.create_checkout(*args) == "https://checkout.stripe.com/test-fixture"
        assert len(created) == 1
        assert created[0]["mode"] == "subscription"

