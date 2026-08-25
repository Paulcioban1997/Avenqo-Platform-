"""Façade HTTP du registre d'assistants Avenqo (lecture seule).

Ne fait qu'exposer le statut déclaratif des assistants (Retail AVAILABLE,
autres COMING_SOON). N'exécute jamais d'outil ni n'accède à des données
tenant : ceci reste la responsabilité de `/ai/chat` et de son Tool Registry.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.assistants.registry import AssistantRegistry
from backend.app.dependencies.assistants import get_assistant_registry
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity
from backend.app.schemas.assistants import AssistantResponse

router = APIRouter(prefix="/assistants", tags=["assistants"])


def _to_response(definition) -> AssistantResponse:
    return AssistantResponse(
        slug=definition.slug,
        name_key=definition.name_key,
        description_key=definition.description_key,
        status=definition.status.value,
        category=definition.category,
        available=definition.status.is_executable,
    )


@router.get("", response_model=list[AssistantResponse])
def list_assistants(
    identity: CurrentIdentity = Depends(get_current_identity),
    registry: AssistantRegistry = Depends(get_assistant_registry),
):
    return [_to_response(item) for item in registry.list_all()]


@router.get("/{slug}", response_model=AssistantResponse)
def get_assistant(
    slug: str,
    identity: CurrentIdentity = Depends(get_current_identity),
    registry: AssistantRegistry = Depends(get_assistant_registry),
):
    definition = registry.get(slug)
    if definition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assistant introuvable")
    return _to_response(definition)
