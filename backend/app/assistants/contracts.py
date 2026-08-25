"""Contrat minimal de l'abstraction Assistant Avenqo.

Avenqo n'est PAS un chatbot : le chat est une des interfaces possibles
d'un "assistant" métier. Cette abstraction décrit UNIQUEMENT les métadonnées
nécessaires pour enregistrer/résoudre un assistant (Retail aujourd'hui,
CRM/Comptabilité/Legal/etc. demain) sans dupliquer l'infrastructure Core
(auth, billing, AI Gateway, Tool Registry, RAG, ingestion) que chaque
assistant réutilise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class AssistantStatus(StrEnum):
    """État commercial/fonctionnel d'un assistant."""

    AVAILABLE = "available"
    COMING_SOON = "coming_soon"
    BETA = "beta"
    DISABLED = "disabled"

    @property
    def is_executable(self) -> bool:
        """Un assistant COMING_SOON/DISABLED ne peut jamais exécuter d'outil,
        consommer de quota IA, ni accéder à un dataset."""

        return self in (AssistantStatus.AVAILABLE, AssistantStatus.BETA)


@dataclass(frozen=True, slots=True)
class AssistantDefinition:
    """Métadonnées déclaratives d'un assistant Avenqo.

    `module_code` relie l'assistant au `CompanyModule`/`Module` existant
    (ex: "retail") pour réutiliser l'entitlement/plan Core déjà en place,
    sans jamais dupliquer cette logique ici.
    """

    slug: str
    name_key: str
    description_key: str
    status: AssistantStatus
    category: str
    module_code: str | None = None
    minimum_plan: str | None = None
    required_capabilities: frozenset[str] = field(default_factory=frozenset)
    allowed_tool_names: frozenset[str] = field(default_factory=frozenset)
