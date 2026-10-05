"""Définitions déclaratives des agents Avenqo et de leurs capacités réelles."""

from __future__ import annotations

from backend.app.assistants.contracts import AssistantDefinition, AssistantStatus
from modules.registry import RETAIL_MODULE_CODE

CRM_MODULE_CODE = "crm"
ACCOUNTING_MODULE_CODE = "accounting"
CROSS_AGENT_MODULE_CODE = "cross_agent"

RETAIL_INTENT_KEYWORDS = frozenset({
    "sale", "sales", "vente", "ventes", "revenue", "revenu", "customer",
    "customers", "client", "clients", "order", "orders", "commande",
    "commandes", "product", "products", "produit", "produits", "inventory",
    "inventaire", "stock", "recommendation", "recommendations", "recommandation",
    "recommandations", "kpi", "trend", "trends", "tendance", "tendances",
    "anomaly", "anomalies", "anomalie", "forecast", "prevision", "demand",
    "demande", "churn", "performance", "chiffre", "chiffres", "statistique",
    "statistiques", "bilan", "overview",
})
CRM_INTENT_KEYWORDS = frozenset({
    "crm", "lead", "leads", "opportunity", "opportunities", "prospect",
    "prospects", "deal", "deals", "relance", "relances", "contact", "contacts",
    "appointment", "appointments", "rendez", "creneau", "creneaux", "disponibilite",
    "disponibilites", "slot", "slots", "reservation", "reservations", "schedule",
    "scheduling", "booking", "calendrier", "agenda",
})
ACCOUNTING_INTENT_KEYWORDS = frozenset({
    "accounting", "comptabilite", "comptable", "invoice", "invoices", "facture",
    "factures", "impaye", "impayee", "impayes", "impayees", "depense", "depenses",
    "depenser", "marge", "marges", "tresorerie", "cashflow", "cash", "burn",
    "creance", "creances",
})
CROSS_AGENT_INTENT_KEYWORDS = frozenset({
    "360", "cross", "synergie", "synergies", "global", "globale", "globales",
    "synthese", "omnicanal", "strategie", "strategique", "complet", "complete",
    "holistique", "transversal", "transversale",
})
class AssistantRegistry:
    """Résout les métadonnées/statut d'un assistant par slug."""

    def __init__(self) -> None:
        self._items: dict[str, AssistantDefinition] = {}

    def register(self, definition: AssistantDefinition) -> None:
        self._items[definition.slug] = definition

    def get(self, slug: str) -> AssistantDefinition | None:
        return self._items.get(slug)

    def list_all(self) -> tuple[AssistantDefinition, ...]:
        return tuple(self._items.values())

    def list_available(self) -> tuple[AssistantDefinition, ...]:
        return tuple(item for item in self._items.values() if item.status.is_executable)

    def list_authorized(self, active_modules: frozenset[str]) -> tuple[AssistantDefinition, ...]:
        return tuple(
            item for item in self.list_available()
            if agent_entitlements(item).issubset(active_modules)
        )


def agent_entitlements(definition: AssistantDefinition) -> frozenset[str]:
    entitlements = set(definition.required_entitlements)
    if definition.module_code:
        entitlements.add(definition.module_code)
    return frozenset(entitlements)


def build_default_assistant_registry(*tool_registries) -> AssistantRegistry:
    """Register only agents whose tools and business behavior are implemented."""

    tools_by_agent: dict[str, set[str]] = {}
    capabilities_by_agent: dict[str, set[str]] = {}
    for tool_registry in tool_registries:
        for tool in tool_registry.list_tools():
            for agent_id in tool.agent_ids:
                tools_by_agent.setdefault(agent_id, set()).add(tool.name)
                capabilities = capabilities_by_agent.setdefault(agent_id, set())
                capabilities.update(tool.required_capabilities)
                if tool.requires_capability:
                    capabilities.add(tool.requires_capability)
    allowed_tools = {
        agent_id: frozenset(tool_names)
        for agent_id, tool_names in tools_by_agent.items()
    }

    definitions = (
        AssistantDefinition(
            slug="tenant_capabilities",
            name_key="navigation.billing",
            description_key="settings.billing",
            status=AssistantStatus.AVAILABLE,
            category="platform",
            allowed_tool_names=allowed_tools.get("tenant_capabilities", frozenset()),
            intent_keywords=frozenset({"subscription", "abonnement", "upgrade", "plan", "abonament", "suscripcion"}),
            routing_priority=100,
            supported_operations=frozenset({"read"}),
        ),
        AssistantDefinition(
            slug="voice",
            name_key="navigation.voiceAi",
            description_key="copilot.subtitle",
            status=AssistantStatus.AVAILABLE,
            category="communication",
            module_code="voice",
            allowed_tool_names=allowed_tools.get("voice", frozenset()),
            supported_operations=frozenset({"read"}),
            entrypoints=frozenset({"voice"}),
        ),
        AssistantDefinition(
            slug=RETAIL_MODULE_CODE,
            name_key="assistant.retail.name",
            description_key="assistant.retail.description",
            status=AssistantStatus.AVAILABLE,
            category="commerce",
            module_code=RETAIL_MODULE_CODE,
            capabilities=frozenset(capabilities_by_agent.get(RETAIL_MODULE_CODE, set())),
            allowed_tool_names=allowed_tools.get(RETAIL_MODULE_CODE, frozenset()),
            intents=("retail.sales", "retail.customers", "retail.products", "retail.analytics"),
            intent_keywords=RETAIL_INTENT_KEYWORDS,
            supported_operations=frozenset({"read", "analyze", "forecast"}),
            localization_metadata={"system_prompt": "ai.agent.retail.system"},
        ),
        AssistantDefinition(
            slug=CRM_MODULE_CODE,
            name_key="assistant.crm.name",
            description_key="assistant.crm.description",
            status=AssistantStatus.AVAILABLE,
            category="customer",
            module_code=CRM_MODULE_CODE,
            capabilities=frozenset(capabilities_by_agent.get(CRM_MODULE_CODE, set())),
            allowed_tool_names=allowed_tools.get(CRM_MODULE_CODE, frozenset()),
            intents=("crm.customers", "crm.leads", "crm.appointments"),
            intent_keywords=CRM_INTENT_KEYWORDS,
            page_context_prefixes=("/crm",),
            supported_operations=frozenset({"read", "analyze", "appointment.create", "appointment.update", "appointment.cancel"}),
            mutation_capabilities=frozenset({
                "calendar.write", "crm.appointment.write", "appointment.create",
                "appointment.update", "appointment.cancel",
            }),
            confirmation_policy="explicit_user_confirmation",
            localization_metadata={"system_prompt": "ai.agent.crm.system"},
        ),
        AssistantDefinition(
            slug=ACCOUNTING_MODULE_CODE,
            name_key="assistant.accounting.name",
            description_key="assistant.accounting.description",
            status=AssistantStatus.AVAILABLE,
            category="finance",
            module_code=ACCOUNTING_MODULE_CODE,
            capabilities=frozenset(capabilities_by_agent.get(ACCOUNTING_MODULE_CODE, set())),
            allowed_tool_names=allowed_tools.get(ACCOUNTING_MODULE_CODE, frozenset()),
            intents=("accounting.invoices", "accounting.expenses", "accounting.cashflow"),
            intent_keywords=ACCOUNTING_INTENT_KEYWORDS,
            supported_operations=frozenset({"read", "analyze", "forecast"}),
            localization_metadata={"system_prompt": "ai.agent.accounting.system"},
        ),
        AssistantDefinition(
            slug=CROSS_AGENT_MODULE_CODE,
            name_key="assistant.cross_agent.name",
            description_key="assistant.cross_agent.description",
            status=AssistantStatus.AVAILABLE,
            category="intelligence",
            required_entitlements=frozenset({"retail", "crm", "accounting"}),
            capabilities=frozenset(capabilities_by_agent.get(CROSS_AGENT_MODULE_CODE, set())),
            allowed_tool_names=allowed_tools.get(CROSS_AGENT_MODULE_CODE, frozenset()),
            intents=("business.cross_domain_summary",),
            intent_keywords=CROSS_AGENT_INTENT_KEYWORDS,
            aggregate=True,
            supported_operations=frozenset({"read", "analyze"}),
            localization_metadata={"system_prompt": "ai.agent.cross_domain.system"},
        ),
        AssistantDefinition(
            slug="platform_support",
            name_key="assistant.platform_support.name",
            description_key="assistant.platform_support.description",
            status=AssistantStatus.AVAILABLE,
            category="platform_support",
            capabilities=frozenset(capabilities_by_agent.get("platform_support", set())),
            allowed_tool_names=allowed_tools.get("platform_support", frozenset()),
            intents=("platform.support",),
            supported_operations=frozenset({"read"}),
            localization_metadata={"system_prompt": "ai.agent.platform_support.system"},
            entrypoints=frozenset({"support"}),
        ),
    )
    registry = AssistantRegistry()
    for definition in definitions:
        registry.register(definition)
    return registry
