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
    selected_ids = {
        str(item) for item in (context.get("selected_source_ids") or []) if item
    }
    payload: dict[str, Any] = {
        "state": context.get("state"),
        "selection": context.get("source_type"),
        "source_id": str(context["source_id"]) if context.get("source_id") else None,
        "name": None,
        "provider": None,
        "dataset_id": None,
        "selected_source_ids": sorted(selected_ids),
    }

    source_type = context.get("source_type")
    source_id = context.get("source_id")
    state = context.get("state")

    # Preserve legacy company-wide ledger only when no explicit selection exists.
    # An unavailable or empty explicit selection must never widen the query.
    if source_type is None:
        return (None if state in {None, "NO_SOURCES"} else frozenset()), payload

    if state != "READY":
        return frozenset(), payload

    def _is_ready(item: Any) -> bool:
        return bool(
            getattr(item, "enabled", False)
            and str(getattr(item, "status", "")).upper() == "READY"
            and (
                getattr(item, "dataset_id", None) is not None
                or getattr(item, "source_type", None) == "connector"
            )
        )

    if source_type == "all":
        ready = [item for item in sources if _is_ready(item)]
        if selected_ids:
            ready = [
                item for item in ready
                if str(getattr(item, "source_id", getattr(item, "dataset_id", ""))) in selected_ids
                or str(getattr(item, "dataset_id", "")) in selected_ids
            ]
        if not ready:
            payload["state"] = "NO_SOURCES"
    elif source_type == "custom_set":
        ready = [
            item for item in sources
            if _is_ready(item)
            and (
                not selected_ids
                or str(getattr(item, "source_id", "")) in selected_ids
                or str(getattr(item, "dataset_id", "")) in selected_ids
            )
        ]
        if not ready:
            payload["state"] = "SOURCE_UNAVAILABLE"
    else:
        selected = next(
            (
                item
                for item in sources
                if getattr(item, "source_type", None) == source_type
                and getattr(item, "source_id", None) == source_id
            ),
            None,
        )
        if selected is None and selected_ids:
            selected = next(
                (
                    item
                    for item in sources
                    if str(getattr(item, "source_id", "")) in selected_ids
                    or str(getattr(item, "dataset_id", "")) in selected_ids
                ),
                None,
            )
        if selected is not None:
            payload["name"] = getattr(selected, "display_name", None)
            payload["provider"] = getattr(selected, "provider", None)
            payload["dataset_id"] = (
                str(selected.dataset_id) if getattr(selected, "dataset_id", None) else None
            )
        if selected is not None and _is_ready(selected):
            ready = [selected]
        else:
            payload["state"] = "SOURCE_UNAVAILABLE"
            ready = []

    payload["name"] = ", ".join(
        getattr(item, "display_name", "") for item in ready if getattr(item, "display_name", None)
    ) or payload.get("name")
    dataset_ids = frozenset(
        item.dataset_id for item in ready if getattr(item, "dataset_id", None) is not None
    )
    connection_ids = tuple(sorted(
        str(item.source_id)
        for item in ready
        if getattr(item, "source_type", None) == "connector" and getattr(item, "source_id", None)
    ))
    payload["selected_source_ids"] = [
        str(getattr(item, "source_id", getattr(item, "dataset_id", "")))
        for item in ready
        if getattr(item, "source_id", None) is not None or getattr(item, "dataset_id", None) is not None
    ]
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
