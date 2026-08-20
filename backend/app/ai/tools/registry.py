"""Registre central des outils Avenqo (Phase 30).

Ne fournit JAMAIS automatiquement tous les outils à tous les utilisateurs :
`available_for` filtre par permissions, capacité tenant et plan.
"""

from __future__ import annotations

from backend.app.ai.tools.base import AITool
from backend.app.ai.tools.plans import plan_meets_minimum


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AITool] = {}

    def register(self, tool: AITool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> AITool | None:
        return self._tools.get(name)

    def list_tools(self) -> tuple[AITool, ...]:
        return tuple(self._tools.values())

    def available_for(
        self,
        *,
        permissions: frozenset[str],
        plan_code: str | None,
        capabilities: frozenset[str],
    ) -> tuple[AITool, ...]:
        """Sous-ensemble des outils réellement utilisables par ce tenant/utilisateur."""

        return tuple(
            tool
            for tool in self._tools.values()
            if set(tool.required_permissions).issubset(permissions)
            and plan_meets_minimum(plan_code, tool.minimum_plan)
            and tool.is_available_for(capabilities=capabilities)
        )
