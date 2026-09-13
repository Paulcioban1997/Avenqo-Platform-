"""Façade HTTP orientée métier du module RetailSense."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.auth import get_tenant_context
from backend.app.dependencies.retail import get_retail_assistant
from backend.app.schemas.retail_assistant import RetailAssistantRequest, RetailAssistantResponse
from backend.app.schemas.retail_sources import (
    RetailSourceResponse,
    RetailSourceSelectionRequest,
)
from backend.app.services.retail_source_service import (
    RetailSourceNotFound,
    RetailSourceService,
)
from modules.entitlements import ModuleAccessDenied
from modules.retailsense.assistant import RetailAssistantService
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/retail", tags=["retail"])


@router.get("/sources", response_model=list[RetailSourceResponse])
def retail_sources(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> list[RetailSourceResponse]:
    return [
        RetailSourceResponse.model_validate(source, from_attributes=True)
        for source in RetailSourceService(db).list_sources(tenant)
    ]


@router.put("/sources/active", response_model=RetailSourceResponse)
def select_retail_source(
    request: RetailSourceSelectionRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> RetailSourceResponse:
    try:
        source = RetailSourceService(db).select_source(
            tenant,
            source_type=request.source_type,
            source_id=request.source_id,
        )
    except RetailSourceNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Retail source not found",
        ) from exc
    return RetailSourceResponse.model_validate(source, from_attributes=True)


@router.post("/assistant", response_model=RetailAssistantResponse)
def ask_retail_assistant(
    request: RetailAssistantRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    assistant: RetailAssistantService = Depends(get_retail_assistant),
    db: Session = Depends(get_db),
) -> RetailAssistantResponse:
    active_source_name = None
    active_source_id_str = None
    if request.source_id and request.source_type:
        try:
            source = RetailSourceService(db).select_source(
                tenant, source_type=request.source_type, source_id=request.source_id
            )
            active_source_name = source.display_name
            active_source_id_str = str(source.id)
        except Exception:
            pass

    if not active_source_name:
        sources = RetailSourceService(db).list_sources(tenant)
        active_src = next((s for s in sources if s.active), None)
        if active_src:
            active_source_name = active_src.display_name
            active_source_id_str = str(active_src.id)

    try:
        reply = assistant.answer(tenant, request.question)
    except ModuleAccessDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return RetailAssistantResponse(
        answer=reply.answer,
        suggested_actions=list(reply.suggested_actions),
        grounded_source=f"Analyse basée sur : [{active_source_name}]" if active_source_name else None,
        source_id=active_source_id_str,
    )