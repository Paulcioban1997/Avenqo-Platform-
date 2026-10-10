"""Adaptateur Stripe isolÃ© des cas d'usage de facturation Avenqo."""

from dataclasses import dataclass
from typing import Any, Protocol

import stripe


class StripeTaxConfigurationError(RuntimeError):
    """Requested tax collection is not configured; do not silently collect zero."""


@dataclass(frozen=True, slots=True)
class CreditCheckoutSession:
    id: str
    url: str


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
    ) -> CreditCheckoutSession: ...
    def list_customer_invoices(self, customer_id: str, *, limit: int = 100) -> list[dict[str, Any]]: ...
    def change_subscription(self, subscription_id: str, price_id: str) -> None: ...
    def cancel_subscription(self, subscription_id: str) -> None: ...
    def create_portal(self, customer_id: str, return_url: str) -> str: ...
    def construct_event(self, payload: bytes, signature: str, secret: str) -> dict[str, Any]: ...


class StripeGateway:
    """Traduit les opÃ©rations Avenqo vers le SDK officiel Stripe."""

    def __init__(self, api_key: str, *, automatic_tax_enabled: bool = False) -> None:
        self._api_key = api_key
        self._automatic_tax_enabled = automatic_tax_enabled

    def _tax_options(self) -> dict[str, Any]:
        if not self._automatic_tax_enabled:
            return {}
        client = stripe.StripeClient(self._api_key)
        try:
            tax_settings = client.v1.tax.settings.retrieve().to_dict()
            registrations = client.v1.tax.registrations.list(params={"status": "active", "limit": 100})
        except stripe.StripeError as exc:
            raise StripeTaxConfigurationError("Impossible de vérifier la configuration Stripe Tax ; aucun paiement créé.") from exc
        if tax_settings.get("status") != "active" or not registrations.data:
            raise StripeTaxConfigurationError("Stripe Tax exige une adresse fiscale et une inscription active avant la collecte.")
        if not (tax_settings.get("defaults") or {}).get("tax_code"):
            raise StripeTaxConfigurationError("La classification fiscale du service Avenqo doit être configurée dans Stripe Tax.")
        if (tax_settings.get("defaults") or {}).get("tax_behavior") != "exclusive":
            raise StripeTaxConfigurationError("Les tarifs hors taxes exigent un comportement fiscal exclusif dans Stripe Tax.")
        return {"automatic_tax": {"enabled": True}, "billing_address_collection": "required",
                "customer_update": {"address": "auto", "name": "auto"}, "tax_id_collection": {"enabled": True}}

    def enrich_invoice_taxes(self, invoice: dict[str, Any]) -> dict[str, Any]:
        client = stripe.StripeClient(self._api_key)
        cache = {}
        for tax in invoice.get("total_taxes") or invoice.get("total_tax_amounts") or []:
            rate = (tax.get("tax_rate_details") or {}).get("tax_rate") or tax.get("tax_rate")
            if isinstance(rate, str):
                if rate not in cache:
                    try:
                        cache[rate] = client.v1.tax_rates.retrieve(rate).to_dict()
                    except stripe.StripeError:
                        cache[rate] = {}  # Amount persists even if the descriptive lookup is unavailable.
                tax["_avenqo_tax_rate"] = cache[rate]
        return invoice

    def _require_monthly_price(self, price_id: str) -> None:
        price = (stripe.StripeClient(self._api_key).v1.prices.retrieve(price_id).to_dict()
                 if self._automatic_tax_enabled else stripe.Price.retrieve(price_id, api_key=self._api_key))
        recurring = price.get("recurring") if hasattr(price, "get") else None
        if not recurring or recurring.get("interval") != "month":
            raise ValueError("Avenqo subscription prices must recur monthly")
        if self._automatic_tax_enabled and price.get("tax_behavior") == "inclusive":
            raise StripeTaxConfigurationError("Ce tarif Stripe inclut les taxes ; utilisez un nouveau tarif hors taxes.")

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
        self._require_monthly_price(price_id)
        tax_options = self._tax_options()
        params = dict(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            client_reference_id=company_id,
            subscription_data={"metadata": {"avenqo_company_id": company_id}},
            adaptive_pricing={"enabled": False},
            success_url=success_url,
            cancel_url=cancel_url,
            **tax_options,
        )
        checkout = (stripe.StripeClient(self._api_key).v1.checkout.sessions.create(params=params)
                    if tax_options else stripe.checkout.Session.create(**params, api_key=self._api_key))
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
    ) -> CreditCheckoutSession:
        from payments.plans import get_ai_credit_pack
        client = stripe.StripeClient(self._api_key)
        if "avenqo_price_cents" in metadata:
            amount = int(metadata["avenqo_price_cents"])
            if amount <= 0 or int(metadata["avenqo_credits"]) <= 0:
                raise ValueError("Positive credit pack terms required")
            line_item = {"price_data": {"currency": "cad", "unit_amount": amount,
                "tax_behavior": "exclusive", "product_data": {"name": metadata["avenqo_pack_name"] + " - " + metadata["avenqo_credits"] + " crédits IA"}}, "quantity": 1}
        else:
            pack = get_ai_credit_pack(metadata["avenqo_credit_pack"])
            price = client.v1.prices.retrieve(price_id)
            product = price["product"]
            if not isinstance(product, str) or price["recurring"]:
                raise ValueError("A one-time credit product is required")
            amount = pack.price_cad * 100
            line_item = {"price": price_id, "quantity": 1} if (
                price["currency"] == "cad" and price["unit_amount"] == amount
            ) else {"price_data": {"currency": "cad", "unit_amount": amount, "product": product}, "quantity": 1}
        checkout = client.v1.checkout.sessions.create(params=dict(
            mode="payment",
            customer=customer_id,
            currency="cad",
            line_items=[line_item],
            metadata=metadata,
            payment_intent_data={"metadata": metadata},
            invoice_creation={
                "enabled": True,
                "invoice_data": {"metadata": metadata},
            },
            adaptive_pricing={"enabled": False},
            success_url=success_url,
            cancel_url=cancel_url,
            **self._tax_options(),
        ))
        if not checkout.url:
            raise RuntimeError("Stripe n'a pas retourné d'URL Checkout")
        return CreditCheckoutSession(id=str(checkout.id), url=str(checkout.url))

    def list_customer_invoices(self, customer_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        """Retourne les factures Stripe du Customer courant, jamais celles d'un autre tenant."""
        result = stripe.Invoice.list(
            customer=customer_id,
            limit=min(max(limit, 1), 100),
            api_key=self._api_key,
        )
        invoices: list[dict[str, Any]] = []
        for invoice in result.data:
            if hasattr(invoice, "to_dict_recursive"):
                invoices.append(invoice.to_dict_recursive())
            elif hasattr(invoice, "to_dict"):
                invoices.append(invoice.to_dict())
            else:
                invoices.append(dict(invoice))
        return [self.enrich_invoice_taxes(invoice) for invoice in invoices]

    def change_subscription(self, subscription_id: str, price_id: str) -> None:
        self._require_monthly_price(price_id)
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
