from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from backend.app.ai.tools.contracts import ToolCall, ToolDefinition


@dataclass(frozen=True, slots=True)
class LLMUsage:
    """Provider-independent, billable usage returned by one model call."""

    provider: str
    model: str
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    tool_calls: int = 0
    provider_request_id: str | None = None
    avenqo_request_id: str | None = None

    @property
    def total_tokens(self) -> int:
        # Cached input and reasoning tokens are subsets of input/output.
        return self.input_tokens + self.output_tokens

    def as_token_usage(self) -> dict[str, object]:
        return {
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "tool_calls": self.tool_calls,
            "provider_request_id": self.provider_request_id,
            "avenqo_request_id": self.avenqo_request_id,
        }


@dataclass(frozen=True, slots=True)
class LLMProviderAttempt:
    """One sequential provider attempt made for an Avenqo model operation."""

    provider: str
    model: str
    operation: str
    attempt_number: int
    success: bool
    latency_ms: int
    usage: LLMUsage
    failure_category: str | None = None
    provider_cost_usd: Decimal = Decimal("0")
    input_cost_per_million_usd: Decimal = Decimal("0")
    cached_input_cost_per_million_usd: Decimal = Decimal("0")
    output_cost_per_million_usd: Decimal = Decimal("0")
    tool_call_cost_usd: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class LLMStreamChunk:
    content: str = ""
    usage: LLMUsage | None = None
    attempts: tuple[LLMProviderAttempt, ...] = ()


@dataclass(frozen=True, slots=True)
class LLMGeneration:
    content: str
    provider: str
    model: str
    token_usage: dict[str, object] = field(default_factory=dict)
    attempts: tuple[LLMProviderAttempt, ...] = ()
    usage: LLMUsage | None = None


@dataclass(frozen=True, slots=True)
class LLMMessage:
    """Message provider-agnostique d'une conversation de tool calling."""

    role: str  # "user" | "assistant" | "tool"
    content: str
    tool_call_id: str | None = None
    name: str | None = None
    # Rempli UNIQUEMENT sur un message role="assistant" qui a demandé des
    # appels d'outils : chaque provider doit rejouer ce tour exactement tel
    # que le mod\u00e8le l'a produit avant les messages role="tool" qui suivent
    # (protocole exig\u00e9 par OpenAI/Anthropic/Gemini - sans ce tour, l'appel
    # suivant est rejet\u00e9 comme invalide par les 3 fournisseurs).
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True, slots=True)
class LLMToolResponse:
    """Réponse d'un tour de tool calling : soit du texte, soit des appels d'outil."""

    content: str | None
    tool_calls: tuple[ToolCall, ...]
    provider: str
    model: str
    token_usage: dict[str, object] = field(default_factory=dict)
    attempts: tuple[LLMProviderAttempt, ...] = ()
    usage: LLMUsage | None = None


__all__ = [
    "LLMGeneration",
    "LLMMessage",
    "LLMProviderAttempt",
    "LLMStreamChunk",
    "LLMToolResponse",
    "LLMUsage",
    "ToolDefinition",
    "ToolCall",
]