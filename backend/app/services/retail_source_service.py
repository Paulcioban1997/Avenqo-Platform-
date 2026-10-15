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
    UserSourceSelection,
)
from backend.app.services.commerce_normalized_source import (
    connection_has_normalized_records,
)
from shared.ai_engine.contracts import TenantContext


class RetailSourceNotFound(ValueError):
    pass


class CrossTenantSourceAccessDenied(PermissionError):
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
        active = self._user_selection(tenant) or self._resolve_active(TenantContext(tenant.company_id), connections, datasets)
        activation_default = self._session.scalar(select(RetailActiveSource).where(RetailActiveSource.company_id == tenant.company_id))
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
                        activation_default is None
                        or (activation_default.source_type or "").lower() == "all"
                        or (
                            getattr(activation_default, "selection_mode", "") == "CUSTOM_SET"
                            and str(source.source_id) in (getattr(activation_default, "selected_source_ids", None) or [])
                        )
                        or (
                            activation_default.source_type == source.source_type
                            and (
                                activation_default.connection_id == source.connection_id
                                if source.source_type == "connector"
                                else activation_default.dataset_id == source.dataset_id
                            )
                        )
                        or (
                            getattr(activation_default, "selection_mode", "") == "SINGLE"
                            and (
                                activation_default.connection_id == source.connection_id
                                if source.source_type == "connector"
                                else activation_default.dataset_id == source.dataset_id
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
                source_id=source_id or UUID(int=0),
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
            if tenant.user_id is not None and not self._connector_is_readable(connection):
                raise RetailSourceNotFound("Retail source is unavailable")
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
            if tenant.user_id is not None and self._dataset_source(dataset, None).status.upper() != "READY":
                raise RetailSourceNotFound("Retail source is unavailable")
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
        user_selection = self._user_selection(tenant)
        if user_selection is not None:
            return user_selection
        if tenant.user_id is not None:
            inherited = self._session.scalar(select(RetailActiveSource).where(RetailActiveSource.company_id == tenant.company_id))
            if inherited is None:
                inherited = self.active_selection(TenantContext(tenant.company_id))
            if inherited is not None:
                return self._store_selection(tenant, source_type=inherited.source_type, dataset_id=inherited.dataset_id, connection_id=inherited.connection_id)
            return None
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
            and selection.source_type.lower() in ("all", "custom", "custom_set", "single")
        ):
            return selection

        ready_connections = [
            item
            for item in connections
            if item.status == CommerceConnectionStatus.READY.value
        ]
        if len(ready_connections) + len(datasets) > 1:
            return self._store_selection(
                tenant,
                source_type="all",
                dataset_id=None,
                connection_id=None,
            )
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
        if tenant.user_id is not None:
            selection = self._user_selection(tenant)
            if selection is None:
                selection = UserSourceSelection(company_id=tenant.company_id, user_id=tenant.user_id, source_type=source_type)
                self._session.add(selection)
            selection.source_type = source_type
            selection.dataset_id = dataset_id
            selection.connection_id = connection_id
            self._session.commit()
            return selection
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

    def _user_selection(self, tenant: TenantContext):
        if tenant.user_id is None:
            return None
        return self._session.get(UserSourceSelection, (tenant.company_id, tenant.user_id))

    def context(self, tenant: TenantContext) -> dict:
        selection = self.active_selection(tenant)
        sources = self.list_sources(tenant)
        if selection is None:
            return {"state": "NO_SOURCES", "source_type": None, "source_id": None, "sources": sources}
        if selection.source_type == "all":
            return {"state": "READY" if any(source.enabled and source.status.upper() == "READY" for source in sources) else "NO_SOURCES", "source_type": "all", "source_id": None, "sources": sources}
        source_id = selection.connection_id if selection.source_type == "connector" else selection.dataset_id
        source = next((item for item in sources if item.source_type == selection.source_type and item.source_id == source_id), None)
        readable = source is not None and source.status.upper() == "READY" and (
            source.dataset_id is not None or selection.source_type == "connector"
        )
        state = "READY" if readable else "SOURCE_UNAVAILABLE"
        reauthorization_required = False
        reauthorization_provider = None
        reauthorization_shop = None
        if selection.source_type == "connector":
            connection = self._session.scalar(select(CommerceConnection).where(CommerceConnection.id == selection.connection_id, CommerceConnection.company_id == tenant.company_id))
            if connection is not None and connection.status == "DISCONNECTED":
                state = "SOURCE_DISCONNECTED"
            elif connection is not None and connection.status == CommerceConnectionStatus.REAUTH_REQUIRED.value:
                reauthorization_required = True
                reauthorization_provider = connection.provider
                reauthorization_shop = connection.external_account_id
                if not readable:
                    state = "SOURCE_ERROR"
            elif connection is not None and connection.status in {"ERROR", "FAILED"}:
                state = "SOURCE_ERROR"
        return {
            "state": state,
            "source_type": selection.source_type,
            "source_id": source_id,
            "sources": sources,
            "reauthorization_required": reauthorization_required,
            "reauthorization_provider": reauthorization_provider,
            "reauthorization_shop": reauthorization_shop,
            "authorize_path": (
                f"/api/v1/connectors/{reauthorization_provider}/authorize"
                if reauthorization_provider
                else None
            ),
        }

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

    def _connector_artifact_ready(self, connection: CommerceConnection) -> bool:
        dataset_id = self._connection_dataset_id(connection)
        if dataset_id is None:
            return False
        dataset = self._session.scalar(
            select(Dataset).where(
                Dataset.id == dataset_id,
                Dataset.company_id == connection.company_id,
                Dataset.status == DatasetStatus.READY,
            )
        )
        return dataset is not None and self._dataset_source(dataset, None).status.upper() == "READY"

    def _connector_is_readable(self, connection: CommerceConnection) -> bool:
        if connection.status == CommerceConnectionStatus.DISCONNECTED.value:
            return False
        if self._connector_artifact_ready(connection):
            return True
        return connection_has_normalized_records(self._session, connection)

    def _connection_source(
        self,
        connection: CommerceConnection,
        active: UserSourceSelection | RetailActiveSource | None,
    ) -> RetailSource:
        if connection.status == CommerceConnectionStatus.DISCONNECTED.value:
            status = connection.status
        elif self._connector_is_readable(connection):
            status = "READY"
        elif connection.status == CommerceConnectionStatus.READY.value:
            status = "SOURCE_UNAVAILABLE"
        else:
            status = connection.status
        return RetailSource(
            source_type="connector",
            source_id=connection.id,
            dataset_id=self._connection_dataset_id(connection),
            connection_id=connection.id,
            display_name=connection.display_name or connection.external_account_id,
            provider=connection.provider,
            status=status,
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
        active: UserSourceSelection | RetailActiveSource | None,
    ) -> RetailSource:
        from pathlib import Path
        version = next((version for version in dataset.versions if version.is_current), None)
        unavailable = bool(version and version.artifact_path and not Path(version.artifact_path).is_file())
        return RetailSource(
            source_type="dataset",
            source_id=dataset.id,
            dataset_id=dataset.id,
            connection_id=None,
            display_name=dataset.name,
            provider=None,
            status="SOURCE_UNAVAILABLE" if unavailable else dataset.status.value,
            last_synchronized_at=dataset.uploaded_at,
            active=bool(
                active
                and active.source_type == "dataset"
                and active.dataset_id == dataset.id
            ),
        )

    def get_workspace_selection(self, tenant: TenantContext) -> dict:
        """Retourne la configuration multi-sources actuelle de l'entreprise."""
        available = self.list_sources(tenant)
        active = self._session.scalar(
            select(RetailActiveSource).where(
                RetailActiveSource.company_id == tenant.company_id
            )
        )
        mode = "ALL"
        raw_selected_ids: set[str] = set()

        if active is not None:
            mode = getattr(active, "selection_mode", "ALL")
            if mode == "ALL":
                raw_selected_ids = {
                    str(s.source_id) for s in available
                    if s.enabled and s.status.upper() != CommerceConnectionStatus.DISCONNECTED.value
                }
            elif mode == "CUSTOM_SET":
                raw_selected_ids = set(getattr(active, "selected_source_ids", None) or [])
            elif mode == "SINGLE":
                single_id = active.connection_id or active.dataset_id
                if not single_id and getattr(active, "selected_source_ids", None):
                    single_id = active.selected_source_ids[0]
                if single_id:
                    raw_selected_ids = {str(single_id)}
        else:
            raw_selected_ids = {
                str(s.source_id) for s in available
                if s.enabled and s.status.upper() != CommerceConnectionStatus.DISCONNECTED.value
            }

        items = []
        selected_items = []
        selected_ids_list = []
        for s in available:
            is_sel = str(s.source_id) in raw_selected_ids
            if mode == "ALL":
                is_sel = s.enabled and s.status.upper() != CommerceConnectionStatus.DISCONNECTED.value
            item = {
                "id": s.source_id,
                "source_type": s.source_type,
                "display_name": s.display_name,
                "provider": s.provider,
                "status": s.status,
                "enabled": s.enabled,
                "last_synchronized_at": s.last_synchronized_at,
                "is_selected": is_sel,
            }
            items.append(item)
            if is_sel:
                selected_items.append(item)
                selected_ids_list.append(s.source_id)

        return {
            "mode": mode,
            "selected_source_ids": selected_ids_list,
            "selected_sources": selected_items,
            "available_sources": items,
            "effective_count": len(selected_items),
        }

    def set_workspace_selection(
        self,
        tenant: TenantContext,
        *,
        mode: str,
        selected_source_ids: list[UUID],
    ) -> dict:
        """Met à jour le mode et la sélection multi-sources pour l'entreprise."""
        normalized_mode = (mode or "").strip().upper()
        if normalized_mode not in ("ALL", "CUSTOM_SET", "SINGLE"):
            raise ValueError(
                f"Mode de sélection invalide: '{mode}'. Doit être 'ALL', 'CUSTOM_SET' ou 'SINGLE'."
            )

        available_sources = self.list_sources(tenant)
        available_by_id = {s.source_id: s for s in available_sources}

        # 1. Validation de cardinalité
        if normalized_mode == "SINGLE":
            if len(selected_source_ids) != 1:
                raise ValueError("Le mode SINGLE requiert exactement un identifiant de source sélectionné.")
        elif normalized_mode == "CUSTOM_SET":
            if len(selected_source_ids) < 1:
                raise ValueError("Le mode CUSTOM_SET requiert au moins un identifiant de source sélectionné.")

        # 2. Validation d'étanchéité multi-tenant & de déconnexion
        valid_selected_ids: list[UUID] = []
        if normalized_mode in ("SINGLE", "CUSTOM_SET"):
            for sid in selected_source_ids:
                if sid not in available_by_id:
                    # Vérifier si l'ID existe sur un autre tenant pour lever CrossTenantSourceAccessDenied
                    other_conn = self._session.get(CommerceConnection, sid)
                    other_ds = self._session.get(Dataset, sid)
                    if (other_conn and other_conn.company_id != tenant.company_id) or (
                        other_ds and other_ds.company_id != tenant.company_id
                    ):
                        raise CrossTenantSourceAccessDenied(
                            "Refus d'accès : la source demandée appartient à une autre entreprise."
                        )
                    if other_conn and other_conn.status.upper() == CommerceConnectionStatus.DISCONNECTED.value:
                        raise ValueError(
                            f"Impossible de sélectionner la source déconnectée '{other_conn.display_name or other_conn.external_account_id}'."
                        )
                    raise RetailSourceNotFound(f"Source avec l'identifiant '{sid}' introuvable.")

                source = available_by_id[sid]
                if source.status.upper() == CommerceConnectionStatus.DISCONNECTED.value:
                    raise ValueError(f"Impossible de sélectionner la source déconnectée '{source.display_name}'.")

                valid_selected_ids.append(sid)

        # 3. Persistance dans RetailActiveSource
        active = self._session.scalar(
            select(RetailActiveSource).where(
                RetailActiveSource.company_id == tenant.company_id
            )
        )
        if active is None:
            active = RetailActiveSource(
                company_id=tenant.company_id,
                source_type=normalized_mode,
            )
            self._session.add(active)

        active.source_type = normalized_mode
        active.selected_source_ids = [str(sid) for sid in valid_selected_ids]

        if normalized_mode == "SINGLE" and valid_selected_ids:
            target = available_by_id[valid_selected_ids[0]]
            active.connection_id = target.connection_id
            active.dataset_id = target.dataset_id
        else:
            active.connection_id = None
            active.dataset_id = None

        self._session.commit()
        return self.get_workspace_selection(tenant)