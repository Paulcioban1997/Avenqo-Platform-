from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.models import (
    Company,
    Dataset,
    DatasetStatus,
    JobStatus,
    ModelRegistry,
    TrainingJob,
)
from backend.app.routers.datasets import _pipeline_status
from backend.app.services.company_dataset_ingestion_service import CompanyDatasetIngestionService
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_ingestion.prepared_dataset import PreparedCompanyDataset


BUSINESS_METRIC_FIELDS = {
    "revenue": frozenset({"total_amount"}),
    "orders": frozenset({"order_id"}),
    "customers": frozenset({"customer_id"}),
    "average_order_value": frozenset({"total_amount", "order_id"}),
}


@dataclass(frozen=True, slots=True)
class TenantAnalyticsSnapshot:
    company: Company | None
    datasets: tuple[Dataset, ...]
    statuses: tuple[str, ...]
    prepared: tuple[PreparedCompanyDataset, ...]
    active_models: tuple[ModelRegistry, ...]
    capabilities: frozenset[str]
    status: str

    @property
    def currency(self) -> str:
        return self.company.currency_code if self.company is not None else "USD"

    def source_for(self, required_fields: frozenset[str]) -> PreparedCompanyDataset | None:
        return next(
            (
                item
                for item in self.prepared
                if required_fields <= set(item.canonical_columns.values())
            ),
            None,
        )


class TenantAnalyticsService:
    """Loads the shared, tenant-scoped analytics inputs produced by Phase 4A."""

    def __init__(self, session: Session, ingestion: CompanyDatasetIngestionService) -> None:
        self._session = session
        self._ingestion = ingestion

    def load(self, tenant: TenantContext) -> TenantAnalyticsSnapshot:
        company = self._session.scalar(select(Company).where(Company.id == tenant.company_id))
        datasets = tuple(
            self._session.scalars(
                select(Dataset)
                .where(Dataset.company_id == tenant.company_id)
                .options(selectinload(Dataset.training_jobs))
                .order_by(Dataset.uploaded_at.desc())
            ).all()
        )
        statuses = tuple(_pipeline_status(dataset) for dataset in datasets)
        prepared = self._prepared_ready_datasets(tenant, datasets)
        prepared_ids = {item.dataset_id for item in prepared}
        active_models = tuple(
            self._session.scalars(
                select(ModelRegistry)
                .join(TrainingJob, TrainingJob.id == ModelRegistry.training_job_id)
                .where(
                    ModelRegistry.company_id == tenant.company_id,
                    ModelRegistry.is_active.is_(True),
                    TrainingJob.company_id == tenant.company_id,
                    TrainingJob.status == JobStatus.COMPLETED,
                    TrainingJob.dataset_id.in_(prepared_ids),
                )
            ).all()
        ) if prepared_ids else ()
        capabilities = self._capabilities(prepared, active_models)
        return TenantAnalyticsSnapshot(
            company=company,
            datasets=datasets,
            statuses=statuses,
            prepared=prepared,
            active_models=active_models,
            capabilities=frozenset(capabilities),
            status=self._status(datasets, statuses, prepared),
        )

    def _prepared_ready_datasets(
        self, tenant: TenantContext, datasets: tuple[Dataset, ...]
    ) -> tuple[PreparedCompanyDataset, ...]:
        result: list[PreparedCompanyDataset] = []
        for dataset in datasets:
            if dataset.status != DatasetStatus.READY or dataset.mapping is None:
                continue
            try:
                result.append(self._ingestion.get_prepared_dataset(tenant, dataset.id))
            except Exception:
                continue
        return tuple(result)

    @staticmethod
    def _capabilities(
        prepared: tuple[PreparedCompanyDataset, ...],
        active_models: tuple[ModelRegistry, ...],
    ) -> set[str]:
        capabilities = {model.task_code for model in active_models}
        for dataset in prepared:
            fields = set(dataset.canonical_columns.values())
            capabilities.update(
                key for key, required in BUSINESS_METRIC_FIELDS.items() if required <= fields
            )
            capabilities.update(
                readiness.capability
                for readiness in dataset.capability_readiness
                if readiness.ready
            )
        return capabilities

    @staticmethod
    def _status(
        datasets: tuple[Dataset, ...],
        statuses: tuple[str, ...],
        prepared: tuple[PreparedCompanyDataset, ...],
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