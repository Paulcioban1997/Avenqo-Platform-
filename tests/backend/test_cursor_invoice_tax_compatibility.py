from backend.app.services.invoice_tax import invoice_tax_snapshot


def test_modern_tax_components_preserve_actual_amounts_and_rates() -> None:
    invoice = {
        "total_taxes": [
            {
                "amount": 150,
                "taxable_amount": 2999,
                "tax_behavior": "exclusive",
                "tax_rate_details": {"tax_rate": "txr_gst"},
                "_avenqo_tax_rate": {"tax_type": "gst", "percentage": 5.0, "country": "CA"},
                "taxability_reason": "standard_rated",
            },
            {
                "amount": 299,
                "tax_rate_details": {"tax_rate": "txr_qst"},
                "_avenqo_tax_rate": {"tax_type": "qst", "percentage": 9.975, "state": "QC"},
            },
        ]
    }
    rows = invoice_tax_snapshot(invoice)
    assert sum(row["amount"] for row in rows) == 449
    assert [row["name"] for row in rows] == ["TPS", "TVQ"]
    assert rows[1]["percentage"] == 9.975
    assert rows[0]["taxable_amount"] == 2999


def test_legacy_tax_amounts_still_count_without_inventing_names() -> None:
    rows = invoice_tax_snapshot({"total_tax_amounts": [{"amount": 700}]})
    assert rows == [
        {
            "name": "Taxe Stripe",
            "rate_id": None,
            "percentage": None,
            "amount": 700,
            "taxable_amount": None,
            "country": None,
            "state": None,
            "inclusive": False,
            "reason": None,
        }
    ]


def test_missing_tax_components_do_not_invent_taxes() -> None:
    assert invoice_tax_snapshot({
        "total": 2999,
        "customer_address": {"country": "CA", "state": "QC"},
    }) == []
    zero_rated = invoice_tax_snapshot({
        "total_tax_amounts": [{"amount": 0, "tax_rate": {"display_name": "Exonérée", "percentage": 0}}],
    })
    assert zero_rated[0]["percentage"] == 0
    assert zero_rated[0]["amount"] == 0
