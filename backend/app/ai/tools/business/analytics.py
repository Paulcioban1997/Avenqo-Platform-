"""Agrégations business en lecture seule, calculées sur `PreparedCompanyDataset`.

Aucune donnée fictive : tout est calculé depuis les lignes réelles du
tenant (Phase 26/27). Aucun entraînement de modèle n'est déclenché ici.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from shared.ai_engine.dataset_ingestion.prepared_dataset import PreparedCompanyDataset

TOP_PRODUCTS_METRICS = ("revenue", "quantity", "orders")


def _reverse_mapping(canonical_columns: dict[str, str]) -> dict[str, str]:
    return {canonical: original for original, canonical in canonical_columns.items()}


def _value(row: dict[str, object], reverse: dict[str, str], field: str) -> object | None:
    original = reverse.get(field)
    if original is None or original not in row:
        return None
    return row[original]


def _as_float(value: object | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _as_datetime(value: object | None) -> datetime | None:
    if value is None or not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def filter_rows_by_date(
    rows: tuple[dict[str, object], ...],
    reverse: dict[str, str],
    date_from: datetime | None,
    date_to: datetime | None,
) -> tuple[dict[str, object], ...]:
    if date_from is None and date_to is None:
        return rows
    filtered = []
    for row in rows:
        timestamp = _as_datetime(_value(row, reverse, "order_timestamp"))
        if timestamp is None:
            continue
        if date_from is not None and timestamp < date_from:
            continue
        if date_to is not None and timestamp > date_to:
            continue
        filtered.append(row)
    return tuple(filtered)


def compute_business_overview(prepared: PreparedCompanyDataset) -> dict[str, object]:
    reverse = _reverse_mapping(prepared.canonical_columns)
    revenue = 0.0
    order_ids: set[object] = set()
    customer_ids: set[object] = set()
    timestamps: list[datetime] = []

    for row in prepared.rows:
        amount = _as_float(_value(row, reverse, "total_amount"))
        if amount is not None:
            revenue += amount
        order_id = _value(row, reverse, "order_id")
        if order_id is not None:
            order_ids.add(order_id)
        customer_id = _value(row, reverse, "customer_id")
        if customer_id is not None:
            customer_ids.add(customer_id)
        timestamp = _as_datetime(_value(row, reverse, "order_timestamp"))
        if timestamp is not None:
            timestamps.append(timestamp)

    orders = len(order_ids) if order_ids else len(prepared.rows)
    period = None
    if timestamps:
        period = min(timestamps).strftime("%Y-%m") if len(set(t.strftime("%Y-%m") for t in timestamps)) == 1 else f"{min(timestamps).strftime('%Y-%m-%d')} to {max(timestamps).strftime('%Y-%m-%d')}"

    return {
        "period": period,
        "revenue": round(revenue, 2),
        "orders": orders,
        "customers": len(customer_ids),
        "average_order_value": round(revenue / orders, 2) if orders else 0.0,
    }


def compute_sales_summary(
    prepared: PreparedCompanyDataset,
    *,
    date_from: datetime | None,
    date_to: datetime | None,
    product: str | None,
) -> dict[str, object]:
    reverse = _reverse_mapping(prepared.canonical_columns)
    rows = filter_rows_by_date(prepared.rows, reverse, date_from, date_to)
    if product is not None:
        rows = tuple(
            row for row in rows if str(_value(row, reverse, "product_id") or "") == product
        )

    revenue = 0.0
    order_ids: set[object] = set()
    for row in rows:
        amount = _as_float(_value(row, reverse, "total_amount"))
        if amount is not None:
            revenue += amount
        order_id = _value(row, reverse, "order_id")
        if order_id is not None:
            order_ids.add(order_id)

    orders = len(order_ids) if order_ids else len(rows)
    return {
        "revenue": round(revenue, 2),
        "orders": orders,
        "average_order_value": round(revenue / orders, 2) if orders else 0.0,
        "rows_considered": len(rows),
    }


def compute_sales_trend(prepared: PreparedCompanyDataset) -> dict[str, object]:
    reverse = _reverse_mapping(prepared.canonical_columns)
    revenue_by_month: dict[str, float] = defaultdict(float)

    for row in prepared.rows:
        timestamp = _as_datetime(_value(row, reverse, "order_timestamp"))
        if timestamp is None:
            continue
        amount = _as_float(_value(row, reverse, "total_amount")) or 0.0
        revenue_by_month[timestamp.strftime("%Y-%m")] += amount

    points = [
        {"period": period, "revenue": round(revenue, 2)}
        for period, revenue in sorted(revenue_by_month.items())
    ]
    return {"granularity": "month", "points": points}


def compute_sales_comparison(
    prepared: PreparedCompanyDataset,
    *,
    current_from: datetime,
    current_to: datetime,
    previous_from: datetime,
    previous_to: datetime,
) -> dict[str, object]:
    reverse = _reverse_mapping(prepared.canonical_columns)

    def revenue_between(start: datetime, end: datetime) -> float:
        rows = filter_rows_by_date(prepared.rows, reverse, start, end)
        return sum(_as_float(_value(row, reverse, "total_amount")) or 0.0 for row in rows)

    current = revenue_between(current_from, current_to)
    previous = revenue_between(previous_from, previous_to)
    absolute_change = current - previous
    percentage_change = round((absolute_change / previous) * 100, 2) if previous else None

    return {
        "current": round(current, 2),
        "previous": round(previous, 2),
        "absolute_change": round(absolute_change, 2),
        "percentage_change": percentage_change,
    }


def compute_top_products(
    prepared: PreparedCompanyDataset,
    *,
    top_n: int,
    metric: str,
    date_from: datetime | None,
    date_to: datetime | None,
) -> dict[str, object]:
    reverse = _reverse_mapping(prepared.canonical_columns)
    rows = filter_rows_by_date(prepared.rows, reverse, date_from, date_to)

    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        product_id = _value(row, reverse, "product_id")
        if product_id is None:
            continue
        product_key = str(product_id)
        if metric == "revenue":
            totals[product_key] += _as_float(_value(row, reverse, "total_amount")) or 0.0
        elif metric == "quantity":
            totals[product_key] += _as_float(_value(row, reverse, "quantity")) or 0.0
        else:  # "orders"
            totals[product_key] += 1

    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:top_n]
    return {
        "metric": metric,
        "products": [
            {"product_id": product_id, "value": round(value, 2)} for product_id, value in ranked
        ],
    }


def compute_customer_summary(prepared: PreparedCompanyDataset) -> dict[str, object]:
    reverse = _reverse_mapping(prepared.canonical_columns)
    orders_by_customer: dict[str, int] = defaultdict(int)

    for row in prepared.rows:
        customer_id = _value(row, reverse, "customer_id")
        if customer_id is None:
            continue
        orders_by_customer[str(customer_id)] += 1

    total_customers = len(orders_by_customer)
    returning_customers = sum(1 for count in orders_by_customer.values() if count > 1)
    new_customers = total_customers - returning_customers

    return {
        "total_customers": total_customers,
        "returning_customers": returning_customers,
        "new_customers": new_customers,
        "average_orders_per_customer": round(sum(orders_by_customer.values()) / total_customers, 2)
        if total_customers
        else 0.0,
    }
