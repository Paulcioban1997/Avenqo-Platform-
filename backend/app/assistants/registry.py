"""Registre minimal des assistants Avenqo (Retail AVAILABLE, autres COMING_SOON).

Ne construit PAS un marketplace : uniquement de quoi résoudre le statut/les
outils autorisés d'un assistant. Le Tool Registry par assistant existe déjà
(`build_business_tool_registry`, `build_support_tool_registry`) : ce module
formalise seulement quel assistant possède quel registre, sans le dupliquer.
"""

from __future__ import annotations

from backend.app.assistants.contracts import AssistantDefinition, AssistantStatus
from backend.app.ai.tools.business.registry_factory import RETAIL_MODULE_CODE
from modules.registry import BUSINESS_MODULE_REGISTRY, ModuleAvailability

RETAIL_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "get_business_overview",
        "get_sales_summary",
        "get_sales_trend",
        "get_sales_comparison",
        "get_top_products",
        "get_customer_summary",
        "get_customer_segments",
        "get_inventory_summary",
        "get_churn_risk",
        "get_segment_insights",
        "get_demand_forecast",
        "get_sales_forecast",
        "get_anomalies",
        "get_prediction_summary",
    }
)

CRM_MODULE_CODE = "crm"
CRM_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "get_crm_overview",
        "get_leads_to_contact",
        "get_ranked_leads",
        "get_high_risk_customers",
        "get_top_revenue_deals",
        "get_follow_up_recommendation",
    }
)

ACCOUNTING_MODULE_CODE = "accounting"
ACCOUNTING_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "get_financial_overview",
        "get_monthly_expenses",
        "get_profit_margin",
        "get_unpaid_invoices",
        "get_expense_anomalies",
        "get_cash_flow_forecast",
    }
)

CROSS_AGENT_MODULE_CODE = "cross_agent"
CROSS_AGENT_TOOL_NAMES: frozenset[str] = (
    RETAIL_TOOL_NAMES
    | CRM_TOOL_NAMES
    | ACCOUNTING_TOOL_NAMES
    | frozenset({"get_cross_agent_business_health"})
)


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


def build_default_assistant_registry() -> AssistantRegistry:
    """Registre de référence Avenqo : Retail AVAILABLE, futurs assistants COMING_SOON."""

    registry = AssistantRegistry()
    for module in BUSINESS_MODULE_REGISTRY:
        status = {
            ModuleAvailability.AVAILABLE: AssistantStatus.AVAILABLE,
            ModuleAvailability.COMING_SOON: AssistantStatus.COMING_SOON,
            ModuleAvailability.UNAVAILABLE: AssistantStatus.DISABLED,
        }[module.availability]
        registry.register(
            AssistantDefinition(
                slug=module.key,
                name_key=f"assistant.{module.key}.name",
                description_key=f"assistant.{module.key}.description",
                status=status,
                category=module.category,
                module_code=module.key,
                allowed_tool_names=RETAIL_TOOL_NAMES
                if module.key == RETAIL_MODULE_CODE
                else (
                    CRM_TOOL_NAMES
                    if module.key == CRM_MODULE_CODE
                    else (ACCOUNTING_TOOL_NAMES if module.key == ACCOUNTING_MODULE_CODE else frozenset())
                ),
            )
        )
    registry.register(
        AssistantDefinition(
            slug=CROSS_AGENT_MODULE_CODE,
            name_key="assistant.cross_agent.name",
            description_key="assistant.cross_agent.description",
            status=AssistantStatus.AVAILABLE,
            category="intelligence",
            module_code=CROSS_AGENT_MODULE_CODE,
            allowed_tool_names=CROSS_AGENT_TOOL_NAMES,
        )
    )
    return registry
