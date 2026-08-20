"""Outil métier Avenqo : inventaire (Phase 30) — PRÉPARÉ MAIS NON DISPONIBLE.

Aucun modèle `Inventory`/`Stock`, aucun champ canonique `stock_quantity`, et
aucun service d'analytics d'inventaire n'existent dans la plateforme
aujourd'hui. Conformément à la règle "ne pas fabriquer de fausses données",
ce contrat est préparé proprement (nom, description, schéma) mais
`run()` renvoie toujours `ToolUnavailableError` tant que ces fondations ne
sont pas construites (hors périmètre Phase 30).
"""

from __future__ import annotations

from backend.app.ai.tools.base import AITool, ToolArguments
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.ai.tools.exceptions import ToolUnavailableError


class InventorySummaryArgs(ToolArguments):
    pass


class GetInventorySummaryTool(AITool):
    name = "get_inventory_summary"
    description = "Return which products are low in stock or need attention. NOT YET AVAILABLE: no inventory data source exists in the platform."
    input_schema = InventorySummaryArgs
    required_permissions = ("ai:use",)
    requires_capability = "inventory"

    async def run(self, context: ToolExecutionContext, arguments: InventorySummaryArgs) -> ToolResult:
        raise ToolUnavailableError(
            "Inventory data is not connected yet for this company. This capability is "
            "prepared architecturally but not backed by real data."
        )
