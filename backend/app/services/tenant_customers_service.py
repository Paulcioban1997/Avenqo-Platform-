from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from backend.app.ai.tools.business.analytics import compute_customer_portfolio
from backend.app.models import ModelRegistry
from backend.app.services.prediction_runtime import resolve_executor
from backend.app.services.tenant_analytics_service import TenantAnalyticsService
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.prediction.service import PredictionService


_CUSTOMER_FIELDS = frozenset({"customer_id"})
_SORT_FIELDS = frozenset({"customer_id", "orders", "total_value", "last_purchase"})


class InvalidCustomerQuery(ValueError):
    pass


class CustomerNotFound(LookupError):
    pass


class TenantCustomersService:
    def __init__(
        self,
        analytics: TenantAnalyticsService,
        prediction_service: PredictionService,
    ) -> None:
        self._analytics = analytics
        self._prediction_service = prediction_service

    def build(
        self,
        tenant: TenantContext,
        *,
        page: int = 1,
        page_size: int = 25,
        search: str | None = None,
        segment: str | None = None,
        risk: str | None = None,
        sort_by: str = "total_value",
        sort_direction: str = "desc",
        exact_customer_id: str | None = None,
    ) -> dict[str, Any]:
        if sort_by not in _SORT_FIELDS or sort_direction not in {"asc", "desc"}:
            raise InvalidCustomerQuery("Unsupported customer sorting")
        snapshot = self._analytics.load(tenant)
        source = snapshot.source_for(_CUSTOMER_FIELDS)
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
                "segments": [],
                "risks": [],
                "items": [],
                "pagination": {"page": page, "page_size": page_size, "total": 0, "pages": 0},
            }

        customers = compute_customer_portfolio(source)
        self._add_activity_status(customers)
        self._add_model_outputs(tenant, source, snapshot.active_models, customers)
        summary = self._summary(customers, "total_amount" in source.canonical_columns.values())
        segments = self._counts(customers, "segment")
        risks = self._counts(customers, "risk")

        filtered = customers
        if search:
            needle = search.casefold()
            filtered = [item for item in filtered if needle in str(item["customer_id"]).casefold()]
        if exact_customer_id is not None:
            filtered = [item for item in filtered if item["customer_id"] == exact_customer_id]
        if segment:
            filtered = [item for item in filtered if item.get("segment") == segment]
        if risk:
            filtered = [item for item in filtered if item.get("risk") == risk]
        reverse = sort_direction == "desc"
        filtered.sort(
            key=lambda item: (item.get(sort_by) is not None, item.get(sort_by)),
            reverse=reverse,
        )
        total = len(filtered)
        offset = (page - 1) * page_size
        items = [self._safe_item(item) for item in filtered[offset : offset + page_size]]
        return {
            **base,
            "summary": summary,
            "segments": segments,
            "risks": risks,
            "items": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "pages": (total + page_size - 1) // page_size,
            },
        }

    def get_customer(self, tenant: TenantContext, customer_id: str) -> dict[str, Any]:
        result = self.build(
            tenant,
            page=1,
            page_size=1,
            exact_customer_id=customer_id,
        )
        match = next(
            (item for item in result["items"] if item["customer_id"] == customer_id),
            None,
        )
        if match is None:
            raise CustomerNotFound("Customer not found")
        return match

    def _add_model_outputs(
        self,
        tenant: TenantContext,
        source,
        active_models: tuple[ModelRegistry, ...],
        customers: list[dict[str, object]],
    ) -> None:
        by_task = {
            model.task_code: model
            for model in active_models
            if model.training_job.dataset_id == source.dataset_id
        }
        segment_model = by_task.get("segmentation")
        churn_model = by_task.get("churn")
        churn_column = next(
            (
                original
                for original, canonical in source.canonical_columns.items()
                if canonical == "churn_flag"
            ),
            None,
        )
        for customer in customers:
            row = dict(customer["latest_row"])
            if segment_model is not None:
                try:
                    outcome = self._prediction_service.predict(
                        tenant,
                        segment_model.module_code,
                        "segmentation",
                        row,
                        resolve_executor(segment_model.model_type),
                    )
                    if outcome.get("result") is not None:
                        customer["segment"] = str(outcome["result"])
                except Exception:
                    pass
            if churn_model is not None:
                if churn_column is not None:
                    row.pop(churn_column, None)
                try:
                    outcome = self._prediction_service.predict(
                        tenant,
                        churn_model.module_code,
                        "churn",
                        row,
                        resolve_executor(churn_model.model_type),
                    )
                    customer["risk"] = (
                        "churn_prediction"
                        if outcome.get("result") in {1, 1.0, True, "1"}
                        else "not_predicted_at_risk"
                    )
                except Exception:
                    pass

    @staticmethod
    def _add_activity_status(customers: list[dict[str, object]]) -> None:
        dates = [item["last_purchase"] for item in customers if item["last_purchase"] is not None]
        cutoff = max(dates) - timedelta(days=89) if dates else None
        for customer in customers:
            last = customer["last_purchase"]
            customer["status"] = (
                "active" if cutoff is not None and last is not None and last >= cutoff else "inactive"
            ) if cutoff is not None else None

    @staticmethod
    def _summary(customers: list[dict[str, object]], has_value: bool) -> dict[str, Any]:
        total = len(customers)
        active = sum(1 for item in customers if item.get("status") == "active")
        repeat = sum(1 for item in customers if int(item["orders"]) > 1)
        dates = [item["last_purchase"] for item in customers if item["last_purchase"] is not None]
        new_cutoff = max(dates) - timedelta(days=29) if dates else None
        new = sum(
            1
            for item in customers
            if new_cutoff is not None
            and item["first_purchase"] is not None
            and item["first_purchase"] >= new_cutoff
        )
        return {
            "total_customers": total,
            "active_customers": active if dates else None,
            "new_customers": new if dates else None,
            "repeat_customers": repeat,
            "purchase_frequency": round(
                sum(int(item["orders"]) for item in customers) / total, 2
            ) if total else 0.0,
            "average_customer_value": round(
                sum(float(item["total_value"]) for item in customers) / total, 2
            ) if total and has_value else None,
        }

    @staticmethod
    def _counts(customers: list[dict[str, object]], field: str) -> list[dict[str, object]]:
        counts = Counter(str(item[field]) for item in customers if item.get(field) is not None)
        return [{"label": label, "count": count} for label, count in counts.most_common()]

    @staticmethod
    def _safe_item(customer: dict[str, object]) -> dict[str, object]:
        return {
            "customer_id": customer["customer_id"],
            "orders": customer["orders"],
            "total_value": customer["total_value"],
            "first_purchase": customer["first_purchase"],
            "last_purchase": customer["last_purchase"],
            "status": customer.get("status"),
            "segment": customer.get("segment"),
            "risk": customer.get("risk"),
        }