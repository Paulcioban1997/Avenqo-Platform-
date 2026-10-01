from uuid import UUID

import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.app.ai.chat.chat_service import ChatService
from backend.app.ai.request_identity import reconcile_idempotency_keys, resolve_ai_request_id
from backend.app.ai.central.routing import CentralAIIntentRouter
from backend.app.ai.chat.conversation_service import ConversationService
from backend.app.ai.chat.exceptions import AIServiceUnavailableError, ConversationNotFoundError
from backend.app.ai.tools.business.registry_factory import resolve_tenant_capabilities
from backend.app.ai.usage.exceptions import AIQuotaExceededError, AIRequestConflictError
from backend.app.core.permissions import permissions_for
from backend.app.core.rate_limit import rate_limit
from backend.app.database import get_db
from backend.app.dependencies.ai_chat import get_chat_service, get_conversation_service
from backend.app.dependencies.ai_engine import get_prediction_service
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, get_tenant_context
from backend.app.dependencies.ai_authorization import get_active_ai_membership
from backend.app.dependencies.assistants import get_assistant_registry
from backend.app.assistants.registry import AssistantRegistry, agent_entitlements
from backend.app.dependencies.tenant_business import (
    get_tenant_customers_service,
    get_tenant_sales_service,
)
from backend.app.services.retail_source_service import RetailSourceService
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.services.tenant_customers_service import TenantCustomersService
from backend.app.services.tenant_sales_service import TenantSalesService
from backend.app.schemas.ai_chat import ChatMessageResponse, ConversationDetailResponse, ConversationResponse, CreateConversationRequest, MessageResponse, SendMessageRequest, SourceResponse
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.prediction.service import PredictionService

router = APIRouter(
    prefix="/ai/chat",
    tags=["ai-chat"],
    dependencies=[Depends(get_active_ai_membership)],
)
logger = logging.getLogger("avenqo.ai.router")


def _retail_trusted_context(
    tenant: TenantContext,
    db: Session,
    sales: TenantSalesService,
    customers: TenantCustomersService,
) -> str:
    """Expose backend-computed Retail facts to Copilot without LLM inference."""

    try:
        active_source = next(
            (
                source
                for source in RetailSourceService(db).list_sources(tenant)
                if source.active and source.enabled
            ),
            None,
        )
        if active_source is None:
            return ""
        sales_data = sales.build(tenant, period_key="all")
        summary = sales_data.get("summary") or {}
        customer_data = customers.build(tenant, page=1, page_size=1)
        customer_total = customer_data.get("pagination", {}).get("total", 0)
        return (
            "Retail facts computed server-side from the active tenant source:\n"
            f"source={active_source.display_name}\n"
            f"source_type={active_source.source_type}\n"
            f"currency={sales_data.get('currency')}\n"
            f"revenue={summary.get('revenue')}\n"
            f"orders={summary.get('orders')}\n"
            f"customers={customer_total}\n"
            f"average_order_value={summary.get('average_order_value')}"
        )
    except Exception:
        logger.exception("Unable to build trusted Retail context for Copilot")
        return ""


def response(item) -> ConversationResponse:
    return ConversationResponse(id=item.id, title=item.title, created_at=item.created_at, updated_at=item.updated_at, locale=item.locale)


def _authorized_agent(query: str, page_context: str | None, tenant: TenantContext, db: Session, registry: AssistantRegistry):
    agent = CentralAIIntentRouter(registry).select(query, page_context=page_context)
    if agent is None:
        return None
    active_modules = frozenset(ModuleEntitlementService(db).get_active_modules(tenant))
    if not agent.status.is_executable or not agent_entitlements(agent).issubset(active_modules):
        raise HTTPException(status_code=403, detail="The requested AI agent is not available to this tenant.")
    return agent


@router.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create(request: CreateConversationRequest, tenant: TenantContext = Depends(get_tenant_context), identity: CurrentIdentity = Depends(get_current_identity), service: ConversationService = Depends(get_conversation_service)):
    return response(service.create(tenant.company_id, identity.user.id, request.title, request.locale or "fr"))


@router.get("/conversations", response_model=list[ConversationResponse])
def list_items(
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    membership=Depends(get_active_ai_membership),
    agent_registry: AssistantRegistry = Depends(get_assistant_registry),
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
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    service: ChatService = Depends(get_chat_service),
    db: Session = Depends(get_db),
    prediction_service: PredictionService = Depends(get_prediction_service),
    sales_service: TenantSalesService = Depends(get_tenant_sales_service),
    customers_service: TenantCustomersService = Depends(get_tenant_customers_service),
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
    permissions = frozenset(permissions_for(membership.role))
    capabilities = resolve_tenant_capabilities(db, tenant, prediction_service)
    agent = _authorized_agent(request.content, None, tenant, db, agent_registry)
    trusted_context = (
        _retail_trusted_context(tenant, db, sales_service, customers_service)
        if agent is not None and agent.module_code == "retail"
        else ""
    )
    company = identity.user.company
    plan_code = ModuleEntitlementService(db).get_company_plan(tenant).code.value
    try:
        request_id = resolve_ai_request_id(
            reconcile_idempotency_keys(idempotency_key, request.idempotency_key),
            tenant_id=tenant.company_id,
            user_id=identity.user.id,
            conversation_id=conversation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Idempotency-Key invalide") from exc
    try:
        item, sources = await service.send(
            tenant.company_id,
            identity.user.id,
            conversation_id,
            request.content,
            permissions=permissions,
            plan_code=plan_code,
            capabilities=capabilities,
            request_id=request_id,
            trusted_context=trusted_context,
            user_language=company.preferred_language or "fr",
            company_country=company.country or "",
            company_currency=getattr(company, "currency_code", None) or "USD",
            company_timezone=company.timezone or "UTC",
            selected_agent_id=agent.agent_id if agent is not None else None,
            allowed_tool_names=agent.allowed_tool_names if agent is not None else frozenset(),
            retrieve_tenant_data=agent is not None,
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation introuvable") from exc
    except AIQuotaExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except AIRequestConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    membership=Depends(get_active_ai_membership),
    agent_registry: AssistantRegistry = Depends(get_assistant_registry),
    service: ChatService = Depends(get_chat_service),
    db: Session = Depends(get_db),
    prediction_service: PredictionService = Depends(get_prediction_service),
    sales_service: TenantSalesService = Depends(get_tenant_sales_service),
    customers_service: TenantCustomersService = Depends(get_tenant_customers_service),
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
    permissions = frozenset(permissions_for(membership.role))
    capabilities = resolve_tenant_capabilities(db, tenant, prediction_service)
    company = identity.user.company
    agent = _authorized_agent(request.content, None, tenant, db, agent_registry)
    trusted_context = (
        _retail_trusted_context(tenant, db, sales_service, customers_service)
        if agent is not None and agent.module_code == "retail"
        else ""
    )
    plan_code = ModuleEntitlementService(db).get_company_plan(tenant).code.value
    try:
        request_id = resolve_ai_request_id(
            reconcile_idempotency_keys(idempotency_key, request.idempotency_key),
            tenant_id=tenant.company_id,
            user_id=identity.user.id,
            conversation_id=conversation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Idempotency-Key invalide") from exc

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
                plan_code=plan_code,
                capabilities=capabilities,
                request_id=request_id,
                trusted_context=trusted_context,
                is_cancelled=is_cancelled,
                user_language=company.preferred_language or "fr",
                company_country=company.country or "",
                company_currency=getattr(company, "currency_code", None) or "USD",
                company_timezone=company.timezone or "UTC",
                selected_agent_id=agent.agent_id if agent is not None else None,
                allowed_tool_names=agent.allowed_tool_names if agent is not None else frozenset(),
                retrieve_tenant_data=agent is not None,
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
        except (ConversationNotFoundError, AIServiceUnavailableError, AIQuotaExceededError, AIRequestConflictError) as exc:
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"
    return StreamingResponse(events(), media_type="text/event-stream")


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(conversation_id: UUID, tenant: TenantContext = Depends(get_tenant_context), identity: CurrentIdentity = Depends(get_current_identity), service: ConversationService = Depends(get_conversation_service)):
    try:
        service.delete(tenant.company_id, identity.user.id, conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation introuvable") from exc