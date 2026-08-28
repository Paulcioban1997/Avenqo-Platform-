from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.ai.tools.business.analytics import compute_business_overview
from backend.app.models import Company, Dataset, DatasetStatus, ModelRegistry
from backend.app.routers.datasets import _pipeline_status
from backend.app.services.company_dataset_ingestion_service import CompanyDatasetIngestionService
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_ingestion.prepared_dataset import PreparedCompanyDataset


_KPI_FIELDS = {
    "revenue": frozenset({"total_amount"}),
    "orders": frozenset({"order_id"}),
    "customers": frozenset({"customer_id"}),
    "average_order_value": frozenset({"total_amount", "order_id"}),
}


@dataclass(frozen=True, slots=True)
class DashboardKPI:
    key: str
    value: float | int | None
    previous_value: float | int | None
    absolute_change: float | int | None
    change_percent: float | None
    currency: str | None
    available: bool


class TenantDashboardService:
    """Builds one tenant dashboard from READY Phase 4A outputs only."""

    def __init__(self, session: Session, ingestion: CompanyDatasetIngestionService) -> None:
        self._session = session
        self._ingestion = ingestion

    def build(self, tenant: TenantContext) -> dict[str, Any]:
        company = self._session.scalar(
            select(Company).where(Company.id == tenant.company_id)
        )
        currency = company.currency_code if company is not None else "USD"
        datasets = list(
            self._session.scalars(
                select(Dataset)
                .where(Dataset.company_id == tenant.company_id)
                .options(selectinload(Dataset.training_jobs))
                .order_by(Dataset.uploaded_at.desc())
            ).all()
        )
        statuses = [_pipeline_status(dataset) for dataset in datasets]
        prepared = self._prepared_ready_datasets(tenant, datasets)
        active_models = list(
            self._session.scalars(
                select(ModelRegistry).where(
                    ModelRegistry.company_id == tenant.company_id,
                    ModelRegistry.is_active.is_(True),
                )
            ).all()
        )
        capabilities = self._capabilities(prepared, active_models)
        period = self._period(prepared)
        kpis = [
            self._kpi(key, prepared, currency, period)
            for key in _KPI_FIELDS
        ]
        revenue = next(kpi for kpi in kpis if kpi.key == "revenue")
        return {
            "status": self._dashboard_status(datasets, statuses, prepared),
            "generated_at": datetime.now(timezone.utc),
            "company": {
                "currency": currency,
                "plan_code": company.subscription_plan if company is not None else "",
            },
            "period": period,
            "capabilities": sorted(capabilities),
            "kpis": [asdict(kpi) for kpi in kpis],
            "priorities": self._priorities(revenue),
            "connections": {
                "total": len(datasets),
                "ready": statuses.count("ready"),
                "analyzing": statuses.count("analyzing"),
                "preparing_data": statuses.count("preparing_data"),
                "training_ai": statuses.count("training_ai"),
                "attention_required": statuses.count("attention_required"),
                "failed": statuses.count("failed"),
            },
            "recent_activity": [
                {
                    "kind": "dataset_imported",
                    "title": dataset.name,
                    "occurred_at": self._aware(dataset.uploaded_at),
                }
                for dataset in datasets[:5]
            ]
            + [
                {
                    "kind": "model_activated",
                    "title": model.task_code,
                    "occurred_at": self._aware(model.created_at),
                }
                for model in active_models[:5]
            ],
        }

    @staticmethod
    def _priorities(revenue: DashboardKPI) -> list[dict[str, str | None]]:
        change = revenue.change_percent
        if change is None or abs(change) < 10:
            return []
        declining = change < 0
        return [
            {
                "title": "revenue_decline" if declining else "revenue_growth",
                "explanation": "revenue_changed_materially",
                "severity": "high" if declining else "medium",
                "source_capability": "revenue",
                "action_route": "/sales",
            }
        ]

    def _prepared_ready_datasets(
        self, tenant: TenantContext, datasets: list[Dataset]
    ) -> list[PreparedCompanyDataset]:
        result: list[PreparedCompanyDataset] = []
        for dataset in datasets:
            if dataset.status != DatasetStatus.READY or dataset.mapping is None:
                continue
            try:
                result.append(self._ingestion.get_prepared_dataset(tenant, dataset.id))
            except Exception:
                continue
        return result

    @staticmethod
    def _capabilities(
        prepared: list[PreparedCompanyDataset], active_models: list[ModelRegistry]
    ) -> set[str]:
        capabilities = {model.task_code for model in active_models}
        for dataset in prepared:
            fields = set(dataset.canonical_columns.values())
            capabilities.update(key for key, required in _KPI_FIELDS.items() if required <= fields)
            capabilities.update(
                readiness.capability for readiness in dataset.capability_readiness if readiness.ready
            )
        return capabilities

    def _kpi(
        self,
        key: str,
        prepared: list[PreparedCompanyDataset],
        currency: str,
        period: dict[str, datetime | None],
    ) -> DashboardKPI:
        required = _KPI_FIELDS[key]
        source = next(
            (item for item in prepared if required <= set(item.canonical_columns.values())),
            None,
        )
        if source is None:
            return DashboardKPI(key, None, None, None, None, None, False)

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
            current,
            previous,
            absolute,
            change,
            currency if monetary else None,
            True,
        )

    @staticmethod
    def _period(prepared: list[PreparedCompanyDataset]) -> dict[str, datetime | None]:
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
    def _dashboard_status(
        datasets: list[Dataset], statuses: list[str], prepared: list[PreparedCompanyDataset]
    ) -> str:
        if not datasets:
            return "no_data"
        if prepared and any(status != "ready" for status in statuses):
            return "partial_ready"
        if prepared:
            return "ready"
        if statuses and all(status == "failed" for status in statuses):
            return "error"
        return "processing"

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)