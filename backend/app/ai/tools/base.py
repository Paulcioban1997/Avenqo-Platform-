"""Contrat `AITool` professionnel (Phase 30).

Chaque outil expose un contrat strict : nom, description, schémas
d'entrée/sortie Pydantic, permissions requises, caractère read-only,
timeout et plan minimum. Les arguments du LLM ne sont JAMAIS utilisés tels
quels : ils sont toujours validés via `input_schema` par le `ToolExecutor`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from backend.app.ai.tools.contracts import ToolDefinition, ToolExecutionContext, ToolResult


class ToolArguments(BaseModel):
    """Base stricte : rejette toute propriété inconnue fournie par le LLM."""

    model_config = {"extra": "forbid"}


class AITool(ABC):
    """Contrat professionnel d'un outil Avenqo exécutable par tool calling."""

    name: str
    description: str
    input_schema: type[ToolArguments] = ToolArguments
    output_schema: type[BaseModel] | None = None
    required_permissions: tuple[str, ...] = ("ai:use",)
    read_only: bool = True
    timeout_seconds: float = 10.0
    minimum_plan: str | None = None
    requires_capability: str | None = None

    def definition(self) -> ToolDefinition:
        """Représentation provider-agnostique consommée par le LLM tool calling."""

        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters_schema=self.input_schema.model_json_schema(),
        )

    @abstractmethod
    async def run(self, context: ToolExecutionContext, arguments: ToolArguments) -> ToolResult:
        """Exécute l'outil avec des arguments déjà validés. Ne jamais lever d'erreur brute."""

        raise NotImplementedError

    def is_available_for(self, *, capabilities: frozenset[str]) -> bool:
        """Indique si la capacité tenant requise par cet outil est présente."""

        if self.requires_capability is None:
            return True
        return self.requires_capability in capabilities
