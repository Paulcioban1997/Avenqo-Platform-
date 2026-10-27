from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.routing import APIRoute

from backend.app.routers.billing import _plan_display_price, subscription_response
from backend.app.routers.crm import get_crm_kpis, get_crm_summary, router as crm_router
from backend.app.routers.retail import _inventory_anomalies, _sales_operational_anomalies
from backend.app.services.billing_service import BillingService
from payments.plans import get_plan


def test_crm_summary_is_not_aliased_to_kpis() -> None:
    kpis = [
        route
        for route in crm_router.routes
        if isinstance(route, APIRoute) and route.endpoint is get_crm_kpis
    ]
    summary = [
        route
        for route in crm_router.routes
        if isinstance(route, APIRoute) and route.endpoint is get_crm_summary
    ]
    assert len(kpis) == 1
    assert len(summary) == 1
    assert kpis[0].path.rstrip("/").endswith("/kpis")
    assert summary[0].path.rstrip("/").endswith("/summary")
    assert kpis[0].endpoint is not summary[0].endpoint


def test_cad_subscription_price_uses_cad_catalog_not_usd() -> None:
    plan = get_plan("base")
    usd, cad_display = _plan_display_price(plan, "CAD")
    assert usd == 21.99
    assert cad_display == 29.99
    response = subscription_response(
        SimpleNamespace(
            plan_code="base",
            status="active",
            stripe_subscription_id=None,
            current_period_end=None,
            cancel_at_period_end=False,
        ),
        SimpleNamespace(name="Boutique", currency_code="CAD"),
    )
    assert response.monthly_price == 29.99
    assert response.currency == "CAD"


def test_credit_packs_are_unique_by_credits_and_never_free() -> None:
    packs = BillingService._unique_credit_packs(
        [
            {"code": "credits_6500", "credits": 6500, "price_cents": 1000},
            {"code": "demo_extra", "credits": 6500, "price_cents": 1000},
            {"code": "zero", "credits": 1000, "price_cents": 0},
            {"code": "credits_25000", "credits": 25000, "price_cents": 3500},
        ]
    )
    assert [pack["code"] for pack in packs] == ["credits_6500", "credits_25000"]


def test_small_catalog_reports_low_stock_anomaly() -> None:
    anomalies, state, sample = _inventory_anomalies(
        [
            {
                "id": "sku-1",
                "product_name": "Avenqo Headphones X",
                "sku": "AHX",
                "stock_quantity": 4,
            }
        ],
        source={"provider": "woocommerce", "name": "boutique-woo"},
        population_complete=True,
    )
    assert sample == 1
    assert state == "detected"
    assert anomalies[0]["type"] == "low_stock"
    assert anomalies[0]["source"]["provider"] == "woocommerce"
    assert "superstore" not in str(anomalies).lower()


def test_sales_operational_anomalies_use_real_revenue_drops() -> None:
    anomalies = _sales_operational_anomalies(
        [
            {
                "product_id": "p-1",
                "name": "Binders",
                "sku": "BIN",
                "current_revenue": 0,
                "previous_revenue": 420,
                "change_percent": -100,
            },
            {
                "product_id": "p-2",
                "name": "Phones",
                "sku": "PHN",
                "current_revenue": 80,
                "previous_revenue": 200,
                "change_percent": -60,
            },
            {
                "product_id": "p-3",
                "name": "Stable chairs",
                "sku": "CHR",
                "current_revenue": 190,
                "previous_revenue": 200,
                "change_percent": -5,
            },
        ],
        source={"selection": "dataset", "name": "Superstore-utf8.csv"},
        detected_at=datetime(2026, 10, 14, tzinfo=timezone.utc),
    )
    types = {item["type"] for item in anomalies}
    assert types == {"sales_drop", "sales_decline"}
    assert {item["sku"] for item in anomalies} == {"BIN", "PHN"}
    assert all(item["metric"] == "product_revenue" for item in anomalies)
