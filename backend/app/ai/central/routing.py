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
    "appointments": frozenset({"appointment", "appointments", "rendez", "schedule", "booking"}),
    "ocr": frozenset({"ocr", "document", "documents", "scan", "extract"}),
    "hr": frozenset({"employee", "employees", "rh", "recrutement", "recruitment"}),
    "voice": frozenset({"voice", "voix", "call", "calls"}),
    "media": frozenset({"media", "image", "video", "creative"}),
    "workflow": frozenset({"workflow", "automation", "automatisation"}),
    "ai_agents": frozenset({"agent", "agents", "autonomous"}),
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