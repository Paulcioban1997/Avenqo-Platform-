from __future__ import annotations

from datetime import datetime, timedelta
from math import ceil
from typing import Any

from backend.app.ai.tools.business.analytics import (
    compute_product_period_revenue,
    compute_product_portfolio,
    compute_sales_trend,
)
from backend.app.services.tenant_analytics_service import (
    TenantAnalyticsService,
    TenantAnalyticsSnapshot,
)
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_ingestion.prepared_dataset import PreparedCompanyDataset


_PRODUCT_FIELDS = frozenset({"product_id", "product_name"})
_SORT_FIELDS = frozenset(
    {"product_id", "name", "category", "revenue", "quantity", "orders", "last_activity"}
)


class InvalidProductQuery(ValueError):
    pass


class ProductNotFound(LookupError):
    pass


class TenantProductsService:
    def __init__(self, analytics: TenantAnalyticsService) -> None:
        self._analytics = analytics

    def build(
        self,
        tenant: TenantContext,
        *,
        page: int = 1,
        page_size: int = 25,
        search: str | None = None,
        category: str | None = None,
        performance: str | None = None,
        status: str | None = None,
        sort_by: str = "revenue",
        sort_direction: str = "desc",
    ) -> dict[str, Any]:
        return self.build_from_snapshot(
            self._analytics.load(tenant),
            page=page,
            page_size=page_size,
            search=search,
            category=category,
            performance=performance,
            status=status,
            sort_by=sort_by,
            sort_direction=sort_direction,
        )

    def build_from_snapshot(
        self,
        snapshot: TenantAnalyticsSnapshot,
        *,
        page: int = 1,
        page_size: int = 25,
        search: str | None = None,
        category: str | None = None,
        performance: str | None = None,
        status: str | None = None,
        sort_by: str = "revenue",
        sort_direction: str = "desc",
    ) -> dict[str, Any]:
        if sort_by not in _SORT_FIELDS or sort_direction not in {"asc", "desc"}:
            raise InvalidProductQuery("Unsupported product sorting")
        if performance not in {None, "strong", "stable", "weak"}:
            raise InvalidProductQuery("Unsupported product performance filter")
        if status not in {None, "active", "inactive", "out_of_stock"}:
            raise InvalidProductQuery("Unsupported product status filter")

        source = self.source_for(snapshot)
        base = {
            "status": snapshot.status,
            "available": source is not None,
            "currency": snapshot.currency,
            "capabilities": sorted(snapshot.capabilities),
        }
        if source is None:
            return {
                **base,
                "summary": None,
                "categories": [],
                "trend": {"granularity": "month", "points": []},
                "items": [],
                "pagination": {"page": page, "page_size": page_size, "total": 0, "pages": 0},
            }

        products = self.portfolio(source)
        summary = self._summary(products)
        categories = self._categories(products)
        filtered = products
        if search:
            needle = search.casefold()
            filtered = [
                item
                for item in filtered
                if needle in str(item["product_id"]).casefold()
                or needle in str(item.get("name") or "").casefold()
            ]
        if category:
            filtered = [item for item in filtered if item.get("category") == category]
        if performance:
            filtered = [item for item in filtered if item.get("performance") == performance]
        if status:
            filtered = [item for item in filtered if item.get("status") == status]
        filtered.sort(
            key=lambda item: (item.get(sort_by) is not None, item.get(sort_by)),
            reverse=sort_direction == "desc",
        )
        total = len(filtered)
        offset = (page - 1) * page_size
        return {
            **base,
            "summary": summary,
            "categories": categories,
            "trend": compute_sales_trend(source, granularity="month"),
            "items": filtered[offset : offset + page_size],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "pages": ceil(total / page_size) if total else 0,
            },
        }

    def get_product(self, tenant: TenantContext, product_id: str) -> dict[str, Any]:
        snapshot = self._analytics.load(tenant)
        source = self.source_for(snapshot)
        if source is None:
            raise ProductNotFound("Product not found")
        match = next(
            (item for item in self.portfolio(source) if item["product_id"] == product_id),
            None,
        )
        if match is None:
            raise ProductNotFound("Product not found")
        return {
            **match,
            "currency": snapshot.currency,
            "trend": compute_sales_trend(source, granularity="month", product=product_id),
        }

    @staticmethod
    def source_for(snapshot: TenantAnalyticsSnapshot) -> PreparedCompanyDataset | None:
        return snapshot.source_for(frozenset({"product_id"})) or snapshot.source_for(
            frozenset({"product_name"})
        )

    @staticmethod
    def portfolio(source: PreparedCompanyDataset) -> list[dict[str, Any]]:
        products = compute_product_portfolio(source)
        dates = [item["last_activity"] for item in products if item["last_activity"] is not None]
        latest = max(dates) if dates else None
        current_start = latest - timedelta(days=29) if latest is not None else None
        previous_end = current_start - timedelta(microseconds=1) if current_start is not None else None
        previous_start = previous_end - timedelta(days=29) if previous_end is not None else None
        revenue_by_product = compute_product_period_revenue(
            source,
            current_from=current_start,
            current_to=latest,
            previous_from=previous_start,
            previous_to=previous_end,
        )
        for product in products:
            product_id = str(product["product_id"])
            revenue = revenue_by_product.get(
                product_id,
                {"current": 0.0, "previous": 0.0},
            )
            has_revenue = product["revenue"] is not None
            current_revenue = float(revenue["current"]) if has_revenue else None
            previous_revenue = (
                float(revenue["previous"])
                if has_revenue and previous_start is not None
                else None
            )
            change = (
                round(((current_revenue - previous_revenue) / previous_revenue) * 100, 2)
                if current_revenue is not None and previous_revenue not in {None, 0}
                else None
            )
            product["current_revenue"] = current_revenue
            product["previous_revenue"] = previous_revenue
            product["change_percent"] = change
            product["comparison_period"] = {
                "start": current_start,
                "end": latest,
                "comparison_start": previous_start,
                "comparison_end": previous_end,
            }
            product["performance"] = (
                "strong" if change is not None and change >= 10
                else "weak" if change is not None and change <= -10
                else "stable" if change is not None
                else None
            )
            stock = product.get("stock_level")
            product["status"] = (
                "out_of_stock" if stock is not None and float(stock) <= 0
                else "active" if latest is not None and product["last_activity"] is not None
                and product["last_activity"] >= latest - timedelta(days=89)
                else "inactive" if latest is not None
                else None
            )
        return products

    @staticmethod
    def _summary(products: list[dict[str, Any]]) -> dict[str, Any]:
        revenues = [float(item["revenue"]) for item in products if item["revenue"] is not None]
        quantities = [float(item["quantity"]) for item in products if item["quantity"] is not None]
        total_revenue = round(sum(revenues), 2) if revenues else None
        ranked_revenue = sorted(revenues, reverse=True)
        concentration = (
            round((ranked_revenue[0] / total_revenue) * 100, 2)
            if total_revenue not in {None, 0} and len(ranked_revenue) > 1
            else None
        )
        total_quantity = round(sum(quantities), 2) if quantities else None
        stocks = [item["stock_level"] for item in products if item["stock_level"] is not None]
        return {
            "total_products": len(products),
            "active_products": sum(1 for item in products if item["status"] == "active")
            if any(item["status"] is not None for item in products) else None,
            "products_with_activity": sum(1 for item in products if int(item["orders"]) > 0),
            "revenue": total_revenue,
            "units": total_quantity,
            "average_selling_price": round(total_revenue / total_quantity, 2)
            if total_revenue is not None and total_quantity not in {None, 0} else None,
            "top_product_revenue_share": concentration,
            "out_of_stock_products": sum(1 for stock in stocks if float(stock) <= 0) if stocks else None,
        }

    @staticmethod
    def _categories(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for product in products:
            category = product.get("category")
            if category is None:
                continue
            item = grouped.setdefault(
                str(category),
                {"category": str(category), "product_count": 0, "revenue": None, "units": None},
            )
            item["product_count"] += 1
            if product["revenue"] is not None:
                item["revenue"] = round(float(item["revenue"] or 0) + float(product["revenue"]), 2)
            if product["quantity"] is not None:
                item["units"] = round(float(item["units"] or 0) + float(product["quantity"]), 2)
        total_revenue = sum(float(item["revenue"] or 0) for item in grouped.values())
        for item in grouped.values():
            item["revenue_share"] = (
                round((float(item["revenue"]) / total_revenue) * 100, 2)
                if item["revenue"] is not None and total_revenue else None
            )
        return sorted(grouped.values(), key=lambda item: float(item["revenue"] or 0), reverse=True)
