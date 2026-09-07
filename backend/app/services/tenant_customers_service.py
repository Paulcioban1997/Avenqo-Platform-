from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.app.ai.tools.business.analytics import compute_customer_portfolio
from backend.app.models import ModelRegistry
from backend.app.services.prediction_runtime import resolve_executor
from backend.app.services.tenant_analytics_service import TenantAnalyticsService
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.prediction.service import PredictionService


_CUSTOMER_FIELDS = frozenset({"customer_id"})
_SORT_FIELDS = frozenset({"customer_id", "orders", "total_value", "last_purchase"})
_log = logging.getLogger(__name__)


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
        self._add_rule_based_intelligence(source, customers)
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
        evaluated_at = datetime.now(timezone.utc)
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
                        customer["segment"] = self._machine_label(outcome["result"])
                        customer["segment_status"] = "available"
                        customer["segment_reason"] = "segmentation_model_prediction"
                        customer["segment_source"] = "model"
                        customer["segment_model_version"] = segment_model.version
                        customer["segment_confidence"] = self._confidence(outcome)
                        customer["segment_evaluated_at"] = evaluated_at
                except Exception:
                    _log.exception(
                        "Customer segment prediction unavailable tenant=%s customer=%s "
                        "model_version=%s category=segmentation_prediction_failed",
                        tenant.company_id,
                        customer["customer_id"],
                        segment_model.version,
                    )
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
                    risk_score = self._risk_score(outcome.get("result"))
                    confidence = self._confidence(outcome)
                    customer["risk"] = self._risk_level(risk_score, confidence)
                    customer["risk_status"] = "available"
                    customer["risk_score"] = risk_score
                    customer["risk_reason"] = (
                        "churn_model_positive" if risk_score >= 0.5 else "churn_model_negative"
                    )
                    customer["risk_source"] = "model"
                    customer["risk_model_version"] = churn_model.version
                    customer["risk_evaluated_at"] = evaluated_at
                except Exception:
                    _log.exception(
                        "Customer risk prediction unavailable tenant=%s customer=%s "
                        "model_version=%s category=churn_prediction_failed",
                        tenant.company_id,
                        customer["customer_id"],
                        churn_model.version,
                    )

    @staticmethod
    def _add_rule_based_intelligence(source, customers: list[dict[str, object]]) -> None:
        evaluated_at = datetime.now(timezone.utc)
        fields = set(source.canonical_columns.values())
        dated = [item for item in customers if item["last_purchase"] is not None]
        latest = max((item["last_purchase"] for item in dated), default=None)
        has_rfm = latest is not None and "total_amount" in fields
        values = sorted(float(item["total_value"]) for item in customers)
        high_value = values[int((len(values) - 1) * 0.75)] if values else 0.0

        for customer in customers:
            customer.update(
                {
                    "segment": None,
                    "segment_status": "not_calculated",
                    "segment_reason": "insufficient_rfm_data",
                    "segment_source": None,
                    "segment_model_version": None,
                    "segment_confidence": None,
                    "segment_evaluated_at": None,
                    "risk": None,
                    "risk_status": "not_calculated",
                    "risk_score": None,
                    "risk_reason": "insufficient_activity_data",
                    "risk_source": None,
                    "risk_model_version": None,
                    "risk_evaluated_at": None,
                }
            )
            last_purchase = customer["last_purchase"]
            if latest is None or last_purchase is None:
                continue
            recency_days = max(0, (latest - last_purchase).days)
            risk_score = min(1.0, recency_days / 120)
            customer.update(
                {
                    "risk": "low" if recency_days <= 30 else "medium" if recency_days <= 90 else "high",
                    "risk_status": "available",
                    "risk_score": round(risk_score, 4),
                    "risk_reason": "recent_activity" if recency_days <= 30 else "inactive_31_90_days" if recency_days <= 90 else "inactive_over_90_days",
                    "risk_source": "activity_recency",
                    "risk_evaluated_at": evaluated_at,
                }
            )
            if not has_rfm:
                continue
            orders = int(customer["orders"])
            total_value = float(customer["total_value"])
            first_purchase = customer["first_purchase"]
            if recency_days > 90:
                segment, reason = "dormant", "rfm_dormant"
            elif orders >= 3 and total_value >= high_value:
                segment, reason = "vip", "rfm_vip"
            elif total_value >= high_value:
                segment, reason = "high_value", "rfm_high_value"
            elif orders >= 2:
                segment, reason = "loyal", "rfm_loyal"
            elif first_purchase == last_purchase and recency_days <= 30:
                segment, reason = "new", "rfm_new"
            else:
                segment, reason = "regular", "rfm_regular"
            customer.update(
                {
                    "segment": segment,
                    "segment_status": "available",
                    "segment_reason": reason,
                    "segment_source": "rfm_rules",
                    "segment_evaluated_at": evaluated_at,
                }
            )

    @staticmethod
    def _machine_label(value: object) -> str:
        return "_".join(str(value).strip().casefold().split())

    @staticmethod
    def _confidence(outcome: dict[str, object]) -> float | None:
        value = outcome.get("confidence")
        if not isinstance(value, (int, float)):
            return None
        return round(max(0.0, min(1.0, float(value))), 4)

    @staticmethod
    def _risk_score(value: object) -> float:
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _risk_level(score: float, confidence: float | None) -> str:
        if score >= 0.9 and confidence is not None and confidence >= 0.8:
            return "critical"
        if score >= 0.6:
            return "high"
        if score >= 0.3:
            return "medium"
        return "low"

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
            "segment_status": customer["segment_status"],
            "segment_reason": customer["segment_reason"],
            "segment_source": customer["segment_source"],
            "segment_model_version": customer["segment_model_version"],
            "segment_confidence": customer["segment_confidence"],
            "segment_evaluated_at": customer["segment_evaluated_at"],
            "risk": customer.get("risk"),
            "risk_status": customer["risk_status"],
            "risk_score": customer["risk_score"],
            "risk_reason": customer["risk_reason"],
            "risk_source": customer["risk_source"],
            "risk_model_version": customer["risk_model_version"],
            "risk_evaluated_at": customer["risk_evaluated_at"],
        }