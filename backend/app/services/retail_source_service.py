from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import (
    CommerceConnection,
    CommerceConnectionStatus,
    Dataset,
    DatasetRelationship,
    DatasetStatus,
    RetailActiveSource,
    RetailSourceState,
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
    enabled: bool = False

    @property
    def id(self) -> UUID:
        return self.source_id


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
        states = {
            state.source_key: state.enabled
            for state in self._session.scalars(
                select(RetailSourceState).where(
                    RetailSourceState.company_id == tenant.company_id
                )
            ).all()
        }
        sources = [
            self._connection_source(connection, active)
            for connection in connections
        ]
        sources.extend(
            self._dataset_source(dataset, active)
            for dataset in datasets
            if dataset.id not in connector_dataset_ids
        )
        return tuple(
            replace(
                source,
                enabled=states.get(
                    self._source_key(source.source_type, source.source_id),
                    bool(
                        active
                        and (
                            active.source_type == "all"
                            or (
                                active.source_type == source.source_type
                                and (
                                    active.connection_id == source.connection_id
                                    if source.source_type == "connector"
                                    else active.dataset_id == source.dataset_id
                                )
                            )
                        )
                    ),
                ),
            )
            for source in sources
        )

    def set_source_enabled(
        self,
        tenant: TenantContext,
        *,
        source_type: str,
        source_id: UUID,
        enabled: bool,
    ) -> RetailSource:
        from backend.app.core.cache import tenant_cache

        source = next(
            (
                item
                for item in self.list_sources(tenant)
                if item.source_type == source_type and item.source_id == source_id
            ),
            None,
        )
        if source is None:
            raise RetailSourceNotFound("Retail source not found")

        states = list(
            self._session.scalars(
                select(RetailSourceState).where(
                    RetailSourceState.company_id == tenant.company_id
                )
            ).all()
        )
        state_by_key = {item.source_key: item for item in states}
        if not states:
            active = self._session.scalar(
                select(RetailActiveSource).where(
                    RetailActiveSource.company_id == tenant.company_id
                )
            )
            for existing_source in self.list_sources(tenant):
                source_key = self._source_key(
                    existing_source.source_type, existing_source.source_id
                )
                initially_enabled = bool(
                    active
                    and (
                        active.source_type == "all"
                        or existing_source.active
                    )
                )
                state = RetailSourceState(
                    company_id=tenant.company_id,
                    source_key=source_key,
                    dataset_id=existing_source.dataset_id,
                    connection_id=existing_source.connection_id,
                    enabled=initially_enabled,
                )
                self._session.add(state)
                state_by_key[source_key] = state

        key = self._source_key(source_type, source_id)
        state = state_by_key.get(key)
        if state is None:
            state = RetailSourceState(
                company_id=tenant.company_id,
                source_key=key,
                dataset_id=source.dataset_id,
                connection_id=source.connection_id,
                enabled=enabled,
            )
            self._session.add(state)
        else:
            state.enabled = enabled
        self._session.commit()
        tenant_cache.invalidate_tenant(tenant.company_id)
        return next(
            item
            for item in self.list_sources(tenant)
            if item.source_type == source_type and item.source_id == source_id
        )

    def enabled_dataset_ids(self, tenant: TenantContext) -> frozenset[UUID] | None:
        states = tuple(
            self._session.scalars(
                select(RetailSourceState).where(
                    RetailSourceState.company_id == tenant.company_id,
                    RetailSourceState.enabled.is_(True),
                )
            ).all()
        )
        has_state = self._session.scalar(
            select(RetailSourceState.id)
            .where(RetailSourceState.company_id == tenant.company_id)
            .limit(1)
        )
        if has_state is None:
            return None
        dataset_ids = {
            state.dataset_id
            for state in states
            if state.dataset_id is not None and state.connection_id is None
        }
        connection_ids = {state.connection_id for state in states if state.connection_id is not None}
        if connection_ids:
            dataset_ids.update(
                dataset_id
                for connection in self._session.scalars(
                    select(CommerceConnection).where(
                        CommerceConnection.company_id == tenant.company_id,
                        CommerceConnection.id.in_(connection_ids),
                        CommerceConnection.status
                        != CommerceConnectionStatus.DISCONNECTED.value,
                    )
                ).all()
                if (dataset_id := self._connection_dataset_id(connection)) is not None
            )
        return frozenset(dataset_ids)

    def select_source(
        self,
        tenant: TenantContext,
        *,
        source_type: str,
        source_id: UUID,
    ) -> RetailSource:
        from backend.app.core.cache import tenant_cache

        if source_type == "all":
            selection = self._store_selection(
                tenant,
                source_type="all",
                dataset_id=None,
                connection_id=None,
            )
            tenant_cache.invalidate_tenant(tenant.company_id)
            return RetailSource(
                source_type="all",
                source_id=source_id,
                dataset_id=None,
                connection_id=None,
                display_name="Toutes les sources",
                provider=None,
                status="ready",
                last_synchronized_at=None,
                active=True,
            )

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
            tenant_cache.invalidate_tenant(tenant.company_id)
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
            tenant_cache.invalidate_tenant(tenant.company_id)
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
        total_valid_sources = int(ready_connection is not None) + len(datasets)
        if total_valid_sources == 0:
            return None
        if total_valid_sources == 1:
            if ready_connection is not None:
                return self._store_selection(
                    tenant,
                    source_type="connector",
                    dataset_id=self._connection_dataset_id(ready_connection),
                    connection_id=ready_connection.id,
                )
            return self._store_selection(
                tenant,
                source_type="dataset",
                dataset_id=datasets[0].id,
                connection_id=None,
            )
        return self._store_selection(
            tenant,
            source_type="all",
            dataset_id=None,
            connection_id=None,
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
            # Selected connection is no longer present
            self._session.delete(selection)
            self._session.commit()
            return None
        elif (
            selection is not None
            and selection.source_type == "dataset"
        ):
            if selection.dataset_id in datasets_by_id:
                return selection
            # Selected dataset is no longer present
            self._session.delete(selection)
            self._session.commit()
            return None
        elif (
            selection is not None
            and selection.source_type == "all"
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
        # Zero silent fallback to datasets if commerce connections exist
        if not connections and datasets:
            has_relationships = self._session.scalar(
                select(DatasetRelationship.id).where(
                    DatasetRelationship.company_id == tenant.company_id
                ).limit(1)
            ) is not None
            if has_relationships:
                return self._store_selection(
                    tenant,
                    source_type="all",
                    dataset_id=None,
                    connection_id=None,
                )
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
    def _source_key(source_type: str, source_id: UUID) -> str:
        return f"{source_type}:{source_id}"

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