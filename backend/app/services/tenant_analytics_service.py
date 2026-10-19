from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.models import (
    Company,
    CommerceConnection,
    CommerceWebhookReceipt,
    Dataset,
    DatasetRelationship,
    DatasetStatus,
    JobStatus,
    ModelRegistry,
    TrainingJob,
)
from backend.app.routers.datasets import _pipeline_status, _training_status
from backend.app.services import retail_kpi_cache
from backend.app.services.company_dataset_ingestion_service import CompanyDatasetIngestionService
from backend.app.services.commerce_normalized_source import (
    prepared_from_normalized_connection,
    try_restore_connector_retail_dataset,
)
from backend.app.services.retail_source_service import RetailSourceService
from backend.app.models import CommerceConnectionStatus
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

# Large imports must never be fully reconstructed inside an API request. For
# business analytics we read fixed-size summaries prepared by a background worker.
_DASHBOARD_MAX_PREPARED_ROWS = 50_000
_log = logging.getLogger(__name__)


def _safe_float(value: object | None, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value))


@dataclass(frozen=True, slots=True)
class TenantAnalyticsSnapshot:
    company: Company | None
    datasets: tuple[Dataset, ...]
    statuses: tuple[str, ...]
    training_statuses: tuple[str, ...]
    prepared: tuple[PreparedCompanyDataset, ...]
    relationships: tuple[DatasetRelationship, ...]
    active_models: tuple[ModelRegistry, ...]
    capabilities: frozenset[str]
    status: str
    deferred_dataset_ids: frozenset[object] = frozenset()
    retail_summaries: tuple[dict, ...] = ()
    retail_states: tuple[str, ...] = ()
    active_source_selected: bool = False
    active_source_dataset_id: object | None = None
    active_source_provider: str | None = None
    active_source_type: str | None = None
    active_source_name: str | None = None
    active_source_last_updated_at: datetime | None = None
    active_source_last_event_received_at: datetime | None = None
    allow_multi_currency: bool = False

    @property
    def currency(self) -> str:
        return self.company.currency_code if self.company is not None else "USD"

    def source_for(
        self,
        required_fields: frozenset[str],
        *,
        convert_currencies: bool = False,
    ) -> PreparedCompanyDataset | None:
        candidates = [
            (item, self._with_derived_revenue(self._compose_from(item)))
            for item in self.prepared
        ]
        usable = [
            (anchor, composed)
            for anchor, composed in candidates
            if required_fields <= set(composed.canonical_columns.values())
        ]
        if not usable:
            return None

        def score(pair):
            return (
                sum(
                    required <= set(pair[1].canonical_columns.values())
                    for required in BUSINESS_METRIC_FIELDS.values()
                ),
                len(pair[1].canonical_columns),
                len(pair[1].rows),
            )

        compatible_ids = {anchor.dataset_id for anchor, _ in usable}
        graph: dict[object, set[object]] = {
            dataset_id: set() for dataset_id in compatible_ids
        }
        for relationship in self.relationships:
            left, right = relationship.left_dataset_id, relationship.right_dataset_id
            if left in compatible_ids and right in compatible_ids:
                graph[left].add(right)
                graph[right].add(left)

        component_by_id: dict[object, int] = {}
        component_index = 0
        for dataset_id in graph:
            if dataset_id in component_by_id:
                continue
            pending = [dataset_id]
            component_by_id[dataset_id] = component_index
            while pending:
                current = pending.pop()
                for related in graph[current]:
                    if related not in component_by_id:
                        component_by_id[related] = component_index
                        pending.append(related)
            component_index += 1

        best_by_component: dict[int, tuple[PreparedCompanyDataset, PreparedCompanyDataset]] = {}
        for pair in usable:
            component = component_by_id[pair[0].dataset_id]
            if component not in best_by_component or score(pair) > score(best_by_component[component]):
                best_by_component[component] = pair
        components = [pair[1] for pair in best_by_component.values()]
        selected = max(components, key=lambda item: (
            sum(required <= set(item.canonical_columns.values()) for required in BUSINESS_METRIC_FIELDS.values()),
            len(item.canonical_columns),
            len(item.rows),
        ))
        if not (convert_currencies or self.allow_multi_currency) and ("total_amount" in required_fields or "unit_price" in required_fields):
            currencies = {
                str(row["currency"]).upper()
                for item in components
                for row in self._canonical_rows(item)
                if row.get("currency")
            }
            if len(currencies) > 1:
                raise ValueError("INCOMPATIBLE_SOURCE_CURRENCIES")

        if len(components) == 1:
            return selected

        canonical_fields = set().union(
            *(set(item.canonical_columns.values()) for item in components)
        )
        canonical_fields.update({
            "net_amount",
            "source_currency",
            "source_total_amount",
            "source_refund_amount",
            "exchange_rate",
        })
        from backend.app.services.currency_service import CurrencyService

        currency_service = CurrencyService()
        base_currency = self.currency

        reconciled_rows: list[dict[str, object]] = []
        seen_rows: set[tuple[tuple[str, str], ...]] = set()
        seen_commerce: set[tuple] = set()
        for item in components:
            for row in self._canonical_rows(item):
                normalized = {field: row.get(field) for field in canonical_fields if field in row}
                provider = row.get("source_provider")
                store = row.get("source_store") or row.get("source_connection_id")
                record = row.get("source_order_id") or row.get("shopify_order_gid")
                line = row.get("source_line_item_id") or row.get("shopify_line_item_gid")
                if provider and store and record:
                    identity = (str(provider), str(store), str(record), str(line or ""))
                    if identity in seen_commerce:
                        continue
                    seen_commerce.add(identity)

                row_currency = str(row.get("currency") or base_currency).strip().upper()
                if row_currency != base_currency:
                    normalized["source_currency"] = row_currency
                    rate = float(currency_service.get_rate(row_currency, base_currency))
                    normalized["exchange_rate"] = rate
                    if "total_amount" in row and row["total_amount"] is not None:
                        try:
                            s_amt = _safe_float(row["total_amount"])
                            normalized["source_total_amount"] = s_amt
                            normalized["total_amount"] = round(s_amt * rate, 2)
                        except (ValueError, TypeError):
                            pass
                    if "unit_price" in row and row["unit_price"] is not None:
                        try:
                            normalized["unit_price"] = round(_safe_float(row["unit_price"]) * rate, 2)
                        except (ValueError, TypeError):
                            pass
                    if "discount_amount" in row and row["discount_amount"] is not None:
                        try:
                            normalized["discount_amount"] = round(_safe_float(row["discount_amount"]) * rate, 2)
                        except (ValueError, TypeError):
                            pass
                    if "refund_amount" in row and row["refund_amount"] is not None:
                        try:
                            s_ref = _safe_float(row["refund_amount"])
                            normalized["source_refund_amount"] = s_ref
                            normalized["refund_amount"] = round(s_ref * rate, 2)
                        except (ValueError, TypeError):
                            pass
                    normalized["currency"] = base_currency
                else:
                    normalized["currency"] = base_currency
                    normalized["exchange_rate"] = 1.0

                if "total_amount" in normalized and normalized["total_amount"] is not None:
                    try:
                        tot = _safe_float(normalized["total_amount"])
                        disc = _safe_float(normalized.get("discount_amount"), 0.0)
                        ref = _safe_float(normalized.get("refund_amount"), 0.0)
                        normalized["net_amount"] = round(tot - disc - ref, 2)
                    except (ValueError, TypeError):
                        pass

                fingerprint = tuple(
                    sorted((field, repr(value)) for field, value in normalized.items())
                )
                if fingerprint in seen_rows:
                    continue
                seen_rows.add(fingerprint)
                reconciled_rows.append(normalized)
        return PreparedCompanyDataset(
            company_id=selected.company_id,
            dataset_id=selected.dataset_id,
            version=selected.version,
            canonical_columns={field: field for field in canonical_fields},
            rows=tuple(reconciled_rows),
            profile=selected.profile,
            mapping=selected.mapping,
            cleaning_report=selected.cleaning_report,
            quality=selected.quality,
            capability_readiness=selected.capability_readiness,
        )

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
                output[derived_column] = _safe_float(row[quantity_column]) * _safe_float(
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
    """Loads shared, tenant-scoped analytics inputs without unbounded API memory."""

    def __init__(self, session: Session, ingestion: CompanyDatasetIngestionService) -> None:
        self._session = session
        self._ingestion = ingestion

    def load(self, tenant: TenantContext) -> TenantAnalyticsSnapshot:
        # All request-time business analytics use the same bounded path. Large
        # datasets use persisted KPI summaries; missing summaries are queued for
        # background preparation without loading source rows in the request.
        return self._load(tenant, max_prepared_rows=_DASHBOARD_MAX_PREPARED_ROWS)

    def load_for_dashboard(self, tenant: TenantContext) -> TenantAnalyticsSnapshot:
        return self._load(tenant, max_prepared_rows=_DASHBOARD_MAX_PREPARED_ROWS)

    def _load(
        self,
        tenant: TenantContext,
        *,
        max_prepared_rows: int | None = None,
    ) -> TenantAnalyticsSnapshot:
        company = self._session.scalar(select(Company).where(Company.id == tenant.company_id))
        datasets = tuple(
            self._session.scalars(
                select(Dataset)
                .where(Dataset.company_id == tenant.company_id)
                .options(selectinload(Dataset.training_jobs), selectinload(Dataset.versions), selectinload(Dataset.mapping))
                .order_by(Dataset.uploaded_at.desc())
            ).all()
        )
        tenant_datasets = datasets
        active_source = RetailSourceService(self._session).active_selection(tenant)
        active_source_provider = None
        active_source_name = None
        active_source_last_updated_at = None
        active_source_last_event_received_at = None
        active_source_type = active_source.source_type if active_source is not None else None
        if active_source is not None and active_source.connection_id is not None:
            connection = self._session.get(CommerceConnection, active_source.connection_id)
            active_source_provider = connection.provider if connection is not None else None
            active_source_name = connection.display_name if connection is not None else None
            active_source_last_updated_at = connection.last_successful_sync if connection is not None else None
            if connection is not None:
                active_source_last_event_received_at = self._session.scalar(
                    select(CommerceWebhookReceipt.created_at)
                    .where(
                        CommerceWebhookReceipt.company_id == tenant.company_id,
                        CommerceWebhookReceipt.connection_id == connection.id,
                        CommerceWebhookReceipt.status == "PROCESSED",
                        CommerceWebhookReceipt.processed_at.is_not(None),
                    )
                    .order_by(CommerceWebhookReceipt.created_at.desc())
                    .limit(1)
                )
        elif active_source is not None and active_source.source_type == "dataset":
            selected_dataset = next(
                (item for item in datasets if item.id == active_source.dataset_id), None
            )
            active_source_name = selected_dataset.name if selected_dataset is not None else None
            active_source_last_updated_at = selected_dataset.uploaded_at if selected_dataset is not None else None
        elif active_source is not None and active_source.source_type == "all":
            active_source_name = "all_active"
            active_sources = [
                item
                for item in RetailSourceService(self._session).list_sources(tenant)
                if item.enabled and item.status.upper() == "READY"
            ]
            source_updates = [
                item.last_synchronized_at
                for item in active_sources
                if item.last_synchronized_at is not None
            ]
            active_source_last_updated_at = min(source_updates) if source_updates else None
        source_datasets = datasets
        enabled_dataset_ids = RetailSourceService(self._session).enabled_dataset_ids(tenant)
        if tenant.user_id is not None and active_source is not None and active_source.source_type != "all":
            if active_source.source_type == "custom_set":
                selected_ds_ids = set(getattr(active_source, "dataset_ids", []) or [])
                selected_conn_ids = set(getattr(active_source, "connection_ids", []) or [])
                for cid in selected_conn_ids:
                    conn = self._session.get(CommerceConnection, cid)
                    if conn is not None and conn.company_id == tenant.company_id:
                        ds_id = RetailSourceService._connection_dataset_id(conn)
                        if ds_id:
                            selected_ds_ids.add(ds_id)
                source_datasets = tuple(dataset for dataset in datasets if dataset.id in selected_ds_ids)
                datasets = source_datasets
            else:
                selected_id = active_source.dataset_id
                if active_source.connection_id is not None:
                    connection = self._session.scalar(select(CommerceConnection).where(CommerceConnection.id == active_source.connection_id, CommerceConnection.company_id == tenant.company_id))
                    if connection is not None and connection.status != CommerceConnectionStatus.DISCONNECTED.value:
                        source_service = RetailSourceService(self._session)
                        if not source_service._connector_artifact_ready(connection):
                            restored = try_restore_connector_retail_dataset(
                                self._session, self._ingestion, tenant, connection
                            )
                            if restored is not None:
                                self._session.refresh(connection)
                                datasets = tuple(
                                    self._session.scalars(
                                        select(Dataset)
                                        .where(Dataset.company_id == tenant.company_id)
                                        .options(
                                            selectinload(Dataset.training_jobs),
                                            selectinload(Dataset.versions),
                                            selectinload(Dataset.mapping),
                                        )
                                        .order_by(Dataset.uploaded_at.desc())
                                    ).all()
                                )
                        selected_id = RetailSourceService._connection_dataset_id(connection)
                    else:
                        selected_id = None
                source_datasets = tuple(dataset for dataset in datasets if dataset.id == selected_id)
                datasets = source_datasets
        elif enabled_dataset_ids is not None:
            source_datasets = tuple(
                dataset for dataset in datasets if dataset.id in enabled_dataset_ids
            )
        elif active_source is not None and active_source.source_type != "all":
            source_datasets = tuple(
                dataset
                for dataset in datasets
                if dataset.id == active_source.dataset_id
            )
            datasets = source_datasets
        statuses = tuple(_pipeline_status(dataset) for dataset in tenant_datasets)
        training_statuses = tuple(
            status
            for dataset in tenant_datasets
            if (status := _training_status(dataset)) is not None and status != "not_applicable"
        )
        source_statuses = tuple(
            _pipeline_status(dataset) for dataset in source_datasets
        )
        prepared, deferred_dataset_ids, summaries, retail_states = self._prepared_ready_datasets(
            tenant, source_datasets, max_prepared_rows=max_prepared_rows
        )
        prepared_ids = {item.dataset_id for item in prepared if item is not None}
        candidate_conn_ids: list[UUID] = []
        if active_source is not None:
            if getattr(active_source, "source_type", None) == "single":
                conn_id = getattr(active_source, "connection_id", None)
                if conn_id is not None:
                    candidate_conn_ids = [conn_id]
            elif getattr(active_source, "source_type", None) == "custom_set":
                candidate_conn_ids = list(getattr(active_source, "connection_ids", []) or [])
            elif getattr(active_source, "source_type", None) == "all":
                conns = self._session.scalars(
                    select(CommerceConnection.id).where(
                        CommerceConnection.company_id == tenant.company_id,
                        CommerceConnection.status != CommerceConnectionStatus.DISCONNECTED.value,
                    )
                ).all()
                candidate_conn_ids = list(conns)

        fallback_list = list(prepared)
        for cid in candidate_conn_ids:
            conn = self._session.get(CommerceConnection, cid)
            if conn is not None and conn.company_id == tenant.company_id and conn.status != CommerceConnectionStatus.DISCONNECTED.value:
                ds_id = RetailSourceService._connection_dataset_id(conn) or conn.id
                if ds_id not in prepared_ids:
                    fb = prepared_from_normalized_connection(self._session, tenant, conn, ds_id)
                    if fb is not None:
                        fallback_list.append(fb)
                        prepared_ids.add(ds_id)
        prepared = tuple(fallback_list)
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
        status = self._status(
            tenant_datasets, statuses, prepared, deferred_dataset_ids
        )
        if tenant.user_id is not None and active_source is not None and active_source.source_type != "all" and not source_datasets and not prepared:
            status = "source_unavailable"
        if enabled_dataset_ids == frozenset() and not retail_states:
            status = "no_data"
        if retail_states:
            if summaries or prepared:
                status = "partial_ready" if deferred_dataset_ids or any(s != "ready" for s in source_statuses) else "ready"
            else:
                status = "source_unavailable" if "SOURCE_UNAVAILABLE" in retail_states else "processing"
        if tenant.user_id is not None and active_source is not None and active_source.source_type != "all" and not source_datasets and not prepared:
            status = "source_unavailable"
        snapshot = TenantAnalyticsSnapshot(
            company=company,
            datasets=datasets,
            statuses=statuses,
            training_statuses=training_statuses,
            prepared=prepared,
            relationships=relationships,
            active_models=active_models,
            capabilities=frozenset(),
            status=status,
            deferred_dataset_ids=frozenset(deferred_dataset_ids),
            retail_summaries=tuple(summaries),
            retail_states=tuple(retail_states),
            active_source_selected=active_source is not None,
            active_source_dataset_id=(
                active_source.dataset_id if active_source is not None else None
            ),
            active_source_provider=active_source_provider,
            active_source_type=active_source_type,
            active_source_name=active_source_name,
            active_source_last_updated_at=active_source_last_updated_at,
            active_source_last_event_received_at=active_source_last_event_received_at,
        )
        return replace(
            snapshot,
            capabilities=frozenset(self._capabilities(snapshot, active_models)),
        )

    def _prepared_ready_datasets(
        self,
        tenant: TenantContext,
        datasets: tuple[Dataset, ...],
        *,
        max_prepared_rows: int | None = None,
    ) -> tuple:
        result: list[PreparedCompanyDataset] = []
        summaries, retail_states = [], []
        deferred_dataset_ids: set[object] = set()
        for dataset in datasets:
            if dataset.status != DatasetStatus.READY or dataset.mapping is None:
                continue
            version = retail_kpi_cache.current_version(dataset)
            row_count = version.row_count if version and version.row_count is not None else dataset.rows_count
            if max_prepared_rows is not None and int(row_count or 0) > max_prepared_rows:
                state, summary = retail_kpi_cache.read_or_schedule(tenant, dataset)
                retail_states.append(state)
                if summary is not None:
                    summaries.append(summary)
                else:
                    deferred_dataset_ids.add(dataset.id)
                continue
            try:
                prep = self._ingestion.get_prepared_dataset(tenant, dataset.id)
                if prep is None:
                    raise FileNotFoundError(f"Prepared dataset {dataset.id} unavailable on disk")
                result.append(prep)
            except Exception:
                fallback = self._prepared_from_connector_records(tenant, dataset.id)
                if fallback is not None:
                    result.append(fallback)
                    continue
                _log.exception(
                    "Tenant analytics dataset unavailable endpoint=/api/v1/dashboard "
                    "status=degraded tenant=%s dataset=%s category=prepared_dataset_unavailable",
                    tenant.company_id,
                    dataset.id,
                )
                continue
        return tuple(result), deferred_dataset_ids, summaries, retail_states

    def _prepared_from_connector_records(
        self,
        tenant: TenantContext,
        dataset_id: object,
    ) -> PreparedCompanyDataset | None:
        connections = self._session.scalars(
            select(CommerceConnection).where(
                CommerceConnection.company_id == tenant.company_id,
                CommerceConnection.status != CommerceConnectionStatus.DISCONNECTED.value,
            )
        ).all()
        for connection in connections:
            if RetailSourceService._connection_dataset_id(connection) != dataset_id:
                continue
            prepared = prepared_from_normalized_connection(
                self._session,
                tenant,
                connection,
                dataset_id if isinstance(dataset_id, UUID) else None,
            )
            if prepared is not None:
                return prepared
        return None

    @staticmethod
    def _capabilities(
        snapshot: TenantAnalyticsSnapshot,
        active_models: tuple[ModelRegistry, ...],
    ) -> set[str]:
        capabilities = {model.task_code for model in active_models}
        for summary in snapshot.retail_summaries:
            capabilities.update(summary["current"])
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
        deferred_dataset_ids: set[object],
    ) -> str:
        if not datasets:
            return "no_data"
        if (prepared or deferred_dataset_ids) and any(status != "ready" for status in statuses):
            return "partial_ready"
        if prepared or deferred_dataset_ids:
            return "ready"
        if statuses and all(status == "failed" for status in statuses):
            return "error"
        return "processing"
