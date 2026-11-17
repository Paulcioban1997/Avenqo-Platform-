"""Planificateur et sélectionneur dynamique de capacités et d'outils pour Central AI Universel.

Permet à Central AI de:
1. Comprendre toute question générale sans exiger d'agent spécialisé.
2. Découvrir dynamiquement l'ensemble des outils autorisés pour un tenant selon ses modules actifs et ses permissions.
3. Sélectionner un sous-ensemble d'outils pertinent (multi-domaines si nécessaire) dans la limite MAX_TOOLS_PER_REQUEST.
4. Ne JAMAIS bloquer une requête avec `allowed_tool_names=frozenset()` quand des modules métiers sont actifs et que la demande concerne les données de l'entreprise.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.app.ai.tools.base import AITool
    from backend.app.ai.tools.registry import ToolRegistry
    from backend.app.assistants.contracts import AssistantDefinition
    from backend.app.assistants.registry import AssistantRegistry

logger = logging.getLogger("avenqo.ai.central.planner")

# Limite sûre d'outils injectés par requête LLM pour préserver les contextes et contrôler le coût
MAX_SELECTED_TOOLS = 8

# Mappage par mots-clés et racines pour scoring de pertinence multi-domaines (bilingue FR/EN)
MODULE_TOPIC_KEYWORDS: dict[str, frozenset[str]] = {
    "retail": frozenset({
        "produit", "produits", "product", "products", "item", "items", "article", "articles",
        "catalogue", "catalog", "catalogs", "catalogues", "stock", "stocks", "inventaire",
        "inventory", "inventaires", "vente", "ventes", "sale", "sales", "revenue", "revenu",
        "revenus", "commande", "commandes", "order", "orders", "panier", "paniers", "achat",
        "achats", "chiffre", "affaires", "bestseller", "top", "performance", "magasin", "store",
        "shopify", "woocommerce", "sku", "prix", "price", "pricing", "tendance", "tendances",
    }),
    "crm": frozenset({
        "client", "clients", "customer", "customers", "lead", "leads", "prospect", "prospects",
        "rendez", "rdv", "appointment", "appointments", "creneau", "creneaux", "slot", "slots",
        "disponibilite", "disponibilites", "availability", "schedule", "scheduling", "booking",
        "calendrier", "agenda", "calendar", "contact", "contacts", "reunion", "meeting",
        "horaire", "horaires", "hours", "service", "services",
    }),
    "accounting": frozenset({
        "facture", "factures", "invoice", "invoices", "impaye", "impayee", "impayes", "impayees",
        "unpaid", "depense", "depenses", "expense", "expenses", "marge", "marges", "margin",
        "margins", "tresorerie", "cashflow", "cash", "comptabilite", "accounting", "bilan",
        "creance", "creances",
    }),
    "marketing": frozenset({
        "marketing", "campagne", "campagnes", "campaign", "campaigns", "email", "emails",
        "relance", "relances", "newsletter", "ciblage", "promotion", "promo", "audience",
        "fidelisation", "conversion", "ads",
    }),
    "ocr": frozenset({
        "ocr", "scan", "scans", "document", "documents", "recu", "recus", "recue", "ticket",
        "tickets", "justificatif", "justificatifs", "piece", "pieces", "extraction", "texte",
    }),
    "legal": frozenset({
        "contrat", "contrats", "contract", "contracts", "accord", "accords", "agreement",
        "nda", "clause", "clauses", "juridique", "legal", "signature", "signe",
    }),
    "workflow": frozenset({
        "workflow", "workflows", "automation", "automations", "automatisation", "automatique",
        "declencheur", "trigger", "action", "scenario", "scenarios",
    }),
}

# Outils prioritaires par intention spécifique
TOOL_INTENT_AFFINITIES: dict[str, frozenset[str]] = {
    # Retail
    "get_product_detail": frozenset({"produit", "produits", "product", "products", "sku", "catalogue", "catalog", "prix", "price"}),
    "get_inventory_summary": frozenset({"stock", "stocks", "inventaire", "inventory", "rupture"}),
    "get_top_products": frozenset({"bestseller", "top", "meilleur", "meilleurs", "populaire", "plus"}),
    "get_sales_summary": frozenset({"vente", "ventes", "sale", "sales", "revenue", "revenu", "commande", "commandes"}),
    "get_sales_trend": frozenset({"tendance", "tendances", "evolution", "progression"}),
    # CRM
    "search_appointments": frozenset({"rendez", "rdv", "appointment", "appointments", "agenda", "calendrier"}),
    "list_available_slots": frozenset({"creneau", "creneaux", "slot", "slots", "disponibilite", "disponibilites"}),
    "check_availability": frozenset({"disponible", "libre", "heure", "horaire"}),
    "search_clients": frozenset({"client", "clients", "customer", "customers", "annuaire"}),
    "get_crm_overview": frozenset({"prospect", "prospects", "lead", "leads", "crm"}),
    # Accounting
    "get_unpaid_invoices": frozenset({"impaye", "impayee", "impayes", "impayees", "retard", "attente"}),
    "search_invoices": frozenset({"facture", "factures", "invoice", "invoices"}),
    "get_financial_overview": frozenset({"tresorerie", "cashflow", "bilan", "comptabilite"}),
    # Marketing
    "draft_marketing_campaign": frozenset({"campagne", "campagnes", "marketing", "relance", "newsletter"}),
    # OCR / Documents
    "search_documents": frozenset({"document", "documents", "scan", "recu", "piece"}),
    "get_ocr_document": frozenset({"ocr", "texte", "extraction"}),
    # Contracts
    "search_contracts": frozenset({"contrat", "contrats", "accord", "signature", "nda"}),
}


@dataclass(frozen=True, slots=True)
class PlannedToolScope:
    """Résultat de la planification pour une requête Central AI."""
    allowed_tool_names: frozenset[str]
    authorized_tool_agents: dict[str, str]
    is_general_query: bool
    targeted_modules: frozenset[str]
    primary_agent_slug: str | None


class UniversalCapabilityPlanner:
    """Orchestre la découverte et la sélection multi-outils pour Central AI."""

    def __init__(self, registry: AssistantRegistry, tool_registry: ToolRegistry | None = None) -> None:
        self._registry = registry
        self._tool_registry = tool_registry

    @staticmethod
    def tokenize(text: str) -> set[str]:
        """Normalise et découpe le texte en mots clés insensibles aux accents et à la casse."""
        normalized = unicodedata.normalize("NFKD", text.casefold())
        ascii_text = "".join(c for c in normalized if not unicodedata.combining(c))
        return set(re.findall(r"[a-z0-9]+", ascii_text))

    def plan_tool_scope(
        self,
        query: str,
        *,
        active_modules: frozenset[str],
        permissions: frozenset[str] = frozenset(),
        page_context: str | None = None,
        detected_agent: AssistantDefinition | None = None,
        matching_agents: Sequence[AssistantDefinition] = (),
    ) -> PlannedToolScope:
        """Détermine l'ensemble d'outils optimaux pour la requête selon les droits réels."""
        words = self.tokenize(query)

        # 1. Découvrir tous les agents autorisés par les modules actifs de l'entreprise
        authorized_defs = [
            defn for defn in self._registry.list_authorized(active_modules)
            if defn.status.is_executable
        ]

        # 2. Évaluer la pertinence par module / thématique
        module_scores: dict[str, int] = {}
        for mod, kws in MODULE_TOPIC_KEYWORDS.items():
            if mod in active_modules:
                overlap = len(words & kws)
                if overlap > 0:
                    module_scores[mod] = overlap

        # Bonus si détecté par le routeur d'intentions
        matched_mods = {a.module_code for a in matching_agents if a.module_code}
        for mod in matched_mods:
            if mod in active_modules:
                module_scores[mod] = module_scores.get(mod, 0) + 2

        if detected_agent and detected_agent.module_code and detected_agent.module_code in active_modules:
            module_scores[detected_agent.module_code] = module_scores.get(detected_agent.module_code, 0) + 3

        # Si aucun mot clé métier n'est trouvé et aucun agent spécialisé n'est matché
        is_general = len(module_scores) == 0 and (detected_agent is None or detected_agent.category in {"platform", "platform_support"})
        targeted_modules = frozenset(module_scores.keys())

        # 3. Répertoire de tous les outils autorisés par agent
        tools_map: dict[str, str] = {}  # tool_name -> agent_id
        for defn in authorized_defs:
            for t_name in defn.allowed_tool_names:
                tools_map[t_name] = defn.agent_id

        # Si un ToolRegistry est injecté, enrichir avec les outils enregistrés
        if self._tool_registry is not None:
            for tool_obj in self._tool_registry.list_tools():
                req_ent = getattr(tool_obj, "required_entitlements", frozenset())
                if req_ent and not req_ent.issubset(active_modules):
                    continue
                # Vérifier si l'un de ses agent_ids est autorisé
                for aid in tool_obj.agent_ids:
                    if any(d.agent_id == aid for d in authorized_defs):
                        tools_map.setdefault(tool_obj.name, aid)

        # 4. Scorer les outils individuels
        scored_tools: list[tuple[float, str, str]] = []  # (score, tool_name, agent_id)

        for t_name, a_id in tools_map.items():
            # Trouver le module propriétaire
            owner_def = next((d for d in authorized_defs if d.agent_id == a_id), None)
            owner_mod = owner_def.module_code if owner_def else None

            # Si le module de l'outil n'est pas ciblé et pas de module ciblé du tout
            mod_score = module_scores.get(owner_mod or "", 0)

            # Score d'affinité spécifique à l'outil
            affinity_kws = TOOL_INTENT_AFFINITIES.get(t_name, frozenset())
            affinity_score = len(words & affinity_kws) * 2.5

            total_score = (mod_score * 1.5) + affinity_score

            if total_score > 0:
                scored_tools.append((total_score, t_name, a_id))

        # Trier les outils par score décroissant
        scored_tools.sort(key=lambda item: item[0], reverse=True)

        candidate_tools: dict[str, str] = {}
        for score, t_name, a_id in scored_tools:
            if len(candidate_tools) >= MAX_SELECTED_TOOLS:
                break
            candidate_tools[t_name] = a_id

        # Priorité B : Si plusieurs modules ciblés, s'assurer d'avoir au moins 1 outil de chaque module ciblé
        if len(targeted_modules) >= 2:
            for mod in targeted_modules:
                has_mod_tool = any(
                    tools_map.get(t) and any(d.module_code == mod for d in authorized_defs if d.agent_id == tools_map[t])
                    for t in candidate_tools
                )
                if not has_mod_tool:
                    # Trouver le meilleur outil pour ce module
                    mod_tools = [
                        t for t, aid in tools_map.items()
                        if any(d.module_code == mod for d in authorized_defs if d.agent_id == aid)
                    ]
                    if mod_tools:
                        best_tool = max(mod_tools, key=lambda t: len(words & TOOL_INTENT_AFFINITIES.get(t, frozenset())))
                        candidate_tools[best_tool] = tools_map[best_tool]

        # Priorité C : si aucun module ciblé mais l'utilisateur utilise des termes possessifs ou d'interrogation interne
        if not candidate_tools and active_modules:
            internal_intent = bool(words & {"mon", "mes", "notre", "nos", "donne", "combien", "qui", "quels", "quelles", "liste", "etat", "resume"})
            if internal_intent:
                # Injecter les outils clés de consultation de base
                priority_defaults = [
                    "get_business_overview", "get_sales_summary", "get_product_detail",
                    "get_crm_overview", "search_appointments", "get_financial_overview",
                    "search_documents", "get_cross_agent_business_health"
                ]
                for p_tool in priority_defaults:
                    if p_tool in tools_map and len(candidate_tools) < MAX_SELECTED_TOOLS:
                        candidate_tools[p_tool] = tools_map[p_tool]

        # 5. Filtrer les outils selon ToolRegistry si disponible
        if self._tool_registry is not None:
            filtered_candidates: dict[str, str] = {}
            for t_name, a_id in candidate_tools.items():
                tool_obj = self._tool_registry.get(t_name)
                if tool_obj is None:
                    continue
                req_ent = getattr(tool_obj, "required_entitlements", frozenset())
                if req_ent and not req_ent.issubset(active_modules):
                    continue
                filtered_candidates[t_name] = a_id
            candidate_tools = filtered_candidates

        # 6. Limiter à MAX_SELECTED_TOOLS
        selected_tool_names = list(candidate_tools.keys())[:MAX_SELECTED_TOOLS]
        selected_tool_agents = {t: candidate_tools[t] for t in selected_tool_names}

        primary_slug = detected_agent.slug if detected_agent else (sorted(targeted_modules)[0] if targeted_modules else None)

        logger.info(
            "universal_planner_result query_words=%d targeted_modules=%s selected_tools_count=%d general=%s",
            len(words),
            list(targeted_modules),
            len(selected_tool_names),
            is_general,
        )

        return PlannedToolScope(
            allowed_tool_names=frozenset(selected_tool_names),
            authorized_tool_agents=selected_tool_agents,
            is_general_query=is_general and len(selected_tool_names) == 0,
            targeted_modules=targeted_modules,
            primary_agent_slug=primary_slug,
        )
