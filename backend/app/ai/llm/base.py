from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import contextmanager
from decimal import Decimal

from backend.app.ai.llm.exceptions import ToolCallingUnsupportedError
from backend.app.ai.llm.schemas import LLMGeneration, LLMMessage, LLMStreamChunk, LLMToolResponse, ToolDefinition


class LLMProvider(ABC):
    name: str
    supports_tool_calling: bool = False

    @contextmanager
    def routing(self, context: object):
        """Apply request routing hints when supported by the provider."""

        yield

    def estimate_cost_usd(self, context: object) -> Decimal | None:
        """Return a pre-execution provider-cost estimate when routing supports it."""

        return None

    @abstractmethod
    async def generate(self, *, system_instruction: str, prompt: str) -> LLMGeneration:
        raise NotImplementedError

    @abstractmethod
    async def stream(self, *, system_instruction: str, prompt: str) -> AsyncIterator[str]:
        raise NotImplementedError

    async def stream_events(
        self,
        *,
        system_instruction: str,
        prompt: str,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Usage-aware stream with a text-only compatibility default."""

        async for content in self.stream(system_instruction=system_instruction, prompt=prompt):
            yield LLMStreamChunk(content=content)

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