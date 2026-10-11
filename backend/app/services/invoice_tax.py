"""Persist Stripe's actual tax components; never infer tax from the customer's country."""

from typing import Any


def invoice_tax_components(invoice: dict[str, Any]) -> list[dict[str, Any]]:
    """Return Stripe tax rows from modern (`total_taxes`) or legacy payloads."""

    return invoice.get("total_taxes") or invoice.get("total_tax_amounts") or []


def invoice_tax_snapshot(invoice: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in invoice_tax_components(invoice):
        details = item.get("tax_rate_details") or {}
        rate = item.get("_avenqo_tax_rate") or item.get("tax_rate") or {}
        rate_id = details.get("tax_rate") or (rate if isinstance(rate, str) else rate.get("id"))
        if not isinstance(rate, dict):
            rate = {}
        tax_type = rate.get("tax_type") or ""
        label = {
            "gst": "TPS",
            "hst": "TVH",
            "qst": "TVQ",
            "pst": "Taxe provinciale",
        }.get(tax_type)
        percentage = (
            rate.get("effective_percentage")
            if rate.get("effective_percentage") is not None
            else rate.get("percentage")
        )
        rows.append(
            {
                "name": label or rate.get("display_name") or "Taxe Stripe",
                "rate_id": rate_id,
                "percentage": percentage,
                "amount": int(item.get("amount", 0)),
                "taxable_amount": item.get("taxable_amount"),
                "country": rate.get("country"),
                "state": rate.get("state"),
                "inclusive": item.get("tax_behavior") == "inclusive" or rate.get("inclusive", False),
                "reason": item.get("taxability_reason"),
            }
        )
    return rows
