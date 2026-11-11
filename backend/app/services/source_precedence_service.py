"""Service de précédence des sources et résolution des conflits multi-sources Avenqo.

Assure une hiérarchie stricte et déterministe entre les différentes sources de données :
- Inventaire : Connecteur e-commerce temps réel (Shopify/WooCommerce) > Import tabulaire historique (CSV/Excel).
- Services & Prestations : CRM canonique > Configuration vocale draft/héritée.
- Disponibilité des créneaux : Calendrier connecté (Google Calendar) > Horaires statiques d'ouverture.
- Politiques & FAQ : Documents officiels importés (RAG) > Connaissances générales de l'agent.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from shared.ai_engine.contracts import TenantContext


class SourceFreshnessStatus(StrEnum):
    LIVE = "LIVE"
    NEAR_REALTIME = "NEAR_REALTIME"
    SYNCED = "SYNCED"
    HISTORICAL_IMPORT = "HISTORICAL_IMPORT"
    STATIC_POLICY = "STATIC_POLICY"
    UNAVAILABLE = "UNAVAILABLE"


class SourcePrecedenceCategory(StrEnum):
    INVENTORY = "inventory"
    SERVICES = "services"
    CALENDAR_SLOTS = "calendar_slots"
    POLICIES = "policies"
    ORDERS = "orders"


class SourcePrecedenceService:
    """Résout l'autorité d'une source et arbitre les conflits entre sources concurrentes."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def precedence_order(category: SourcePrecedenceCategory | str) -> list[str]:
        """Retourne l'ordre de priorité strict décroissant pour une catégorie donnée."""
        cat = str(category).lower()
        if cat == SourcePrecedenceCategory.INVENTORY:
            return ["live_connector", "synced_database", "historical_csv", "unverified_estimate"]
        if cat == SourcePrecedenceCategory.SERVICES:
            return ["crm_service_catalog", "voice_business_config", "general_industry_profile"]
        if cat == SourcePrecedenceCategory.CALENDAR_SLOTS:
            return ["google_calendar_live", "crm_internal_calendar", "static_business_hours"]
        if cat == SourcePrecedenceCategory.POLICIES:
            return ["tenant_document_rag", "company_profile_policy", "default_assistant_knowledge"]
        if cat == SourcePrecedenceCategory.ORDERS:
            return ["live_connector", "synced_database", "historical_dataset"]
        return ["live_connector", "synced_database", "historical_dataset", "static_configuration"]

    @staticmethod
    def resolve_preferred_source(
        category: SourcePrecedenceCategory | str,
        available_sources: list[str],
    ) -> str | None:
        """Sélectionne la source qui fait autorité parmi celles disponibles."""
        order = SourcePrecedenceService.precedence_order(category)
        for preferred in order:
            if preferred in available_sources:
                return preferred
        return available_sources[0] if available_sources else None

    @staticmethod
    def freshness_for_source(source_type: str) -> SourceFreshnessStatus:
        """Détermine le statut de fraîcheur canonique d'une source."""
        st = source_type.lower()
        if st in ("live_connector", "shopify_live", "woocommerce_live", "google_calendar_live"):
            return SourceFreshnessStatus.LIVE
        if st in ("synced_database", "crm_service_catalog", "tenant_document_rag"):
            return SourceFreshnessStatus.SYNCED
        if st in ("near_realtime", "webhooks_synced"):
            return SourceFreshnessStatus.NEAR_REALTIME
        if st in ("historical_csv", "historical_dataset", "dataset_import"):
            return SourceFreshnessStatus.HISTORICAL_IMPORT
        if st in ("company_profile_policy", "static_business_hours", "static_configuration"):
            return SourceFreshnessStatus.STATIC_POLICY
        return SourceFreshnessStatus.UNAVAILABLE

    @staticmethod
    def normalized_capabilities_for_source(source_type: str) -> frozenset[str]:
        """Retourne les capacités normalisées d'une source."""
        st = source_type.lower()
        if "shopify" in st or "woocommerce" in st or "commerce" in st:
            return frozenset({
                "catalog.search",
                "inventory.read",
                "orders.read",
                "reservations.in_store_pickup",
            })
        if "crm" in st or "calendar" in st:
            return frozenset({
                "appointments.availability",
                "appointments.create",
                "appointments.update",
                "appointments.cancel",
                "clients.read",
            })
        if "document" in st or "rag" in st:
            return frozenset({
                "documents.search",
                "documents.read",
                "policies.read",
            })
        if "dataset" in st or "csv" in st:
            return frozenset({
                "historical_sales.read",
                "historical_kpis.read",
            })
        return frozenset({"business.profile.read"})

