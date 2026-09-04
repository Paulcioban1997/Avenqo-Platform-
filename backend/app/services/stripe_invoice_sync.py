"""Synchronisation ciblée des factures Stripe vers l'historique local Avenqo.

Cette synchronisation est volontairement sans notification email : elle sert à
rattraper les factures déjà existantes chez Stripe lorsqu'un webhook historique
n'a pas été persisté localement. Les nouveaux webhooks restent gérés par
BillingService.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings
from backend.app.models import BillingAccount, BillingInvoice
from backend.app.services.stripe_gateway import BillingProvider


def _stripe_datetime(value: object) -> datetime | None:
    return datetime.fromtimestamp(int(value), timezone.utc) if value else None


def _line_snapshot(line: dict[str, Any]) -> dict[str, Any]:
    legacy_price = line.get("price") or {}
    pricing = line.get("pricing") or {}
    price_details = pricing.get("price_details") or {}
    return {
        "description": line.get("description"),
        "quantity": line.get("quantity"),
        "amount": int(line.get("amount", 0)),
        "currency": line.get("currency"),
        "price_id": legacy_price.get("id") or price_details.get("price"),
        "product_id": legacy_price.get("product") or price_details.get("product"),
    }


def sync_customer_invoices(
    db: Session,
    provider: BillingProvider,
    settings: Settings,
    company_id: UUID,
) -> int:
    """Backfill/upsert les factures Stripe du Customer du tenant courant.

    Aucun email n'est envoyé ici : les factures historiques deviennent seulement
    visibles dans l'espace Facturation. Le customer Stripe est résolu depuis le
    BillingAccount du même company_id, ce qui maintient l'isolation multi-tenant.
    """
    account = db.scalar(
        select(BillingAccount).where(BillingAccount.company_id == company_id)
    )
    if account is None or not account.stripe_customer_id:
        return 0

    synced = 0
    for invoice in provider.list_customer_invoices(account.stripe_customer_id, limit=100):
        if str(invoice.get("customer") or "") != account.stripe_customer_id:
            continue

        stripe_invoice_id = str(invoice.get("id") or "")
        if not stripe_invoice_id:
            continue

        existing = db.scalar(
            select(BillingInvoice).where(
                BillingInvoice.stripe_invoice_id == stripe_invoice_id
            )
        )
        lines = (invoice.get("lines") or {}).get("data") or []
        first_line = lines[0] if lines else {}
        period = first_line.get("period") or {}

        legacy_price = first_line.get("price") or {}
        pricing = first_line.get("pricing") or {}
        price_details = pricing.get("price_details") or {}
        price_id = str(
            legacy_price.get("id") or price_details.get("price") or ""
        )
        plan_code = settings.stripe_plan_code(price_id) or account.plan_code

        parent = invoice.get("parent") or {}
        subscription_details = parent.get("subscription_details") or {}
        subscription_id = (
            subscription_details.get("subscription")
            or invoice.get("subscription")
            or account.stripe_subscription_id
        )
        discounts = invoice.get("total_discount_amounts") or []
        taxes = invoice.get("total_tax_amounts") or invoice.get("total_taxes") or []
        status_transitions = invoice.get("status_transitions") or {}

        issued_at = _stripe_datetime(invoice.get("created")) or datetime.now(timezone.utc)
        values = {
            "company_id": company_id,
            "stripe_subscription_id": str(subscription_id) if subscription_id else None,
            "stripe_customer_id": account.stripe_customer_id,
            "number": invoice.get("number"),
            "plan_code": plan_code,
            "status": str(invoice.get("status") or "unknown"),
            "currency": str(invoice.get("currency") or "usd"),
            "subtotal": int(invoice.get("subtotal", 0)),
            "discount_total": sum(int(item.get("amount", 0)) for item in discounts),
            "tax_total": sum(int(item.get("amount", 0)) for item in taxes),
            "total": int(invoice.get("total", invoice.get("amount_due", 0))),
            "amount_due": int(invoice.get("amount_due", 0)),
            "amount_paid": int(invoice.get("amount_paid", 0)),
            "line_items": [_line_snapshot(item) for item in lines],
            "billing_details": {
                "name": invoice.get("customer_name"),
                "address": invoice.get("customer_address"),
                "phone": invoice.get("customer_phone"),
            },
            "tax_identifiers": invoice.get("customer_tax_ids") or [],
            "customer_email": invoice.get("customer_email"),
            "hosted_invoice_url": invoice.get("hosted_invoice_url"),
            "invoice_pdf": invoice.get("invoice_pdf"),
            "period_start": _stripe_datetime(period.get("start")),
            "period_end": _stripe_datetime(period.get("end")),
            "issued_at": issued_at,
            "paid_at": _stripe_datetime(status_transitions.get("paid_at")),
            "due_at": _stripe_datetime(invoice.get("due_date")),
        }

        if existing is None:
            existing = BillingInvoice(
                stripe_invoice_id=stripe_invoice_id,
                **values,
            )
            db.add(existing)
        else:
            for field, value in values.items():
                setattr(existing, field, value)
        synced += 1

    if synced:
        db.commit()
    return synced
