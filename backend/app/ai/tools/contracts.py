"""Contrats stables du Tool Calling Avenqo (Phase 30).

`ToolExecutionContext` est construit EXCLUSIVEMENT par le backend authentifié
(jamais par le LLM ni par un argument client) : `tenant_id`, `user_id` et
`permissions` proviennent toujours de `CurrentIdentity`/`TenantContext`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from shared.ai_engine.contracts import TenantContext


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    """Contexte d'exécution sécurisé, jamais alimenté par le LLM."""

    tenant: TenantContext
    user_id: UUID
    permissions: frozenset[str]
    request_id: str
    conversation_id: UUID | None = None

    @property
    def tenant_id(self) -> UUID:
        return self.tenant.company_id


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Résultat standardisé renvoyé par un outil, jamais un objet ORM brut."""

    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    source_refs: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Représentation interne d'un outil, indépendante du provider LLM."""

    name: str
    description: str
    parameters_schema: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Appel d'outil décidé par le LLM (nom + arguments NON FIABLES)."""

    id: str
    name: str
    arguments: dict[str, Any]
    # Opaque, propre au fournisseur (ex. Gemini `thought_signature`) : à
    # rejouer TEL QUEL par le MÊME fournisseur lors du tour assistant suivant
    # (obligatoire pour les modèles Gemini "thinking" — jamais interprété ni
    # modifié, jamais transmis à un autre fournisseur).
    provider_metadata: bytes | None = None


@dataclass(frozen=True, slots=True)
class ToolCallResult:
    """Association d'un appel d'outil et de son résultat exécuté."""

    call: ToolCall
    result: ToolResult
