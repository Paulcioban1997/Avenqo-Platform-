"""Explicit registry of supported external LLM providers."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable


@dataclass(frozen=True, slots=True)
class LLMProviderDefinition:
    code: str
    credential_setting: str
    model_setting: str


class LLMProviderRegistry:
    def __init__(self, definitions: Iterable[LLMProviderDefinition] = ()) -> None:
        self._definitions: dict[str, LLMProviderDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: LLMProviderDefinition) -> None:
        code = definition.code.casefold()
        if not code or code in self._definitions:
            raise ValueError(f"Provider '{definition.code}' is already registered")
        self._definitions[code] = LLMProviderDefinition(
            code=code,
            credential_setting=definition.credential_setting,
            model_setting=definition.model_setting,
        )

    def get(self, code: str) -> LLMProviderDefinition | None:
        return self._definitions.get(code.casefold())

    def codes(self) -> tuple[str, ...]:
        return tuple(self._definitions)


DEFAULT_LLM_PROVIDER_REGISTRY = LLMProviderRegistry(
    (
        LLMProviderDefinition("openai", "openai_api_key", "openai_model"),
        LLMProviderDefinition("anthropic", "anthropic_api_key", "anthropic_model"),
        LLMProviderDefinition("gemini", "google_ai_api_key", "gemini_model"),
    )
)
