"""A Voice number is one item on the existing subscription, never a second subscription."""
import stripe
from backend.app.services.stripe_gateway import StripeGateway

class VoiceBillingGateway:
    def __init__(self, settings):
        self.settings = settings
        self.client = stripe.StripeClient(settings.stripe_secret_key or "non-sensitive-disabled-fixture",max_network_retries=0)

    def preview(self, customer, subscription, price_id, proration_date):
        price = self.client.v1.prices.retrieve(price_id).to_dict()
        recurring = price.get("recurring") or {}
        if not price.get("active") or recurring.get("interval") != "month" or recurring.get("interval_count", 1) != 1 or price.get("tax_behavior") != "exclusive" or not isinstance(price.get("unit_amount"), int) or (price.get("metadata") or {}).get("avenqo_kind")!="voice_number":
            raise ValueError("A monthly exclusive-tax fixed Voice price is required")
        sub = self.client.v1.subscriptions.retrieve(subscription).to_dict()
        if sub.get("customer") != customer or sub.get("status") not in {"active", "trialing"} or sub.get("pending_update") or sub.get("collection_method") != "charge_automatically":
            raise ValueError("Subscription ownership, payment method or pending update requires reconciliation")
        items = sub["items"]["data"]
        if any(x["price"]["id"] == price_id for x in items):
            raise ValueError("A Voice add-on already exists")
        amounts = []
        for item in items:
            p = item["price"]
            if p.get("currency") != price["currency"] or not isinstance(p.get("unit_amount"), int) or (p.get("recurring") or {}).get("interval")!="month":
                raise ValueError("A single-currency fixed subscription is required")
            amounts.append(p["unit_amount"] * int(item.get("quantity") or 1))
        tax = StripeGateway(self.settings.stripe_secret_key, automatic_tax_enabled=self.settings.stripe_automatic_tax_enabled)._tax_options()
        args = {"customer": customer, "subscription": subscription, "subscription_details": {
            "items": [{"price": price_id, "quantity": 1}], "proration_behavior": "always_invoice", "proration_date": proration_date}}
        if tax:
            args["automatic_tax"] = tax["automatic_tax"]
        invoice = self.client.v1.invoices.create_preview(params=args).to_dict()
        recurring_args={"customer":customer,"subscription":subscription,"preview_mode":"recurring",
                        "subscription_details":{"items":[{"price":price_id,"quantity":1}],"proration_behavior":"none"}}
        if tax:recurring_args["automatic_tax"]=tax["automatic_tax"]
        renewal=self.client.v1.invoices.create_preview(params=recurring_args).to_dict()
        if tax and any((value.get("automatic_tax") or {}).get("status") != "complete" for value in (invoice, renewal)):
            raise ValueError("Complete tax/address calculation is required")
        return {"currency": price["currency"].upper(), "number_monthly_amount": price["unit_amount"],
                "subscription_monthly_before_tax": sum(amounts), "monthly_total_before_tax": sum(amounts) + price["unit_amount"],
                "monthly_invoice_total":renewal["total"],
                "monthly_tax":sum(x.get("amount",0) for x in renewal.get("total_taxes") or renewal.get("total_tax_amounts") or []),
                "initial_invoice_total": invoice["total"], "initial_amount_due": invoice["amount_due"],
                "initial_tax": sum(x.get("amount", 0) for x in invoice.get("total_taxes") or invoice.get("total_tax_amounts") or []),
                "tax_status": "calculated" if tax else "collection_not_configured", "price_id": price_id,
                "proration_date": proration_date, "subscription_metadata": sub.get("metadata") or {},
                "livemode": bool(price.get("livemode"))}

    def add_number(self, order):
        q = order.snapshot["billing"]
        params = {"items": [{"price": q["price_id"], "quantity": 1}],
                  "payment_behavior": "pending_if_incomplete", "proration_behavior": "always_invoice",
                  "proration_date": q["proration_date"], "expand": ["latest_invoice"],
                  "metadata": {**q["subscription_metadata"], "avenqo_voice_order_id": str(order.id)}}
        sub = self.client.v1.subscriptions.update(order.stripe_subscription_id, params=params,
                    options={"idempotency_key": f"voice-bill:{order.id}"}).to_dict()
        invoice = sub.get("latest_invoice")
        if isinstance(invoice, str):
            invoice = self.client.v1.invoices.retrieve(invoice).to_dict()
        if not isinstance(invoice, dict) or not invoice.get("id"):
            raise ValueError("Stripe invoice is unavailable; billing outcome must be reconciled")
        return invoice

    def invoice(self, invoice_id):
        return self.client.v1.invoices.retrieve(invoice_id, params={"expand": ["lines.data"]}).to_dict()

    def subscription(self, subscription_id):
        return self.client.v1.subscriptions.retrieve(subscription_id, params={"expand": ["latest_invoice"]}).to_dict()

    def compensate(self, order, *, refund=True):
        """Remove only this add-on and refund only its initial invoice payment."""
        sub = self.subscription(order.stripe_subscription_id)
        if sub.get("customer")!=order.stripe_customer_id or (sub.get("metadata") or {}).get("avenqo_voice_order_id")!=str(order.id):
            raise ValueError("Billing compensation ownership cannot be confirmed")
        items = [x for x in sub["items"]["data"] if x["price"]["id"] == order.snapshot["billing"]["price_id"]]
        if len(items) > 1:
            raise ValueError("Ambiguous add-on requires reconciliation")
        if items:
            self.client.v1.subscription_items.delete(items[0]["id"], params={"proration_behavior": "none"})
        if not refund:
            return
        # A credit note is invoice-scoped and cannot refund another tenant/payment.
        if order.stripe_invoice_id:
            invoice = self.invoice(order.stripe_invoice_id)
            if invoice.get("status") == "draft":
                self.client.v1.invoices.delete(invoice["id"])
                return
            if invoice.get("status") == "open":
                self.client.v1.invoices.void_invoice(invoice["id"])
                return
            if invoice.get("status")!="paid" or order.snapshot["billing"]["initial_amount_due"]<=0:return
            lines = [{"type": "invoice_line_item", "invoice_line_item": x["id"], "quantity": 1}
                     for x in invoice["lines"]["data"] if line_price(x) == order.snapshot["billing"]["price_id"]]
            if not lines:
                raise ValueError("Voice invoice lines cannot be reconciled")
            credit = self.client.v1.credit_notes.preview(params={"invoice": invoice["id"], "lines": lines}).to_dict()
            self.client.v1.credit_notes.create(params={"invoice": invoice["id"], "lines": lines,
                "refund_amount": credit["amount"]},
                options={"idempotency_key": f"voice-compensation:{order.id}"})

def line_price(line):
    price = line.get("price") or (line.get("pricing") or {}).get("price_details", {}).get("price")
    return price.get("id") if isinstance(price, dict) else price
