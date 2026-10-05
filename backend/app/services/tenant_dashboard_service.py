from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.app.ai.tools.business.analytics import (
    parse_business_datetime,
)
from backend.app.services.business_metrics_service import BusinessMetricsService
from backend.app.services.data_freshness_service import DataFreshnessService
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
    metric: dict[str, object] | None = None


class TenantDashboardService:
    """Builds one tenant dashboard from READY Phase 4A outputs only."""

    def __init__(
        self,
        analytics: TenantAnalyticsService,
        recommendations: TenantRecommendationsService,
    ) -> None:
        self._analytics = analytics
        self._recommendations = recommendations

    def build(self, tenant: TenantContext, period_key: str | None = None) -> dict[str, Any]:
        snapshot = self._analytics.load_for_dashboard(tenant)
        metrics_service = BusinessMetricsService()
        timezone_name = getattr(snapshot.company, "timezone", None) or "UTC"
        period_source = snapshot.source_for(
            BUSINESS_METRIC_FIELDS["revenue"] | BUSINESS_METRIC_FIELDS["orders"]
        )
        period = metrics_service.resolve_period(
            period_key,
            timezone_name=timezone_name,
            now=datetime.now(timezone.utc),
            source=period_source,
        )
        if period_key == "all" and snapshot.retail_summaries:
            cached_periods = [
                summary.get("period", {}) for summary in snapshot.retail_summaries
            ]
            starts = [
                datetime.fromisoformat(value)
                for item in cached_periods
                if (value := item.get("start"))
            ]
            ends = [
                datetime.fromisoformat(value)
                for item in cached_periods
                if (value := item.get("end"))
            ]
            period["start"] = min(starts) if starts else None
            period["end"] = max(ends) if ends else None
        kpis = [
            self._kpi(key, snapshot, snapshot.currency, period, period_key, metrics_service)
            for key in BUSINESS_METRIC_FIELDS
        ]
        recommendations = self._recommendations.build_from_snapshot(tenant, snapshot)[
            "recommendations"
        ]
        trend_source = snapshot.source_for(
            BUSINESS_METRIC_FIELDS["revenue"] | BUSINESS_METRIC_FIELDS["orders"]
        )
        granularity = "day" if period_key == "last_7_days" else "week" if period_key == "last_30_days" else "month"
        cached_trend_points = [
            point
            for summary in snapshot.retail_summaries
            for point in (summary.get("period_trends", {}).get(period_key or "last_30_days") or [])
        ]
        trend = metrics_service.sales_trend(
            snapshot,
            trend_source,
            period_start=None if period_key == "all" else period["start"],
            period_end=None if period_key == "all" else period["end"],
            granularity=granularity,
        ) if trend_source is not None else {"points": []}
        if not trend.get("points") and cached_trend_points:
            trend = {"points": cached_trend_points}
        if not trend.get("points") and period_key == "all":
            values = {item.key: item.value for item in kpis}
            revenue = float(values.get("revenue") or 0)
            orders = int(values.get("orders") or 0)
            if revenue or orders:
                trend = {
                    "points": [{
                        "period": "All",
                        "revenue": revenue,
                        "orders": orders,
                        "change_percent": None,
                    }]
                }
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
            "metrics": [kpi.metric for kpi in kpis if kpi.metric is not None],
            "data_freshness": DataFreshnessService().for_snapshot(snapshot).as_dict(),
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
            "trend": {"points": trend.get("points", [])},
            "connections": {
                "total": len(snapshot.statuses),
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
        period_key: str | None,
        metrics_service: BusinessMetricsService,
    ) -> DashboardKPI:
        summary_key = period_key or "last_30_days"
        for summary in snapshot.retail_summaries:
            metrics = (
                summary.get("current")
                if period_key is None
                else summary.get("period_metrics", {}).get(summary_key)
            )
            if metrics is not None and key in metrics:
                current = metrics[key]
                monetary = key in {"revenue", "average_order_value"}
                metric = metrics_service.metric_envelope(
                    snapshot,
                    None,
                    key,
                    current,
                    "currency" if monetary else "count",
                    period.get("start"),
                    period.get("end"),
                    int(metrics.get("orders") or 0),
                    state="AVAILABLE",
                )
                return DashboardKPI(
                    key,
                    "AVAILABLE",
                    current,
                    None,
                    None,
                    None,
                    currency if monetary else None,
                    True,
                    metric,
                )
        required = BUSINESS_METRIC_FIELDS[key]
        source = snapshot.source_for(required)
        if source is None:
            processing = snapshot.status == "processing" or any(
                status == "analyzing" for status in snapshot.statuses
            ) or any(
                status in {"preparing_data", "training_ai"}
                for status in snapshot.training_statuses
            )
            metric = metrics_service.metric_envelope(
                snapshot, None, key, None, "currency" if key in {"revenue", "average_order_value"} else "count",
                period.get("start"), period.get("end"), 0, state="SOURCE_UNAVAILABLE" if "SOURCE_UNAVAILABLE" in snapshot.retail_states else "UNAVAILABLE",
            )
            return DashboardKPI(
                key,
                "SOURCE_UNAVAILABLE" if "SOURCE_UNAVAILABLE" in snapshot.retail_states else "PROCESSING" if processing or "PROCESSING" in snapshot.retail_states else "UNAVAILABLE",
                None,
                None,
                None,
                None,
                None,
                False,
                metric,
            )

        current_overview = metrics_service.business_overview(
            snapshot,
            source,
            period_start=period.get("start"),
            period_end=period.get("end"),
        )
        current = current_overview[key]
        previous_overview = None
        if period.get("comparison_start") is not None and period.get("comparison_end") is not None:
            previous_overview = metrics_service.business_overview(
                snapshot,
                source,
                period_start=period["comparison_start"],
                period_end=period["comparison_end"],
            )
        previous_sample_size = int(previous_overview["orders"]) if previous_overview else 0
        previous = previous_overview[key] if previous_sample_size else None
        absolute = current - previous if previous is not None else None
        change = round((absolute / previous) * 100, 2) if previous not in {None, 0} else None
        monetary = key in {"revenue", "average_order_value"}
        metric = next(item for item in current_overview["metrics"] if item["metric_id"] == key)
        return DashboardKPI(
            key,
            "AVAILABLE",
            current,
            previous,
            absolute,
            change,
            currency if monetary else None,
            True,
            metric,
        )

    @staticmethod
    def _period(
        prepared: tuple[PreparedCompanyDataset, ...], period_key: str | None
    ) -> dict[str, datetime | None]:
        if period_key is None:
            timestamps: list[datetime] = []
            for dataset in prepared:
                date_column = next(
                    (source for source, canonical in dataset.canonical_columns.items()
                     if canonical == "order_timestamp"),
                    None,
                )
                if date_column is None:
                    continue
                for row in dataset.rows:
                    timestamp = parse_business_datetime(row.get(date_column))
                    if timestamp is not None:
                        timestamps.append(
                            timestamp.replace(tzinfo=timezone.utc)
                            if timestamp.tzinfo is None
                            else timestamp.astimezone(timezone.utc)
                        )
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
        now = datetime.now(timezone.utc)
        if period_key == "all":
            timestamps = TenantDashboardService._timestamps(prepared)
            return {
                "start": min(timestamps) if timestamps else None,
                "end": max(timestamps) if timestamps else None,
                "comparison_start": None,
                "comparison_end": None,
            }
        if period_key == "last_7_days":
            start = now - timedelta(days=7)
            comparison_start = start - timedelta(days=7)
            comparison_end = start - timedelta(microseconds=1)
        elif period_key == "last_30_days":
            start = now - timedelta(days=30)
            comparison_start = start - timedelta(days=30)
            comparison_end = start - timedelta(microseconds=1)
        elif period_key == "current_quarter":
            quarter_month = ((now.month - 1) // 3) * 3 + 1
            start = now.replace(month=quarter_month, day=1, hour=0, minute=0, second=0, microsecond=0)
            previous_quarter_month = ((quarter_month - 4) % 12) + 1
            previous_quarter_year = now.year - (1 if quarter_month == 1 else 0)
            comparison_start = datetime(
                previous_quarter_year, previous_quarter_month, 1, tzinfo=timezone.utc
            )
            comparison_end = start - timedelta(microseconds=1)
        else:
            raise ValueError("Unsupported dashboard period")
        return {
            "start": start,
            "end": now,
            "comparison_start": comparison_start,
            "comparison_end": comparison_end,
        }

    @staticmethod
    def _timestamps(
        prepared: tuple[PreparedCompanyDataset, ...],
    ) -> list[datetime]:
        timestamps = []
        for dataset in prepared:
            date_column = next(
                (source for source, canonical in dataset.canonical_columns.items()
                 if canonical == "order_timestamp"),
                None,
            )
            if date_column is None:
                continue
            for row in dataset.rows:
                timestamp = parse_business_datetime(row.get(date_column))
                if timestamp is not None:
                    timestamps.append(
                        timestamp.replace(tzinfo=timezone.utc)
                        if timestamp.tzinfo is None
                        else timestamp.astimezone(timezone.utc)
                    )
        return timestamps

    @staticmethod
    def _period_rows(
        prepared: PreparedCompanyDataset,
        period: dict[str, datetime | None],
        period_key: str | None,
    ) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
        if period_key == "all":
            return prepared.rows, ()
        if period_key is None and period["start"] is None:
            return prepared.rows, ()
        reverse = {canonical: source for source, canonical in prepared.canonical_columns.items()}
        date_column = reverse.get("order_timestamp")
        if date_column is None:
            return (), ()

        def between(row: dict[str, object], start: datetime, end: datetime) -> bool:
            timestamp = parse_business_datetime(row.get(date_column))
            if timestamp is None:
                return False
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            else:
                timestamp = timestamp.astimezone(timezone.utc)
            return start <= timestamp <= end

        comparison_start = period["comparison_start"]
        comparison_end = period["comparison_end"]
        return (
            tuple(row for row in prepared.rows if between(row, period["start"], period["end"])),
            tuple(
                row
                for row in prepared.rows
                if comparison_start is not None
                and comparison_end is not None
                and between(row, comparison_start, comparison_end)
            ) if comparison_start is not None and comparison_end is not None else (),
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
