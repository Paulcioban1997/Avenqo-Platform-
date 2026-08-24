from __future__ import annotations

from dataclasses import dataclass, field

from backend.app.ai.tools.contracts import ToolCall, ToolDefinition


@dataclass(frozen=True, slots=True)
class LLMGeneration:
    content: str
    provider: str
    model: str
    token_usage: dict[str, object] = field(default_factory=dict)


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


__all__ = ["LLMGeneration", "LLMMessage", "LLMToolResponse", "ToolDefinition", "ToolCall"]