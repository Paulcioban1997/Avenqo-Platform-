"""AVENQO Voice Master — Selected Data Source Intelligence.

Absolute rule: Voice never auto-consults all connected org data.
Only sources that are Connected AND Currently Selected AND Active/Enabled
AND Authorized for the authenticated session/org/user may be queried.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.permissions import permissions_for, resolve_verified_staff_role
from backend.app.models import CompanyMembership, Dataset, User
from backend.app.services.retail_source_service import RetailSource, RetailSourceService
from backend.app.voice.module_actions import VOICE_RETAIL_NATIVE_TOOLS, action_for_tool
from shared.ai_engine.contracts import TenantContext

_logger = logging.getLogger("avenqo.voice.selected_sources")

_DATASET_FILE_RE = re.compile(
    r"\b("
    r"fichier|file|excel|xlsx|xls|csv|dataset|jeu de donn|feuille|sheet|onglet|"
    r"colonne|column|contenu|content|resume|summary|sommaire|"
    r"importe|imported|uploade|uploaded|document.*donnees|data.?file"
    r")\b",
    re.IGNORECASE,
)
_CALENDAR_RE = re.compile(
    r"\b("
    r"rendez[- ]?vous|rdv|appointment|appointments|booking|bookings|"
    r"calendrier|calendar|disponibilit|availability|horaire de rendez|"
    r"prendre (un )?rdv|book( an)? appointment|cita|programare"
    r")\b",
    re.IGNORECASE,
)
_DATE_ONLY_RE = re.compile(
    r"\b("
    r"\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?"
    r"|(\d{1,2}\s+)?"
    r"(janvier|fevrier|février|mars|avril|mai|juin|juillet|aout|août|septembre|octobre|novembre|decembre|décembre"
    r"|january|february|march|april|may|june|july|august|september|october|november|december)"
    r"(\s+\d{2,4})?"
    r")\b",
    re.IGNORECASE,
)
_ALL_SOURCES_INJECTION_RE = re.compile(
    r"\b("
    r"toutes? les sources|all (connected )?sources|every source|read all|"
    r"ignore (la )?selection|bypass selection|sans selection|all datasets|"
    r"toutes? les donnees connectees|all connected data"
    r")\b",
    re.IGNORECASE,
)

PRIVATE_DATA_TOOLS = frozenset({
    *VOICE_RETAIL_NATIVE_TOOLS,
    "get_sales_summary",
    "get_sales_trend",
    "get_sales_comparison",
    "get_sales_forecast",
    "get_inventory_summary",
    "get_inventory_freshness",
    "get_product_detail",
    "get_customer_summary",
    "get_prediction_summary",
    "get_coaching_advice",
    "get_executive_briefing",
    "get_financial_overview",
    "get_profit_margin",
    "list_invoices",
    "get_cashflow_forecast",
})
CALENDAR_TOOLS = frozenset({
    "book_appointment",
    "create_appointment",
    "reschedule_appointment",
    "update_appointment",
    "cancel_appointment",
    "list_appointments",
    "get_availability",
})


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", (text or "").casefold())
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


@dataclass(frozen=True, slots=True)
class SelectedSourceResolution:
    state: str
    selection_mode: str | None
    sources: list[dict[str, Any]]
    selected_source_ids: list[str]
    excluded_source_ids: list[str]
    dataset_ids: frozenset[UUID]


@dataclass(frozen=True, slots=True)
class VoiceIntentDecision:
    intent: str
    allow_calendar_tools: bool
    allow_dataset_tools: bool
    reason: str


def resolve_authorized_selected_sources(
    db: Session,
    tenant: TenantContext,
    *,
    require_data_read: bool = False,
) -> SelectedSourceResolution:
    """Server-side selected-source gate used by Voice (fail closed)."""
    service = RetailSourceService(db, fresh_reads=True)
    available = service.list_sources(tenant, preserve_selection=True)
    explicit = service.explicit_selection(tenant)
    if explicit is None:
        excluded = [str(item.source_id) for item in available]
        return SelectedSourceResolution(
            state="NO_SELECTION",
            selection_mode=None,
            sources=[],
            selected_source_ids=[],
            excluded_source_ids=excluded,
            dataset_ids=frozenset(),
        )

    if require_data_read:
        if tenant.user_id is None:
            return SelectedSourceResolution(
                state="UNAUTHORIZED",
                selection_mode=getattr(explicit, "selection_mode", None) or explicit.source_type,
                sources=[],
                selected_source_ids=[],
                excluded_source_ids=[str(item.source_id) for item in available],
                dataset_ids=frozenset(),
            )
        user = db.get(User, tenant.user_id, populate_existing=True)
        membership = db.scalar(
            select(CompanyMembership).where(
                CompanyMembership.company_id == tenant.company_id,
                CompanyMembership.user_id == tenant.user_id,
                CompanyMembership.is_active.is_(True),
            ).execution_options(populate_existing=True)
        )
        if (
            user is None
            or not user.is_active
            or user.company_id != tenant.company_id
            or membership is None
        ):
            return SelectedSourceResolution(
                state="UNAUTHORIZED",
                selection_mode=getattr(explicit, "selection_mode", None) or explicit.source_type,
                sources=[],
                selected_source_ids=[],
                excluded_source_ids=[str(item.source_id) for item in available],
                dataset_ids=frozenset(),
            )
        if "data:read" not in permissions_for(membership.role):
            return SelectedSourceResolution(
                state="UNAUTHORIZED",
                selection_mode=getattr(explicit, "selection_mode", None) or explicit.source_type,
                sources=[],
                selected_source_ids=[],
                excluded_source_ids=[str(item.source_id) for item in available],
                dataset_ids=frozenset(),
            )

    ready = service.selected_ready_sources(tenant, allow_auto_default=False)
    ready_ids = {str(item.source_id) for item in ready}
    excluded = [
        str(item.source_id)
        for item in available
        if str(item.source_id) not in ready_ids
    ]
    mode = getattr(explicit, "selection_mode", None) or explicit.source_type
    state = "READY" if ready else "SOURCE_UNAVAILABLE"
    return SelectedSourceResolution(
        state=state,
        selection_mode=str(mode).lower() if mode else None,
        sources=[_source_payload(item) for item in ready],
        selected_source_ids=[str(item.source_id) for item in ready],
        excluded_source_ids=excluded,
        dataset_ids=frozenset(item.dataset_id for item in ready if item.dataset_id is not None),
    )


def _source_payload(source: RetailSource) -> dict[str, Any]:
    return {
        "source_id": str(source.source_id),
        "dataset_id": str(source.dataset_id) if source.dataset_id else None,
        "source_type": source.source_type,
        "provider": source.provider,
        "name": source.display_name,
        "last_updated_at": source.last_synchronized_at.isoformat() if source.last_synchronized_at else None,
    }


def classify_voice_data_intent(transcript: str, *, has_selected_dataset: bool) -> VoiceIntentDecision:
    """Distinguish Excel/dataset questions from calendar/appointment intent.

    A bare date such as "21 novembre" inside a file/dataset question must NOT
    route to calendar tools.
    """
    norm = _normalize(transcript)
    if _ALL_SOURCES_INJECTION_RE.search(norm):
        return VoiceIntentDecision(
            intent="prompt_injection_all_sources",
            allow_calendar_tools=False,
            allow_dataset_tools=False,
            reason="prompt_injection_denied",
        )

    has_file = bool(_DATASET_FILE_RE.search(norm))
    has_calendar = bool(_CALENDAR_RE.search(norm))
    has_date = bool(_DATE_ONLY_RE.search(norm))

    if has_file and not has_calendar:
        return VoiceIntentDecision(
            intent="dataset_file",
            allow_calendar_tools=False,
            allow_dataset_tools=True,
            reason="explicit_dataset_or_file_language",
        )
    if has_calendar and not has_file:
        return VoiceIntentDecision(
            intent="calendar_appointment",
            allow_calendar_tools=True,
            allow_dataset_tools=False,
            reason="explicit_appointment_language",
        )
    if has_file and has_calendar:
        # Mixed utterance: prefer dataset grounding when a file/dataset is named.
        return VoiceIntentDecision(
            intent="dataset_file",
            allow_calendar_tools=False,
            allow_dataset_tools=True,
            reason="file_context_overrides_calendar_keywords",
        )
    if has_date and has_selected_dataset and not has_calendar:
        return VoiceIntentDecision(
            intent="dataset_file",
            allow_calendar_tools=False,
            allow_dataset_tools=True,
            reason="date_with_selected_dataset_without_appointment_intent",
        )
    if has_calendar:
        return VoiceIntentDecision(
            intent="calendar_appointment",
            allow_calendar_tools=True,
            allow_dataset_tools=has_selected_dataset,
            reason="appointment_intent",
        )
    return VoiceIntentDecision(
        intent="general",
        allow_calendar_tools=True,
        allow_dataset_tools=has_selected_dataset,
        reason="default_general",
    )


def assert_tool_allowed_for_selected_sources(
    *,
    tool_name: str,
    resolution: SelectedSourceResolution,
    intent: VoiceIntentDecision,
) -> None:
    """Fail-closed gate before private/calendar tool execution."""
    from backend.app.voice.tool_guard import VoiceToolDenied

    canonical = tool_name
    if intent.intent == "prompt_injection_all_sources":
        raise VoiceToolDenied("Selected-source policy denied a request to read all connected sources.")

    if tool_name in CALENDAR_TOOLS or canonical in CALENDAR_TOOLS:
        if not intent.allow_calendar_tools:
            raise VoiceToolDenied(
                "Calendar/appointment tools are blocked for this dataset/file question."
            )
        return

    private = tool_name in PRIVATE_DATA_TOOLS or canonical in PRIVATE_DATA_TOOLS
    mapping = action_for_tool(tool_name)
    if mapping is not None and mapping[0] in {"retail", "accounting", "marketing", "cross_agent"}:
        private = True
    if tool_name in VOICE_RETAIL_NATIVE_TOOLS:
        private = True

    if not private:
        return

    if resolution.state in {"NO_SELECTION", "UNAUTHORIZED"} or not resolution.selected_source_ids:
        raise VoiceToolDenied(
            "No currently selected and authorized data source is available for private Voice tools."
        )
    if not intent.allow_dataset_tools:
        raise VoiceToolDenied("Dataset tools are not permitted for this calendar/appointment intent.")


def describe_selected_dataset_grounding(
    db: Session,
    tenant: TenantContext,
    *,
    locale: str = "fr-CA",
) -> str | None:
    """Grounded spoken summary of the currently selected dataset/file — never invent."""
    resolution = resolve_authorized_selected_sources(db, tenant, require_data_read=True)
    if resolution.state != "READY" or not resolution.sources:
        if (locale or "").lower().startswith("fr"):
            return (
                "Aucune source de données n'est actuellement sélectionnée et autorisée "
                "pour cette session. Je ne peux pas inventer le contenu d'un fichier."
            )
        return (
            "No data source is currently selected and authorized for this session. "
            "I cannot invent file contents."
        )

    parts: list[str] = []
    for source in resolution.sources:
        name = source.get("name") or "source"
        dataset_id = source.get("dataset_id")
        if not dataset_id:
            parts.append(f"{name} (connecteur, sans fichier dataset local).")
            continue
        dataset = db.scalar(
            select(Dataset).where(
                Dataset.id == UUID(str(dataset_id)),
                Dataset.company_id == tenant.company_id,
            )
        )
        if dataset is None:
            parts.append(f"{name}: métadonnées indisponibles.")
            continue
        version = next((item for item in (dataset.versions or []) if item.is_current), None)
        columns = getattr(dataset, "columns_count", None)
        rows = getattr(dataset, "rows_count", None)
        sheet_hint = None
        if version is not None:
            meta = getattr(version, "metadata_json", None) or getattr(version, "stats", None) or {}
            if isinstance(meta, dict):
                sheets = meta.get("sheets") or meta.get("sheet_names")
                if isinstance(sheets, list) and sheets:
                    sheet_hint = ", ".join(str(item) for item in sheets[:8])
        if (locale or "").lower().startswith("fr"):
            detail = f"Fichier sélectionné: {dataset.name}."
            if columns:
                detail += f" Environ {columns} colonnes."
            if rows:
                detail += f" Environ {rows} lignes."
            if sheet_hint:
                detail += f" Feuilles: {sheet_hint}."
            detail += " Je réponds uniquement à partir de ce fichier sélectionné, sans inventer."
        else:
            detail = f"Selected file: {dataset.name}."
            if columns:
                detail += f" About {columns} columns."
            if rows:
                detail += f" About {rows} rows."
            if sheet_hint:
                detail += f" Sheets: {sheet_hint}."
            detail += " I only answer from this selected file and will not invent data."
        parts.append(detail)

    return " ".join(parts)


def log_voice_source_access(
    *,
    company_id: UUID | None,
    user_id: UUID | None,
    role: str | None,
    selected_source_ids: list[str],
    queried_source_ids: list[str],
    intent: str | None,
    tool: str | None,
    exclusions: list[str],
    state: str | None = None,
) -> None:
    """Structured observability without PIN/secrets/PII payloads."""
    _logger.info(
        "voice_selected_source_access company_id=%s user_id=%s role=%s state=%s "
        "selected_source_ids=%s queried_source_ids=%s intent=%s tool=%s exclusions=%s",
        str(company_id) if company_id else None,
        str(user_id) if user_id else None,
        role,
        state,
        selected_source_ids,
        queried_source_ids,
        intent,
        tool,
        exclusions,
    )


def staff_role_for_log(db: Session, company_id: UUID, user_id: UUID | None) -> str | None:
    if user_id is None:
        return None
    return resolve_verified_staff_role(db, company_id, user_id)
