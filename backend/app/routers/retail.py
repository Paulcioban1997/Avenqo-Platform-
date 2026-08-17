"""Façade HTTP orientée métier du module RetailSense."""

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.dependencies.auth import get_tenant_context
from backend.app.dependencies.retail import get_retail_assistant
from backend.app.schemas.retail_assistant import RetailAssistantRequest, RetailAssistantResponse
from modules.entitlements import ModuleAccessDenied
from modules.retailsense.assistant import RetailAssistantService
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/retail", tags=["retail"])


@router.post("/assistant", response_model=RetailAssistantResponse)
def ask_retail_assistant(
    request: RetailAssistantRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    assistant: RetailAssistantService = Depends(get_retail_assistant),
) -> RetailAssistantResponse:
    try:
        reply = assistant.answer(tenant, request.question)
    except ModuleAccessDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return RetailAssistantResponse(
        answer=reply.answer,
        suggested_actions=list(reply.suggested_actions),
    )