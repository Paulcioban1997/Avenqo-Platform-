"""Schémas Pydantic pour la sélection multi-sources par entreprise (Workspace)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SourceSelectionMode = Literal["ALL", "CUSTOM_SET", "SINGLE"]


class SourceItemResponse(BaseModel):
    """Représentation normalisée d'une source dans l'espace de sélection."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_type: str
    display_name: str
    provider: str | None = None
    status: str
    enabled: bool = True
    last_synchronized_at: datetime | None = None
    is_selected: bool = False


class WorkspaceSourceSelectionRequest(BaseModel):
    """Requête de mise à jour du mode et des sources sélectionnées."""
    model_config = ConfigDict(extra="forbid")

    mode: SourceSelectionMode
    selected_source_ids: list[UUID] = Field(default_factory=list)


class WorkspaceSourceSelectionResponse(BaseModel):
    """Réponse complète sur la sélection des sources pour l'entreprise."""
    model_config = ConfigDict(from_attributes=True)

    mode: SourceSelectionMode
    selected_source_ids: list[UUID]
    selected_sources: list[SourceItemResponse]
    available_sources: list[SourceItemResponse]
    effective_count: int
