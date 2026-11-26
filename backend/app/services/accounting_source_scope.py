"""Résolution de la portée source active pour Accounting (même contexte que Data Hub / Retail)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.services.retail_source_service import RetailSourceService
from shared.ai_engine.contracts import TenantContext


def resolve_accounting_dataset_scope(
    session: Session,
    tenant: TenantContext,
) -> tuple[frozenset[UUID] | None, dict[str, Any]]:
    """Retourne (filtre dataset_id, source_context serialisable).

    - ``None`` : aucune restriction de source (pas encore d'état / legacy company-wide).
    - ``frozenset()`` : source sélectionnée sans dataset lisible → aucun résultat.
    - ``frozenset({...})`` : limiter les écritures/factures à ces dataset_id du tenant.
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
            item
            for item in sources
            if item.enabled and item.status.upper() == "READY" and item.dataset_id is not None
        ]
        payload["name"] = ", ".join(item.display_name for item in ready) or None
        if not ready:
            payload["state"] = "NO_SOURCES"
        return frozenset(item.dataset_id for item in ready if item.dataset_id is not None), payload

    if (
        selected is None
        or selected.dataset_id is None
        or selected.status.upper() != "READY"
    ):
        payload["state"] = "SOURCE_UNAVAILABLE"
        return frozenset(), payload

    return frozenset({selected.dataset_id}), payload


def apply_dataset_scope(column: Any, dataset_ids: frozenset[UUID] | None):
    """Clause SQLAlchemy pour filtrer une colonne dataset_id nullable."""
    from sqlalchemy import false, true

    if dataset_ids is None:
        return true()
    if not dataset_ids:
        return false()
    return column.in_(tuple(dataset_ids))
