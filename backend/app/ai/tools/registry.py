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
        if not tool.agent_ids:
            raise ValueError(f"Tool '{tool.name}' must declare at least one owning agent.")
        if tool.read_only is None or tool.mutates is None:
            raise ValueError(f"Tool '{tool.name}' must explicitly declare its read-only or mutating behavior.")
        if tool.mutates and (tool.read_only or not tool.mutation_capabilities):
            raise ValueError(f"Mutating tool '{tool.name}' must declare mutation capabilities and read_only=False.")
        if tool.mutates and tool.confirmation_policy != "explicit_user_confirmation":
            raise ValueError(f"Mutating tool '{tool.name}' must require explicit user confirmation.")
        if not tool.mutates and tool.read_only is not True:
            raise ValueError(f"Tool '{tool.name}' must explicitly declare mutates=True.")
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
            and tool.required_capabilities.issubset(capabilities)
        )
