"""Agrégations business en lecture seule, calculées sur `PreparedCompanyDataset`.

Aucune donnée fictive : tout est calculé depuis les lignes réelles du
tenant (Phase 26/27). Aucun entraînement de modèle n'est déclenché ici.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

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
        product_field = "product_id" if "product_id" in reverse else "product_name"
        rows = tuple(
            row for row in rows if str(_value(row, reverse, product_field) or "") == product
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


def compute_sales_trend(
    prepared: PreparedCompanyDataset,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    granularity: str = "month",
    product: str | None = None,
) -> dict[str, object]:
    reverse = _reverse_mapping(prepared.canonical_columns)
    rows = filter_rows_by_date(prepared.rows, reverse, date_from, date_to)
    if product is not None:
        product_field = "product_id" if "product_id" in reverse else "product_name"
        rows = tuple(
            row for row in rows if str(_value(row, reverse, product_field) or "") == product
        )
    revenue_by_period: dict[str, float] = defaultdict(float)
    orders_by_period: dict[str, set[object]] = defaultdict(set)
    row_count_by_period: dict[str, int] = defaultdict(int)

    for row in rows:
        timestamp = _as_datetime(_value(row, reverse, "order_timestamp"))
        if timestamp is None:
            continue
        if granularity == "day":
            period = timestamp.strftime("%Y-%m-%d")
        elif granularity == "week":
            period = (timestamp - timedelta(days=timestamp.weekday())).strftime("%Y-%m-%d")
        else:
            period = timestamp.strftime("%Y-%m")
        amount = _as_float(_value(row, reverse, "total_amount")) or 0.0
        revenue_by_period[period] += amount
        order_id = _value(row, reverse, "order_id")
        if order_id is not None:
            orders_by_period[period].add(order_id)
        row_count_by_period[period] += 1

    points = [
        {
            "period": period,
            "revenue": round(revenue, 2),
            "orders": len(orders_by_period[period]) or row_count_by_period[period],
        }
        for period, revenue in sorted(revenue_by_period.items())
    ]
    return {"granularity": granularity, "points": points}


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


def compute_product_portfolio(
    prepared: PreparedCompanyDataset,
) -> list[dict[str, object]]:
    """Aggregate safe product entities while reusing the shared sales formula."""

    reverse = _reverse_mapping(prepared.canonical_columns)
    entity_field = "product_id" if "product_id" in reverse else "product_name"
    if entity_field not in reverse:
        return []

    by_product: dict[str, dict[str, object]] = {}
    for row_index, row in enumerate(prepared.rows):
        raw_entity = _value(row, reverse, entity_field)
        if raw_entity is None:
            continue
        product_id = str(raw_entity)
        product = by_product.setdefault(
            product_id,
            {
                "product_id": product_id,
                "name": None,
                "category": None,
                "quantity": 0.0 if "quantity" in reverse else None,
                "customer_ids": set(),
                "last_activity": None,
                "latest_row_index": -1,
                "stock_level": None,
            },
        )
        name = _value(row, reverse, "product_name")
        if name is not None:
            product["name"] = str(name)
        category = _value(row, reverse, "product_category")
        if category is not None:
            product["category"] = str(category)
        quantity = _as_float(_value(row, reverse, "quantity"))
        if quantity is not None and product["quantity"] is not None:
            product["quantity"] = float(product["quantity"]) + quantity
        customer_id = _value(row, reverse, "customer_id")
        if customer_id is not None:
            customer_ids = product["customer_ids"]
            assert isinstance(customer_ids, set)
            customer_ids.add(customer_id)
        timestamp = _as_datetime(_value(row, reverse, "order_timestamp"))
        last_activity = product["last_activity"]
        if timestamp is not None and (
            last_activity is None or timestamp >= last_activity
        ):
            product["last_activity"] = timestamp
            product["latest_row_index"] = row_index
            stock = _as_float(_value(row, reverse, "inventory_level"))
            if stock is not None:
                product["stock_level"] = stock
        elif timestamp is None and int(product["latest_row_index"]) < row_index:
            product["latest_row_index"] = row_index
            stock = _as_float(_value(row, reverse, "inventory_level"))
            if stock is not None:
                product["stock_level"] = stock

    has_revenue = "total_amount" in reverse
    has_unit_price = "unit_price" in reverse
    result: list[dict[str, object]] = []
    for product in by_product.values():
        product_id = str(product["product_id"])
        sales = compute_sales_summary(
            prepared,
            date_from=None,
            date_to=None,
            product=product_id,
        )
        quantity = product["quantity"]
        revenue = float(sales["revenue"]) if has_revenue else None
        average_price = (
            round(revenue / float(quantity), 2)
            if revenue is not None and quantity not in {None, 0, 0.0}
            else None
        )
        if average_price is None and has_unit_price:
            prices = [
                price
                for row in prepared.rows
                if str(_value(row, reverse, entity_field) or "") == product_id
                if (price := _as_float(_value(row, reverse, "unit_price"))) is not None
            ]
            average_price = round(sum(prices) / len(prices), 2) if prices else None
        customer_ids = product.pop("customer_ids")
        product.pop("latest_row_index")
        assert isinstance(customer_ids, set)
        product.update(
            {
                "revenue": revenue,
                "orders": int(sales["orders"]),
                "average_price": average_price,
                "customer_reach": len(customer_ids) if "customer_id" in reverse else None,
            }
        )
        if quantity is not None:
            product["quantity"] = round(float(quantity), 2)
        result.append(product)
    return result


def compute_customer_summary(prepared: PreparedCompanyDataset) -> dict[str, object]:
    customers = compute_customer_portfolio(prepared)
    total_customers = len(customers)
    returning_customers = sum(1 for customer in customers if customer["orders"] > 1)
    new_customers = total_customers - returning_customers
    return {
        "total_customers": total_customers,
        "returning_customers": returning_customers,
        "new_customers": new_customers,
        "average_orders_per_customer": round(
            sum(int(customer["orders"]) for customer in customers) / total_customers, 2
        )
        if total_customers
        else 0.0,
    }


def compute_customer_portfolio(
    prepared: PreparedCompanyDataset,
) -> list[dict[str, object]]:
    reverse = _reverse_mapping(prepared.canonical_columns)
    by_customer: dict[str, dict[str, object]] = {}

    for row_index, row in enumerate(prepared.rows):
        customer_id = _value(row, reverse, "customer_id")
        if customer_id is None:
            continue
        key = str(customer_id)
        customer = by_customer.setdefault(
            key,
            {
                "customer_id": key,
                "order_ids": set(),
                "row_count": 0,
                "total_value": 0.0,
                "first_purchase": None,
                "last_purchase": None,
                "latest_row": row,
                "latest_row_index": row_index,
            },
        )
        customer["row_count"] = int(customer["row_count"]) + 1
        order_id = _value(row, reverse, "order_id")
        if order_id is not None:
            order_ids = customer["order_ids"]
            assert isinstance(order_ids, set)
            order_ids.add(order_id)
        customer["total_value"] = float(customer["total_value"]) + (
            _as_float(_value(row, reverse, "total_amount")) or 0.0
        )
        timestamp = _as_datetime(_value(row, reverse, "order_timestamp"))
        if timestamp is not None:
            first = customer["first_purchase"]
            last = customer["last_purchase"]
            if first is None or timestamp < first:
                customer["first_purchase"] = timestamp
            if last is None or timestamp >= last:
                customer["last_purchase"] = timestamp
                customer["latest_row"] = row
                customer["latest_row_index"] = row_index

    result = []
    for customer in by_customer.values():
        order_ids = customer.pop("order_ids")
        row_count = int(customer.pop("row_count"))
        assert isinstance(order_ids, set)
        customer["orders"] = len(order_ids) or row_count
        customer["total_value"] = round(float(customer["total_value"]), 2)
        result.append(customer)
    return result
