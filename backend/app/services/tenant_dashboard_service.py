from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.app.ai.tools.business.analytics import compute_business_overview
from backend.app.services.tenant_analytics_service import (
    BUSINESS_METRIC_FIELDS,
    TenantAnalyticsSnapshot,
    TenantAnalyticsService,
)
from backend.app.services.tenant_recommendations_service import TenantRecommendationsService
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_ingestion.prepared_dataset import PreparedCompanyDataset


@dataclass(frozen=True, slots=True)
class DashboardKPI:
    key: str
    state: str
    value: float | int | None
    previous_value: float | int | None
    absolute_change: float | int | None
    change_percent: float | None
    currency: str | None
    available: bool


class TenantDashboardService:
    """Builds one tenant dashboard from READY Phase 4A outputs only."""

    def __init__(
        self,
        analytics: TenantAnalyticsService,
        recommendations: TenantRecommendationsService,
    ) -> None:
        self._analytics = analytics
        self._recommendations = recommendations

    def build(self, tenant: TenantContext) -> dict[str, Any]:
        snapshot = self._analytics.load(tenant)
        period = self._period(snapshot.prepared)
        kpis = [
            self._kpi(key, snapshot, snapshot.currency, period)
            for key in BUSINESS_METRIC_FIELDS
        ]
        recommendations = self._recommendations.build_from_snapshot(tenant, snapshot)[
            "recommendations"
        ]
        return {
            "status": snapshot.status,
            "generated_at": datetime.now(timezone.utc),
            "company": {
                "currency": snapshot.currency,
                "plan_code": snapshot.company.subscription_plan if snapshot.company is not None else "",
            },
            "period": period,
            "capabilities": sorted(snapshot.capabilities),
            "kpis": [asdict(kpi) for kpi in kpis],
            "priorities": [
                {
                    "id": item["id"],
                    "type": item["type"],
                    "title": item["title"],
                    "explanation": item["explanation"],
                    "severity": item["priority"],
                    "source_capability": item["source_capability"],
                    "evidence": item["evidence"],
                    "suggested_action": item["suggested_action"],
                    "action_route": item["action_route"],
                }
                for item in recommendations[:3]
            ],
            "connections": {
                "total": len(snapshot.datasets),
                "ready": snapshot.statuses.count("ready"),
                "analyzing": snapshot.statuses.count("analyzing"),
                "preparing_data": snapshot.training_statuses.count("preparing_data"),
                "training_ai": snapshot.training_statuses.count("training_ai"),
                "training_failed": snapshot.training_statuses.count("training_failed"),
                "attention_required": snapshot.statuses.count("attention_required"),
                "failed": snapshot.statuses.count("failed"),
            },
            "recent_activity": [
                {
                    "kind": "dataset_imported",
                    "title": dataset.name,
                    "occurred_at": self._aware(dataset.uploaded_at),
                }
                for dataset in snapshot.datasets[:5]
            ]
            + [
                {
                    "kind": "model_activated",
                    "title": model.task_code,
                    "occurred_at": self._aware(model.created_at),
                }
                for model in snapshot.active_models[:5]
            ],
        }

    def _kpi(
        self,
        key: str,
        snapshot: TenantAnalyticsSnapshot,
        currency: str,
        period: dict[str, datetime | None],
    ) -> DashboardKPI:
        required = BUSINESS_METRIC_FIELDS[key]
        source = snapshot.source_for(required)
        if source is None:
            processing = snapshot.status == "processing" or any(
                status == "analyzing" for status in snapshot.statuses
            ) or any(
                status in {"preparing_data", "training_ai"}
                for status in snapshot.training_statuses
            )
            return DashboardKPI(
                key,
                "PROCESSING" if processing else "UNAVAILABLE",
                None,
                None,
                None,
                None,
                None,
                False,
            )

        current_rows, previous_rows = self._period_rows(source, period)
        current = compute_business_overview(self._with_rows(source, current_rows))[key]
        previous = (
            compute_business_overview(self._with_rows(source, previous_rows))[key]
            if previous_rows
            else None
        )
        absolute = current - previous if previous is not None else None
        change = round((absolute / previous) * 100, 2) if previous not in {None, 0} else None
        monetary = key in {"revenue", "average_order_value"}
        return DashboardKPI(
            key,
            "AVAILABLE",
            current,
            previous,
            absolute,
            change,
            currency if monetary else None,
            True,
        )

    @staticmethod
    def _period(prepared: tuple[PreparedCompanyDataset, ...]) -> dict[str, datetime | None]:
        timestamps: list[datetime] = []
        for dataset in prepared:
            reverse = {canonical: source for source, canonical in dataset.canonical_columns.items()}
            date_column = reverse.get("order_timestamp")
            if date_column is None:
                continue
            for row in dataset.rows:
                value = row.get(date_column)
                if isinstance(value, str):
                    try:
                        timestamps.append(datetime.fromisoformat(value))
                    except ValueError:
                        pass
        if not timestamps:
            return {"start": None, "end": None, "comparison_start": None, "comparison_end": None}
        end = max(timestamps)
        start = end - timedelta(days=29)
        return {
            "start": start,
            "end": end,
            "comparison_start": start - timedelta(days=30),
            "comparison_end": start - timedelta(microseconds=1),
        }

    @staticmethod
    def _period_rows(
        prepared: PreparedCompanyDataset, period: dict[str, datetime | None]
    ) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
        if period["start"] is None:
            return prepared.rows, ()
        reverse = {canonical: source for source, canonical in prepared.canonical_columns.items()}
        date_column = reverse.get("order_timestamp")
        if date_column is None:
            return prepared.rows, ()

        def between(row: dict[str, object], start: datetime, end: datetime) -> bool:
            value = row.get(date_column)
            if not isinstance(value, str):
                return False
            try:
                timestamp = datetime.fromisoformat(value)
            except ValueError:
                return False
            return start <= timestamp <= end

        return (
            tuple(row for row in prepared.rows if between(row, period["start"], period["end"])),
            tuple(
                row
                for row in prepared.rows
                if between(row, period["comparison_start"], period["comparison_end"])
            ),
        )

    @staticmethod
    def _with_rows(
        prepared: PreparedCompanyDataset, rows: tuple[dict[str, object], ...]
    ) -> PreparedCompanyDataset:
        return PreparedCompanyDataset(
            company_id=prepared.company_id,
            dataset_id=prepared.dataset_id,
            version=prepared.version,
            canonical_columns=prepared.canonical_columns,
            rows=rows,
            profile=prepared.profile,
            mapping=prepared.mapping,
            cleaning_report=prepared.cleaning_report,
            quality=prepared.quality,
            capability_readiness=prepared.capability_readiness,
        )

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
