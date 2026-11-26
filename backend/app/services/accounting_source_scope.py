"""Résolution de la portée source active pour Accounting (même contexte que Data Hub / Retail)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import and_, false, or_, true
from sqlalchemy.orm import Session

from backend.app.services.retail_source_service import RetailSourceService
from shared.ai_engine.contracts import TenantContext


@dataclass(frozen=True)
class AccountingConnectorScope:
    dataset_ids: frozenset[UUID]
    connection_ids: tuple[str, ...]


AccountingSourceFilter = frozenset[UUID] | AccountingConnectorScope | None


def resolve_accounting_dataset_scope(
    session: Session,
    tenant: TenantContext,
) -> tuple[AccountingSourceFilter, dict[str, Any]]:
    """Retourne (filtre dataset_id, source_context serialisable).

    - ``None`` : aucune restriction de source (pas encore d'état / legacy company-wide).
    - ``frozenset()`` : source sélectionnée sans dataset lisible → aucun résultat.
    - ``frozenset({...})`` : limiter les écritures/factures aux datasets du tenant.
    - ``AccountingConnectorScope`` : inclure les écritures issues des connecteurs sélectionnés.
    """
    service = RetailSourceService(session)
    context = service.context(tenant, preserve_selection=True)
    sources = context.get("sources") or ()
    payload: dict[str, Any] = {
        "state": context.get("state"),
        "selection": context.get("source_type"),
        "source_id": str(context["source_id"]) if context.get("source_id") else None,
        "name": None,
        "provider": None,
        "dataset_id": None,
    }

    selected = None
    source_type = context.get("source_type")
    source_id = context.get("source_id")
    if source_type and source_type != "all" and source_id is not None:
        selected = next(
            (
                item
                for item in sources
                if item.source_type == source_type and item.source_id == source_id
            ),
            None,
        )
        if selected is not None:
            payload["name"] = selected.display_name
            payload["provider"] = selected.provider
            payload["dataset_id"] = str(selected.dataset_id) if selected.dataset_id else None

    state = context.get("state")
    # Preserve legacy company-wide ledger only when no explicit selection exists.
    # An unavailable or empty explicit selection must never widen the query.
    if source_type is None:
        return (None if state in {None, "NO_SOURCES"} else frozenset()), payload

    if state != "READY":
        return frozenset(), payload

    if source_type == "all":
        ready = [
            item for item in sources
            if item.enabled and item.status.upper() == "READY"
            and (item.dataset_id is not None or item.source_type == "connector")
        ]
        if not ready:
            payload["state"] = "NO_SOURCES"
    elif selected is not None and selected.status.upper() == "READY" and (
        selected.dataset_id is not None or selected.source_type == "connector"
    ):
        ready = [selected]
    else:
        payload["state"] = "SOURCE_UNAVAILABLE"
        ready = []

    payload["name"] = ", ".join(item.display_name for item in ready) or None
    dataset_ids = frozenset(item.dataset_id for item in ready if item.dataset_id is not None)
    connection_ids = tuple(sorted(
        str(item.source_id) for item in ready if item.source_type == "connector"
    ))
    scope = AccountingConnectorScope(dataset_ids, connection_ids) if connection_ids else dataset_ids
    return scope, payload


def apply_dataset_scope(model: Any, scope: AccountingSourceFilter):
    """Filter an Accounting model by dataset or server-recorded retail connection."""
    if scope is None:
        return true()
    if isinstance(scope, AccountingConnectorScope):
        return or_(
            model.dataset_id.in_(tuple(scope.dataset_ids)),
            and_(
                model.source_module == "retail",
                model.extra_data["connection_id"].as_string().in_(scope.connection_ids),
            ),
        )
    return model.dataset_id.in_(tuple(scope)) if scope else false()
