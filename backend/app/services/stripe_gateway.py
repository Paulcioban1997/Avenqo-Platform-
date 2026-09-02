"""Adaptateur Stripe isolÃ© des cas d'usage de facturation Avenqo."""

from typing import Any, Protocol

import stripe


class BillingProvider(Protocol):
    def create_customer(self, email: str, name: str, company_id: str) -> str: ...
    def create_checkout(
        self,
        customer_id: str,
        price_id: str,
        company_id: str,
        success_url: str,
        cancel_url: str,
    ) -> str: ...
    def create_credit_checkout(
        self,
        customer_id: str,
        price_id: str,
        metadata: dict[str, str],
        success_url: str,
        cancel_url: str,
    ) -> str: ...
    def change_subscription(self, subscription_id: str, price_id: str) -> None: ...
    def cancel_subscription(self, subscription_id: str) -> None: ...
    def create_portal(self, customer_id: str, return_url: str) -> str: ...
    def construct_event(self, payload: bytes, signature: str, secret: str) -> dict[str, Any]: ...


class StripeGateway:
    """Traduit les opÃ©rations Avenqo vers le SDK officiel Stripe."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def create_customer(self, email: str, name: str, company_id: str) -> str:
        customer = stripe.Customer.create(
            email=email,
            name=name,
            metadata={"avenqo_company_id": company_id},
            api_key=self._api_key,
        )
        return customer.id

    def create_checkout(
        self,
        customer_id: str,
        price_id: str,
        company_id: str,
        success_url: str,
        cancel_url: str,
    ) -> str:
        checkout = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            client_reference_id=company_id,
            subscription_data={"metadata": {"avenqo_company_id": company_id}},
            adaptive_pricing={"enabled": True},
            success_url=success_url,
            cancel_url=cancel_url,
            api_key=self._api_key,
        )
        if not checkout.url:
            raise RuntimeError("Stripe n'a pas retournÃ© d'URL Checkout")
        return checkout.url

    def create_credit_checkout(
        self,
        customer_id: str,
        price_id: str,
        metadata: dict[str, str],
        success_url: str,
        cancel_url: str,
    ) -> str:
        checkout = stripe.checkout.Session.create(
            mode="payment",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            metadata=metadata,
            payment_intent_data={"metadata": metadata},
            adaptive_pricing={"enabled": True},
            success_url=success_url,
            cancel_url=cancel_url,
            api_key=self._api_key,
        )
        if not checkout.url:
            raise RuntimeError("Stripe n'a pas retourné d'URL Checkout")
        return checkout.url

    def change_subscription(self, subscription_id: str, price_id: str) -> None:
        subscription = stripe.Subscription.retrieve(subscription_id, api_key=self._api_key)
        stripe.Subscription.modify(
            subscription_id,
            items=[{"id": subscription["items"]["data"][0]["id"], "price": price_id}],
            proration_behavior="create_prorations",
            api_key=self._api_key,
        )

    def cancel_subscription(self, subscription_id: str) -> None:
        stripe.Subscription.modify(
            subscription_id,
            cancel_at_period_end=True,
            api_key=self._api_key,
        )

    def create_portal(self, customer_id: str, return_url: str) -> str:
        portal = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
            api_key=self._api_key,
        )
        return portal.url

    def construct_event(self, payload: bytes, signature: str, secret: str) -> dict[str, Any]:
        return stripe.Webhook.construct_event(payload, signature, secret)
