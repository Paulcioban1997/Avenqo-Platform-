"""Registre minimal des assistants Avenqo (Retail AVAILABLE, autres COMING_SOON).

Ne construit PAS un marketplace : uniquement de quoi résoudre le statut/les
outils autorisés d'un assistant. Le Tool Registry par assistant existe déjà
(`build_business_tool_registry`, `build_support_tool_registry`) : ce module
formalise seulement quel assistant possède quel registre, sans le dupliquer.
"""

from __future__ import annotations

from backend.app.assistants.contracts import AssistantDefinition, AssistantStatus
from backend.app.ai.tools.business.registry_factory import RETAIL_MODULE_CODE

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
    registry.register(
        AssistantDefinition(
            slug="retail",
            name_key="assistant.retail.name",
            description_key="assistant.retail.description",
            status=AssistantStatus.AVAILABLE,
            category="business",
            module_code=RETAIL_MODULE_CODE,
            allowed_tool_names=RETAIL_TOOL_NAMES,
        )
    )
    for slug, category in (
        ("crm", "business"),
        ("accounting", "business"),
        ("legal", "business"),
        ("marketing", "business"),
        ("real_estate", "business"),
        ("restaurant", "business"),
        ("clinic", "business"),
        ("customer_support", "business"),
    ):
        registry.register(
            AssistantDefinition(
                slug=slug,
                name_key=f"assistant.{slug}.name",
                description_key=f"assistant.{slug}.description",
                status=AssistantStatus.COMING_SOON,
                category=category,
                module_code=None,
            )
        )
    return registry
