"""Deterministic intent routing for the Avenqo assistant registry."""

from __future__ import annotations

import re
import unicodedata

from backend.app.assistants.contracts import AssistantDefinition
from backend.app.assistants.registry import AssistantRegistry


_COMING_SOON_KEYWORDS = {
    "crm": frozenset({"crm", "lead", "leads", "opportunity", "opportunities", "prospect"}),
    "accounting": frozenset({"accounting", "comptabilite", "invoice", "invoices", "facture", "factures", "finance"}),
    "legal": frozenset({"legal", "juridique", "contract", "contracts", "contrat", "contrats"}),
    "marketing": frozenset({"marketing", "campaign", "campaigns", "campagne", "campagnes", "audience"}),
    "real_estate": frozenset({"realestate", "immobilier", "property", "properties"}),
    "restaurant": frozenset({"restaurant", "menu", "reservation"}),
    "clinic": frozenset({"clinic", "clinique", "patient", "patients"}),
    "customer_support": frozenset({"support", "ticket", "tickets", "helpdesk"}),
}

_RETAIL_KEYWORDS = frozenset(
    {
        "sale", "sales", "vente", "ventes", "revenue", "revenu", "customer",
        "customers", "client", "clients", "product", "products", "produit",
        "produits", "inventory", "inventaire", "stock", "recommendation",
        "recommendations", "recommandation", "recommandations", "kpi", "trend",
        "trends", "tendance", "tendances", "anomaly", "anomalies", "anomalie",
        "forecast", "prevision", "demand", "demande", "churn", "performance",
    }
)


class CentralAIIntentRouter:
    def __init__(self, registry: AssistantRegistry) -> None:
        self._registry = registry

    def select(self, query: str) -> AssistantDefinition | None:
        words = self._words(query)
        for slug, keywords in _COMING_SOON_KEYWORDS.items():
            if words & keywords:
                return self._registry.get(slug)
        if words & _RETAIL_KEYWORDS:
            return self._registry.get("retail")
        return None

    @staticmethod
    def _words(query: str) -> set[str]:
        normalized = unicodedata.normalize("NFKD", query.casefold())
        ascii_query = "".join(character for character in normalized if not unicodedata.combining(character))
        return set(re.findall(r"[a-z0-9]+", ascii_query))