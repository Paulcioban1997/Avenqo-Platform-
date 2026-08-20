from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from backend.app.ai.llm.exceptions import ToolCallingUnsupportedError
from backend.app.ai.llm.schemas import LLMGeneration, LLMMessage, LLMToolResponse, ToolDefinition


class LLMProvider(ABC):
    name: str
    supports_tool_calling: bool = False

    @abstractmethod
    async def generate(self, *, system_instruction: str, prompt: str) -> LLMGeneration:
        raise NotImplementedError

    @abstractmethod
    async def stream(self, *, system_instruction: str, prompt: str) -> AsyncIterator[str]:
        raise NotImplementedError

    async def generate_with_tools(
        self,
        *,
        system_instruction: str,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
    ) -> LLMToolResponse:
        """Tour de conversation avec tool calling natif du provider.

        Par défaut, non supporté : l'orchestrateur retombe alors sur
        `generate()` sans tool calling plutôt que de planter.
        """

        raise ToolCallingUnsupportedError(f"Provider '{self.name}' does not support tool calling.")