from __future__ import annotations

from datetime import datetime, timezone
from datetime import timedelta
from typing import Any
from urllib.parse import quote

from backend.app.ai.tools.business.analytics import (
    compute_sales_summary,
    parse_business_datetime,
)
from backend.app.services.prediction_runtime import build_decision_service, resolve_executor
from backend.app.services.recommendation_severity import RecommendationSeverityPolicy
from backend.app.services.tenant_analytics_service import TenantAnalyticsService, TenantAnalyticsSnapshot
from backend.app.services.tenant_products_service import TenantProductsService
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.decision_intelligence.contracts import (
    BusinessSignal,
    DecisionContext,
    SignalDirection,
)
from shared.ai_engine.prediction.service import PredictionService


_MAX_SYNCHRONOUS_RECOMMENDATION_CUSTOMERS = 25


class TenantRecommendationsService:
    def __init__(
        self,
        analytics: TenantAnalyticsService,
        products: TenantProductsService,
        predictions: PredictionService | None,
        severity_policy: RecommendationSeverityPolicy | None = None,
    ) -> None:
        self._analytics = analytics
        self._products = products
        self._predictions = predictions
        self._severity_policy = severity_policy or RecommendationSeverityPolicy()

    def build(self, tenant: TenantContext) -> dict[str, Any]:
        snapshot = self._analytics.load(tenant)
        return self.build_from_snapshot(tenant, snapshot)

    def build_from_snapshot(
        self,
        tenant: TenantContext,
        snapshot: TenantAnalyticsSnapshot,
    ) -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc)
        source = self._products.source_for(snapshot)
        signals: list[BusinessSignal] = []
        metadata_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        self._sales_signal(tenant, snapshot, generated_at, signals, metadata_by_key)
        if source is not None:
            products = self._products.portfolio(source)
            self._product_signals(tenant, products, generated_at, signals, metadata_by_key)
            self._model_signal(tenant, snapshot, source, generated_at, signals, metadata_by_key)

        if not signals:
            return {
                "status": snapshot.status,
                "currency": snapshot.currency,
                "generated_at": generated_at,
                "recommendations": [],
            }

        decisions = build_decision_service("retail").build_bundle(
            DecisionContext(company_id=tenant.company_id, module_code="retail"),
            signals,
        ).decisions
        recommendations = []
        seen: set[tuple[str, str]] = set()
        for decision in decisions:
            signal = decision.insight.signals[0]
            key = (signal.task_code, signal.entity)
            if key in seen:
                continue
            seen.add(key)
            metadata = metadata_by_key[key]
            assessment = metadata.get("severity_assessment")
            recommendations.append(
                {
                    "id": f"{signal.task_code}:{signal.entity}",
                    "type": signal.task_code,
                    "title": metadata["title"],
                    "explanation": metadata["explanation"],
                    "priority": assessment.severity if assessment is not None else decision.priority.value,
                    "severity_reason": assessment.reason if assessment is not None else "decision_intelligence_policy",
                    "severity_score": assessment.score if assessment is not None else None,
                    "severity_factors": {
                        "absolute_impact": assessment.absolute_impact,
                        "revenue_share": assessment.revenue_share,
                    } if assessment is not None else {},
                    "source_capability": signal.capability,
                    "evidence": metadata["evidence"],
                    "affected_entity": signal.entity,
                    "confidence": signal.confidence,
                    "estimated_impact": metadata.get("estimated_impact"),
                    "affected_product": metadata.get("affected_product"),
                    "suggested_action": metadata["suggested_action"],
                    "action_route": metadata["action_route"],
                    "generated_at": generated_at,
                    "source_model_version": metadata.get("source_model_version"),
                    "lifecycle": "active",
                }
            )
        return {
            "status": snapshot.status,
            "currency": snapshot.currency,
            "generated_at": generated_at,
            "recommendations": self._rank_and_limit(recommendations),
        }

    def _sales_signal(self, tenant, snapshot, generated_at, signals, metadata_by_key) -> None:
        source = snapshot.source_for(frozenset({"total_amount"}))
        if source is None:
            return
        reverse = {canonical: original for original, canonical in source.canonical_columns.items()}
        date_column = reverse.get("order_timestamp")
        if date_column is None:
            return
        timestamps = []
        for row in source.rows:
            timestamp = parse_business_datetime(row.get(date_column))
            if timestamp is not None:
                timestamps.append(timestamp)
        if not timestamps:
            return
        current_end = max(timestamps)
        current_start = current_end - timedelta(days=29)
        previous_end = current_start - timedelta(microseconds=1)
        previous_start = previous_end - timedelta(days=29)
        current = compute_sales_summary(
            source, date_from=current_start, date_to=current_end, product=None
        )
        previous = compute_sales_summary(
            source, date_from=previous_start, date_to=previous_end, product=None
        )
        current_revenue = float(current["revenue"])
        previous_revenue = float(previous["revenue"])
        if previous_revenue == 0:
            return
        change = round(
            ((current_revenue - previous_revenue) / previous_revenue) * 100,
            2,
        )
        if abs(change) < 10:
            return
        declining = change < 0
        task_code = "revenue_decline" if declining else "revenue_growth"
        signal = BusinessSignal(
            company_id=tenant.company_id,
            module_code="retail",
            task_code=task_code,
            capability="revenue",
            entity="tenant_business",
            metric="revenue",
            value=current_revenue,
            previous_value=previous_revenue,
            direction=SignalDirection.DOWN if declining else SignalDirection.UP,
            confidence=1.0,
            timestamp=generated_at,
        )
        signals.append(signal)
        assessment = self._severity_policy.assess_revenue_change(
            current=current_revenue,
            previous=previous_revenue,
            tenant_revenue=max(abs(current_revenue), abs(previous_revenue)),
        )
        metadata_by_key[(task_code, signal.entity)] = {
            "title": task_code,
            "explanation": "revenue_changed_materially",
            "evidence": {
                "current": current_revenue,
                "comparison": previous_revenue,
                "change_percent": change,
                "period": "last_30_days_vs_previous",
            },
            "severity_assessment": assessment,
            "estimated_impact": round(current_revenue - previous_revenue, 2),
            "suggested_action": "review_sales_performance",
            "action_route": "/retail/sales",
        }

    def _product_signals(self, tenant, products, generated_at, signals, metadata_by_key) -> None:
        revenue_products = [item for item in products if item["revenue"] is not None]
        tenant_revenue = max(
            sum(float(item.get("current_revenue") or 0) for item in revenue_products),
            sum(float(item.get("previous_revenue") or 0) for item in revenue_products),
        )
        for product in revenue_products:
            change = product.get("change_percent")
            if change is None or abs(float(change)) < 10:
                continue
            declining = float(change) < 0
            task_code = "product_decline" if declining else "product_growth"
            signal = BusinessSignal(
                company_id=tenant.company_id,
                module_code="retail",
                task_code=task_code,
                capability="revenue",
                entity=str(product["product_id"]),
                metric="product_revenue",
                value=float(product["current_revenue"]),
                previous_value=float(product["previous_revenue"]),
                direction=SignalDirection.DOWN if declining else SignalDirection.UP,
                confidence=1.0,
                timestamp=generated_at,
            )
            signals.append(signal)
            assessment = self._severity_policy.assess_revenue_change(
                current=float(product["current_revenue"]),
                previous=float(product["previous_revenue"]),
                tenant_revenue=tenant_revenue,
            )
            product_id = str(product["product_id"])
            affected_product = {
                "id": product_id,
                "name": product.get("name"),
                "category": product.get("category"),
            }
            metadata_by_key[(task_code, signal.entity)] = {
                "title": task_code,
                "explanation": "product_revenue_changed",
                "evidence": {
                    "product_id": product_id,
                    "product_name": product.get("name"),
                    "category": product.get("category"),
                    "current": product["current_revenue"],
                    "comparison": product["previous_revenue"],
                    "absolute_change": round(
                        float(product["current_revenue"]) - float(product["previous_revenue"]),
                        2,
                    ),
                    "change_percent": change,
                    "revenue_share_percent": round(assessment.revenue_share * 100, 2),
                    "period": product["comparison_period"],
                },
                "severity_assessment": assessment,
                "estimated_impact": round(
                    float(product["current_revenue"]) - float(product["previous_revenue"]),
                    2,
                ),
                "affected_product": affected_product,
                "suggested_action": "review_product_performance",
                "action_route": f"/retail/products?product_id={quote(product_id, safe='')}",
            }

        total_revenue = sum(float(item["revenue"]) for item in revenue_products)
        if len(revenue_products) > 1 and total_revenue > 0:
            top = max(revenue_products, key=lambda item: float(item["revenue"]))
            share = float(top["revenue"]) / total_revenue
            if share >= 0.5:
                signal = BusinessSignal(
                    company_id=tenant.company_id,
                    module_code="retail",
                    task_code="product_concentration",
                    capability="product_concentration",
                    entity=str(top["product_id"]),
                    metric="revenue_share",
                    value=share,
                    direction=SignalDirection.RISK,
                    confidence=1.0,
                    timestamp=generated_at,
                )
                signals.append(signal)
                metadata_by_key[(signal.task_code, signal.entity)] = {
                    "title": "product_concentration",
                    "explanation": "product_revenue_concentrated",
                    "evidence": {
                        "product_id": str(top["product_id"]),
                        "product_name": top.get("name"),
                        "category": top.get("category"),
                        "current": round(share * 100, 2),
                        "revenue_share": round(share * 100, 2),
                        "period": "all_ready_data",
                    },
                    "affected_product": {
                        "id": str(top["product_id"]),
                        "name": top.get("name"),
                        "category": top.get("category"),
                    },
                    "suggested_action": "review_product_concentration",
                    "action_route": f"/retail/products?product_id={quote(str(top['product_id']), safe='')}",
                }

    @staticmethod
    def _rank_and_limit(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        priority = {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}
        ranked = sorted(
            recommendations,
            key=lambda item: (
                priority.get(item["priority"], 5),
                -abs(float(item.get("estimated_impact") or 0)),
                item["id"],
            ),
        )
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        per_type: dict[str, int] = {}
        for item in ranked:
            if item["id"] in seen or per_type.get(item["type"], 0) >= 5:
                continue
            seen.add(item["id"])
            per_type[item["type"]] = per_type.get(item["type"], 0) + 1
            result.append(item)
            if len(result) == 12:
                break
        return result

    def _model_signal(self, tenant, snapshot, source, generated_at, signals, metadata_by_key) -> None:
        if self._predictions is None:
            return
        model = next(
            (
                item
                for item in snapshot.active_models
                if item.task_code == "recommendation"
                and item.training_job.dataset_id == source.dataset_id
            ),
            None,
        )
        reverse = {canonical: original for original, canonical in source.canonical_columns.items()}
        customer_column = reverse.get("customer_id")
        if model is None or customer_column is None:
            return
        customers = sorted({str(row[customer_column]) for row in source.rows if row.get(customer_column) is not None})
        if len(customers) > _MAX_SYNCHRONOUS_RECOMMENDATION_CUSTOMERS:
            return
        opportunity_count = 0
        confidence_values: list[float] = []
        executor = resolve_executor(model.model_type)
        for customer_id in customers:
            try:
                outcome = self._predictions.predict(
                    tenant,
                    model.module_code,
                    "recommendation",
                    {"customer_id": customer_id, "top_k": 5},
                    executor,
                )
            except Exception:
                continue
            if outcome.get("result"):
                opportunity_count += 1
                if outcome.get("confidence") is not None:
                    confidence_values.append(float(outcome["confidence"]))
        if opportunity_count == 0:
            return
        confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.6
        signal = BusinessSignal(
            company_id=tenant.company_id,
            module_code=model.module_code,
            task_code="cross_sell_opportunity",
            capability="recommendation",
            entity="customer_portfolio",
            metric="customers_with_recommendations",
            value=float(opportunity_count),
            direction=SignalDirection.OPPORTUNITY,
            confidence=confidence,
            timestamp=generated_at,
        )
        signals.append(signal)
        metadata_by_key[(signal.task_code, signal.entity)] = {
            "title": "cross_sell_opportunity",
            "explanation": "cross_sell_available",
            "evidence": {"current": opportunity_count, "period": "current_ready_dataset"},
            "suggested_action": "review_cross_sell_opportunities",
            "action_route": "/retail/customers",
            "source_model_version": model.version,
        }