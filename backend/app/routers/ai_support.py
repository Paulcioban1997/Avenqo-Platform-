"""Avenqo Platform Support AI — routes REST + SSE (Phase 32).

Mirroir volontaire de `backend/app/routers/ai_chat.py` (Business Copilot),
sous un préfixe strictement séparé (`/support/chat`) et des tables séparées
— jamais partagé avec les conversations Business Copilot.
"""

from uuid import UUID, uuid4

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from backend.app.ai.chat.exceptions import AIServiceUnavailableError, ConversationNotFoundError
from backend.app.core.rate_limit import rate_limit
from backend.app.ai.support.chat_service import SupportChatService
from backend.app.ai.support.conversation_service import SupportConversationService
from backend.app.ai.usage.exceptions import AIQuotaExceededError
from backend.app.core.permissions import permissions_for
from backend.app.dependencies.ai_support import get_support_chat_service, get_support_conversation_service
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, get_tenant_context
from backend.app.schemas.ai_support_chat import (
    CreateSupportConversationRequest,
    SendSupportMessageRequest,
    SupportChatMessageResponse,
    SupportConversationDetailResponse,
    SupportConversationResponse,
    SupportMessageResponse,
    SupportSourceResponse,
)
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/support/chat", tags=["ai-support"])


def response(item) -> SupportConversationResponse:
    return SupportConversationResponse(id=item.id, title=item.title, created_at=item.created_at, updated_at=item.updated_at)


@router.post("/conversations", response_model=SupportConversationResponse, status_code=status.HTTP_201_CREATED)
def create(request: CreateSupportConversationRequest, tenant: TenantContext = Depends(get_tenant_context), identity: CurrentIdentity = Depends(get_current_identity), service: SupportConversationService = Depends(get_support_conversation_service)):
    return response(service.create(tenant.company_id, identity.user.id, request.title))


@router.get("/conversations", response_model=list[SupportConversationResponse])
def list_items(tenant: TenantContext = Depends(get_tenant_context), identity: CurrentIdentity = Depends(get_current_identity), service: SupportConversationService = Depends(get_support_conversation_service)):
    return [response(item) for item in service.list(tenant.company_id, identity.user.id)]


@router.get("/conversations/{conversation_id}", response_model=SupportConversationDetailResponse)
def detail(conversation_id: UUID, tenant: TenantContext = Depends(get_tenant_context), identity: CurrentIdentity = Depends(get_current_identity), service: SupportConversationService = Depends(get_support_conversation_service)):
    try:
        item = service.get(tenant.company_id, identity.user.id, conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation introuvable") from exc
    messages = [SupportMessageResponse(id=message.id, role=message.role.value, content=message.content, created_at=message.created_at) for message in service.messages(tenant.company_id, item.id)]
    return SupportConversationDetailResponse(**response(item).model_dump(), messages=messages)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=SupportChatMessageResponse,
    dependencies=[Depends(rate_limit("ai_support_message", "rate_limit_ai_per_minute"))],
)
async def message(
    conversation_id: UUID,
    request: SendSupportMessageRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    service: SupportChatService = Depends(get_support_chat_service),
):
    permissions = frozenset(permissions_for(identity.user.role))
    try:
        item, sources = await service.send(
            tenant.company_id,
            identity.user.id,
            conversation_id,
            request.content,
            permissions=permissions,
            plan_code=identity.user.company.subscription_plan,
            capabilities=frozenset(),
            request_id=str(uuid4()),
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation introuvable") from exc
    except AIQuotaExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except AIServiceUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return SupportChatMessageResponse(id=item.id, role=item.role.value, content=item.content, created_at=item.created_at, sources=[SupportSourceResponse(type=source.source_type, identifier=source.identifier, name=source.name, metadata=source.metadata) for source in sources])


@router.post(
    "/conversations/{conversation_id}/messages/stream",
    dependencies=[Depends(rate_limit("ai_support_message_stream", "rate_limit_ai_per_minute"))],
)
async def stream(
    conversation_id: UUID,
    request: SendSupportMessageRequest,
    http_request: Request,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    service: SupportChatService = Depends(get_support_chat_service),
):
    permissions = frozenset(permissions_for(identity.user.role))

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
                capabilities=frozenset(),
                request_id=str(uuid4()),
                is_cancelled=is_cancelled,
            ):
                if event.kind == "delta":
                    yield f"data: {json.dumps(event.payload)}\n\n"
                elif event.kind == "status":
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
def delete(conversation_id: UUID, tenant: TenantContext = Depends(get_tenant_context), identity: CurrentIdentity = Depends(get_current_identity), service: SupportConversationService = Depends(get_support_conversation_service)):
    try:
        service.delete(tenant.company_id, identity.user.id, conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation introuvable") from exc
