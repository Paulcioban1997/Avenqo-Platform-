from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import (
    CommerceConnection,
    CommerceConnectionStatus,
    Dataset,
    DatasetStatus,
    RetailActiveSource,
)
from shared.ai_engine.contracts import TenantContext


class RetailSourceNotFound(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RetailSource:
    source_type: str
    source_id: UUID
    dataset_id: UUID | None
    connection_id: UUID | None
    display_name: str
    provider: str | None
    status: str
    last_synchronized_at: datetime | None
    active: bool


class RetailSourceService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_sources(self, tenant: TenantContext) -> tuple[RetailSource, ...]:
        connections = tuple(
            self._session.scalars(
                select(CommerceConnection)
                .where(
                    CommerceConnection.company_id == tenant.company_id,
                    CommerceConnection.status
                    != CommerceConnectionStatus.DISCONNECTED.value,
                )
                .order_by(
                    CommerceConnection.last_successful_sync.desc(),
                    CommerceConnection.created_at.desc(),
                )
            ).all()
        )
        datasets = tuple(
            self._session.scalars(
                select(Dataset)
                .where(
                    Dataset.company_id == tenant.company_id,
                    Dataset.status == DatasetStatus.READY,
                )
                .order_by(Dataset.uploaded_at.desc())
            ).all()
        )
        connector_dataset_ids = {
            dataset_id
            for connection in connections
            if (dataset_id := self._connection_dataset_id(connection)) is not None
        }
        active = self._resolve_active(tenant, connections, datasets)
        sources = [
            self._connection_source(connection, active)
            for connection in connections
        ]
        sources.extend(
            self._dataset_source(dataset, active)
            for dataset in datasets
            if dataset.id not in connector_dataset_ids
        )
        return tuple(sources)

    def select_source(
        self,
        tenant: TenantContext,
        *,
        source_type: str,
        source_id: UUID,
    ) -> RetailSource:
        if source_type == "connector":
            connection = self._session.scalar(
                select(CommerceConnection).where(
                    CommerceConnection.id == source_id,
                    CommerceConnection.company_id == tenant.company_id,
                    CommerceConnection.status
                    != CommerceConnectionStatus.DISCONNECTED.value,
                )
            )
            if connection is None:
                raise RetailSourceNotFound("Retail source not found")
            selection = self._store_selection(
                tenant,
                source_type="connector",
                dataset_id=self._connection_dataset_id(connection),
                connection_id=connection.id,
            )
            return self._connection_source(connection, selection)
        if source_type == "dataset":
            dataset = self._session.scalar(
                select(Dataset).where(
                    Dataset.id == source_id,
                    Dataset.company_id == tenant.company_id,
                    Dataset.status == DatasetStatus.READY,
                )
            )
            if dataset is None:
                raise RetailSourceNotFound("Retail source not found")
            selection = self._store_selection(
                tenant,
                source_type="dataset",
                dataset_id=dataset.id,
                connection_id=None,
            )
            return self._dataset_source(dataset, selection)
        raise RetailSourceNotFound("Retail source not found")

    def active_selection(self, tenant: TenantContext) -> RetailActiveSource | None:
        selection = self._session.scalar(
            select(RetailActiveSource).where(
                RetailActiveSource.company_id == tenant.company_id
            )
        )
        if selection is not None:
            self.list_sources(tenant)
            return self._session.scalar(
                select(RetailActiveSource).where(
                    RetailActiveSource.company_id == tenant.company_id
                )
            )
        ready_connection = self._session.scalar(
            select(CommerceConnection)
            .where(
                CommerceConnection.company_id == tenant.company_id,
                CommerceConnection.status == CommerceConnectionStatus.READY.value,
            )
            .order_by(
                CommerceConnection.last_successful_sync.desc(),
                CommerceConnection.created_at.desc(),
            )
        )
        if ready_connection is None:
            return None
        return self._store_selection(
            tenant,
            source_type="connector",
            dataset_id=self._connection_dataset_id(ready_connection),
            connection_id=ready_connection.id,
        )

    def _resolve_active(
        self,
        tenant: TenantContext,
        connections: tuple[CommerceConnection, ...],
        datasets: tuple[Dataset, ...],
    ) -> RetailActiveSource | None:
        selection = self._session.scalar(
            select(RetailActiveSource).where(
                RetailActiveSource.company_id == tenant.company_id
            )
        )
        connections_by_id = {item.id: item for item in connections}
        datasets_by_id = {item.id: item for item in datasets}
        if selection is not None and selection.source_type == "connector":
            connection = connections_by_id.get(selection.connection_id)
            if connection is not None:
                current_dataset_id = self._connection_dataset_id(connection)
                if selection.dataset_id != current_dataset_id:
                    selection.dataset_id = current_dataset_id
                    self._session.commit()
                return selection
        elif (
            selection is not None
            and selection.source_type == "dataset"
            and selection.dataset_id in datasets_by_id
        ):
            return selection

        ready_connections = [
            item
            for item in connections
            if item.status == CommerceConnectionStatus.READY.value
        ]
        if ready_connections:
            connection = ready_connections[0]
            return self._store_selection(
                tenant,
                source_type="connector",
                dataset_id=self._connection_dataset_id(connection),
                connection_id=connection.id,
            )
        if datasets:
            return self._store_selection(
                tenant,
                source_type="dataset",
                dataset_id=datasets[0].id,
                connection_id=None,
            )
        if selection is not None:
            self._session.delete(selection)
            self._session.commit()
        return None

    def _store_selection(
        self,
        tenant: TenantContext,
        *,
        source_type: str,
        dataset_id: UUID | None,
        connection_id: UUID | None,
    ) -> RetailActiveSource:
        selection = self._session.scalar(
            select(RetailActiveSource).where(
                RetailActiveSource.company_id == tenant.company_id
            )
        )
        if selection is None:
            selection = RetailActiveSource(
                company_id=tenant.company_id,
                source_type=source_type,
            )
            self._session.add(selection)
        selection.source_type = source_type
        selection.dataset_id = dataset_id
        selection.connection_id = connection_id
        self._session.commit()
        return selection

    @staticmethod
    def _connection_dataset_id(connection: CommerceConnection) -> UUID | None:
        raw_value = (connection.dataset_ids or {}).get("retail")
        if not raw_value:
            return None
        try:
            return UUID(str(raw_value))
        except ValueError:
            return None

    def _connection_source(
        self,
        connection: CommerceConnection,
        active: RetailActiveSource | None,
    ) -> RetailSource:
        return RetailSource(
            source_type="connector",
            source_id=connection.id,
            dataset_id=self._connection_dataset_id(connection),
            connection_id=connection.id,
            display_name=connection.display_name or connection.external_account_id,
            provider=connection.provider,
            status=connection.status,
            last_synchronized_at=connection.last_successful_sync,
            active=bool(
                active
                and active.source_type == "connector"
                and active.connection_id == connection.id
            ),
        )

    @staticmethod
    def _dataset_source(
        dataset: Dataset,
        active: RetailActiveSource | None,
    ) -> RetailSource:
        return RetailSource(
            source_type="dataset",
            source_id=dataset.id,
            dataset_id=dataset.id,
            connection_id=None,
            display_name=dataset.name,
            provider=None,
            status=dataset.status.value,
            last_synchronized_at=dataset.uploaded_at,
            active=bool(
                active
                and active.source_type == "dataset"
                and active.dataset_id == dataset.id
            ),
        )