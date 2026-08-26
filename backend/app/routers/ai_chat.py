from uuid import UUID, uuid4

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.app.ai.chat.chat_service import ChatService
from backend.app.ai.chat.conversation_service import ConversationService
from backend.app.ai.chat.exceptions import AIServiceUnavailableError, ConversationNotFoundError
from backend.app.ai.tools.business.registry_factory import resolve_tenant_capabilities
from backend.app.ai.usage.exceptions import AIQuotaExceededError
from backend.app.core.permissions import permissions_for
from backend.app.core.rate_limit import rate_limit
from backend.app.database import get_db
from backend.app.dependencies.ai_chat import get_chat_service, get_conversation_service
from backend.app.dependencies.ai_engine import get_prediction_service
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, get_tenant_context
from backend.app.schemas.ai_chat import ChatMessageResponse, ConversationDetailResponse, ConversationResponse, CreateConversationRequest, MessageResponse, SendMessageRequest, SourceResponse
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.prediction.service import PredictionService

router = APIRouter(prefix="/ai/chat", tags=["ai-chat"])
logger = logging.getLogger("avenqo.ai.router")


def response(item) -> ConversationResponse:
    return ConversationResponse(id=item.id, title=item.title, created_at=item.created_at, updated_at=item.updated_at)


@router.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create(request: CreateConversationRequest, tenant: TenantContext = Depends(get_tenant_context), identity: CurrentIdentity = Depends(get_current_identity), service: ConversationService = Depends(get_conversation_service)):
    return response(service.create(tenant.company_id, identity.user.id, request.title))


@router.get("/conversations", response_model=list[ConversationResponse])
def list_items(
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    service: ConversationService = Depends(get_conversation_service),
    skip: int = 0,
    limit: int = 50,
):
    limit = min(max(limit, 1), 200)
    skip = max(skip, 0)
    return [response(item) for item in service.list(tenant.company_id, identity.user.id)][skip : skip + limit]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
def detail(conversation_id: UUID, tenant: TenantContext = Depends(get_tenant_context), identity: CurrentIdentity = Depends(get_current_identity), service: ConversationService = Depends(get_conversation_service)):
    try:
        item = service.get(tenant.company_id, identity.user.id, conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation introuvable") from exc
    messages = [MessageResponse(id=message.id, role=message.role.value, content=message.content, created_at=message.created_at) for message in service.messages(tenant.company_id, item.id)]
    return ConversationDetailResponse(**response(item).model_dump(), messages=messages)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ChatMessageResponse,
    dependencies=[Depends(rate_limit("ai_chat_message", "rate_limit_ai_per_minute"))],
)
async def message(
    conversation_id: UUID,
    request: SendMessageRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    service: ChatService = Depends(get_chat_service),
    db: Session = Depends(get_db),
    prediction_service: PredictionService = Depends(get_prediction_service),
):
    if tenant.company_id != identity.user.company_id:
        logger.error(
            "ai_chat_tenant_mismatch user_id=%s identity_company_id=%s tenant_company_id=%s",
            identity.user.id,
            identity.user.company_id,
            tenant.company_id,
        )
        raise HTTPException(status_code=403, detail="Contexte tenant invalide")
    logger.info(
        "ai_chat_identity user_id=%s identity_company_id=%s tenant_company_id=%s",
        identity.user.id,
        identity.user.company_id,
        tenant.company_id,
    )
    permissions = frozenset(permissions_for(identity.user.role))
    capabilities = resolve_tenant_capabilities(db, tenant, prediction_service)
    try:
        item, sources = await service.send(
            tenant.company_id,
            identity.user.id,
            conversation_id,
            request.content,
            permissions=permissions,
            plan_code=identity.user.company.subscription_plan,
            capabilities=capabilities,
            request_id=str(uuid4()),
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation introuvable") from exc
    except AIQuotaExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except AIServiceUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ChatMessageResponse(id=item.id, role=item.role.value, content=item.content, created_at=item.created_at, sources=[SourceResponse(type=source.source_type, identifier=source.identifier, name=source.name, metadata=source.metadata) for source in sources])


@router.post(
    "/conversations/{conversation_id}/messages/stream",
    dependencies=[Depends(rate_limit("ai_chat_message_stream", "rate_limit_ai_per_minute"))],
)
async def stream(
    conversation_id: UUID,
    request: SendMessageRequest,
    http_request: Request,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    service: ChatService = Depends(get_chat_service),
    db: Session = Depends(get_db),
    prediction_service: PredictionService = Depends(get_prediction_service),
):
    if tenant.company_id != identity.user.company_id:
        logger.error(
            "ai_chat_stream_tenant_mismatch user_id=%s identity_company_id=%s tenant_company_id=%s",
            identity.user.id,
            identity.user.company_id,
            tenant.company_id,
        )
        raise HTTPException(status_code=403, detail="Contexte tenant invalide")
    logger.info(
        "ai_chat_stream_identity user_id=%s identity_company_id=%s tenant_company_id=%s",
        identity.user.id,
        identity.user.company_id,
        tenant.company_id,
    )
    permissions = frozenset(permissions_for(identity.user.role))
    capabilities = resolve_tenant_capabilities(db, tenant, prediction_service)

    async def is_cancelled() -> bool:
        return await http_request.is_disconnected()

    async def events():
        try:
            async for event in service.stream(
                tenant.company_id,
                identity.user.id,
                conversation_id,
                request.content,
                permissions=permissions,
                plan_code=identity.user.company.subscription_plan,
                capabilities=capabilities,
                request_id=str(uuid4()),
                is_cancelled=is_cancelled,
            ):
                if event.kind == "delta":
                    yield f"data: {json.dumps(event.payload)}\n\n"
                elif event.kind == "status":
                    # Statut générique uniquement ("Analyzing your business data..."),
                    # jamais de nom d'outil, d'arguments ou d'appel provider.
                    yield f"event: status\ndata: {json.dumps(event.payload)}\n\n"
                elif event.kind == "sources":
                    yield f"data: {json.dumps(event.payload)}\n\n"
                elif event.kind == "done":
                    yield f"event: done\ndata: {json.dumps(event.payload)}\n\n"
                elif event.kind == "error":
                    yield f"event: error\ndata: {json.dumps(event.payload)}\n\n"
        except (ConversationNotFoundError, AIServiceUnavailableError, AIQuotaExceededError) as exc:
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"
    return StreamingResponse(events(), media_type="text/event-stream")


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(conversation_id: UUID, tenant: TenantContext = Depends(get_tenant_context), identity: CurrentIdentity = Depends(get_current_identity), service: ConversationService = Depends(get_conversation_service)):
    try:
        service.delete(tenant.company_id, identity.user.id, conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation introuvable") from exc