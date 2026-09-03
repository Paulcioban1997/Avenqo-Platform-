from __future__ import annotations

from dataclasses import dataclass, replace

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.models import (
    Company,
    Dataset,
    DatasetRelationship,
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

_ADDITIVE_FIELDS = frozenset(
    {"total_amount", "quantity", "unit_price", "inventory_level"}
)


@dataclass(frozen=True, slots=True)
class TenantAnalyticsSnapshot:
    company: Company | None
    datasets: tuple[Dataset, ...]
    statuses: tuple[str, ...]
    prepared: tuple[PreparedCompanyDataset, ...]
    relationships: tuple[DatasetRelationship, ...]
    active_models: tuple[ModelRegistry, ...]
    capabilities: frozenset[str]
    status: str

    @property
    def currency(self) -> str:
        return self.company.currency_code if self.company is not None else "USD"

    def source_for(self, required_fields: frozenset[str]) -> PreparedCompanyDataset | None:
        candidates = [
            (item, self._with_derived_revenue(self._compose_from(item)))
            for item in self.prepared
        ]
        usable = [
            (anchor, composed)
            for anchor, composed in candidates
            if required_fields <= set(composed.canonical_columns.values())
        ]
        selected = max(
            usable,
            key=lambda pair: (
                len(required_fields & set(pair[0].canonical_columns.values())),
                sum(
                    required <= set(pair[1].canonical_columns.values())
                    for required in BUSINESS_METRIC_FIELDS.values()
                ),
                len(pair[1].canonical_columns),
                len(pair[1].rows),
            ),
            default=None,
        )
        return selected[1] if selected is not None else None

    @staticmethod
    def _with_derived_revenue(
        prepared: PreparedCompanyDataset,
    ) -> PreparedCompanyDataset:
        reverse = {
            canonical: original
            for original, canonical in prepared.canonical_columns.items()
        }
        if "total_amount" in reverse:
            return prepared
        quantity_column = reverse.get("quantity")
        price_column = reverse.get("unit_price")
        if quantity_column is None or price_column is None:
            return prepared

        derived_column = "__avenqo_total_amount"
        rows: list[dict[str, object]] = []
        for row in prepared.rows:
            output = dict(row)
            try:
                output[derived_column] = float(row[quantity_column]) * float(
                    row[price_column]
                )
            except (KeyError, TypeError, ValueError):
                output[derived_column] = None
            rows.append(output)
        return PreparedCompanyDataset(
            company_id=prepared.company_id,
            dataset_id=prepared.dataset_id,
            version=prepared.version,
            canonical_columns={
                **prepared.canonical_columns,
                derived_column: "total_amount",
            },
            rows=tuple(rows),
            profile=prepared.profile,
            mapping=prepared.mapping,
            cleaning_report=prepared.cleaning_report,
            quality=prepared.quality,
            capability_readiness=prepared.capability_readiness,
        )

    def _compose_from(self, anchor: PreparedCompanyDataset) -> PreparedCompanyDataset:
        prepared_by_id = {item.dataset_id: item for item in self.prepared}
        included = {anchor.dataset_id}
        rows = self._canonical_rows(anchor)
        fields = set(anchor.canonical_columns.values())
        enriched = False

        while True:
            best: tuple[DatasetRelationship, PreparedCompanyDataset, int] | None = None
            for relationship in self.relationships:
                if relationship.left_dataset_id in included:
                    other_id = relationship.right_dataset_id
                elif relationship.right_dataset_id in included:
                    other_id = relationship.left_dataset_id
                else:
                    continue
                if other_id in included or other_id not in prepared_by_id:
                    continue
                other = prepared_by_id[other_id]
                added = len(set(other.canonical_columns.values()) - fields)
                if added and (best is None or added > best[2]):
                    best = relationship, other, added
            if best is None:
                break

            relationship, other, _ = best
            other_rows = self._canonical_rows(other)
            join_field = relationship.canonical_field
            lookup: dict[str, dict[str, object]] = {}
            duplicate = False
            for row in other_rows:
                key = self._join_key(row.get(join_field))
                if key is None:
                    continue
                if key in lookup:
                    duplicate = True
                    break
                lookup[key] = row
            if duplicate or not lookup or join_field not in fields:
                included.add(other.dataset_id)
                continue

            join_keys = [
                key
                for row in rows
                if (key := self._join_key(row.get(join_field))) is not None
            ]
            added_fields = set(other.canonical_columns.values()) - fields
            if len(join_keys) != len(set(join_keys)):
                added_fields -= _ADDITIVE_FIELDS
            if not added_fields:
                included.add(other.dataset_id)
                continue

            rows = tuple(
                {
                    **row,
                    **{
                        field: value
                        for field, value in lookup.get(self._join_key(row.get(join_field)) or "", {}).items()
                        if field in added_fields
                    },
                }
                for row in rows
            )
            fields.update(added_fields)
            included.add(other.dataset_id)
            enriched = True

        if not enriched:
            return anchor
        return PreparedCompanyDataset(
            company_id=anchor.company_id,
            dataset_id=anchor.dataset_id,
            version=anchor.version,
            canonical_columns={field: field for field in fields},
            rows=rows,
            profile=anchor.profile,
            mapping=anchor.mapping,
            cleaning_report=anchor.cleaning_report,
            quality=anchor.quality,
            capability_readiness=anchor.capability_readiness,
        )

    @staticmethod
    def _canonical_rows(prepared: PreparedCompanyDataset) -> tuple[dict[str, object], ...]:
        reverse = {canonical: original for original, canonical in prepared.canonical_columns.items()}
        return tuple(
            {
                canonical: row[original]
                for canonical, original in reverse.items()
                if original in row
            }
            for row in prepared.rows
        )

    @staticmethod
    def _join_key(value: object | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().casefold()
        return normalized or None


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
        relationships = tuple(
            self._session.scalars(
                select(DatasetRelationship).where(
                    DatasetRelationship.company_id == tenant.company_id,
                    DatasetRelationship.left_dataset_id.in_(prepared_ids),
                    DatasetRelationship.right_dataset_id.in_(prepared_ids),
                )
            ).all()
        ) if prepared_ids else ()
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
        snapshot = TenantAnalyticsSnapshot(
            company=company,
            datasets=datasets,
            statuses=statuses,
            prepared=prepared,
            relationships=relationships,
            active_models=active_models,
            capabilities=frozenset(),
            status=self._status(datasets, statuses, prepared),
        )
        return replace(
            snapshot,
            capabilities=frozenset(self._capabilities(snapshot, active_models)),
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
        snapshot: TenantAnalyticsSnapshot,
        active_models: tuple[ModelRegistry, ...],
    ) -> set[str]:
        capabilities = {model.task_code for model in active_models}
        capabilities.update(
            key
            for key, required in BUSINESS_METRIC_FIELDS.items()
            if snapshot.source_for(required) is not None
        )
        for dataset in snapshot.prepared:
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