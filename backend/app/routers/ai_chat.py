from uuid import UUID

import json
import logging
import re
from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.app.ai.chat.chat_service import ChatService
from backend.app.ai.chat.orchestrator import compute_grounding_assessment, strip_raw_triple_stars
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
from backend.app.dependencies.subscription import require_active_subscription
from backend.app.dependencies.assistants import get_assistant_registry
from backend.app.assistants.registry import AssistantRegistry, agent_entitlements
from backend.app.dependencies.tenant_business import (
    get_tenant_customers_service,
    get_tenant_sales_service,
)
from backend.app.services.retail_source_service import RetailSourceService
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.services.tenant_locale_service import get_company_locale
from backend.app.services.tenant_customers_service import TenantCustomersService
from backend.app.services.tenant_sales_service import TenantSalesService
from backend.app.schemas.ai_chat import (
    ChatMessageResponse,
    ConversationDetailResponse,
    ConversationResponse,
    CreateConversationRequest,
    MessageResponse,
    SendMessageRequest,
    SourceResponse,
)
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.prediction.service import PredictionService

router = APIRouter(
    prefix="/ai/chat",
    tags=["ai-chat"],
    dependencies=[Depends(get_active_ai_membership)],
)
logger = logging.getLogger("avenqo.ai.router")

_DOCUMENT_INVOICE_QUERY_RE = re.compile(
    r"\b(?:facture|factures|invoice|invoices|montant|total|totaux|amount|solde|balance|"
    r"sous-total|subtotal|tps|tvq|gst|qst|hst|po|document|documents|ocr|scan|excel|xlsx|xlsm|"
    r"onglet|sheet|cellule|cell|piece|justificatif|recu)\b",
    re.IGNORECASE,
)


def _augment_structured_document_tools(
    query: str,
    *,
    allowed_tools: frozenset[str],
    authorized_tool_agents: dict[str, str],
    active_modules: frozenset[str],
    permissions: frozenset[str],
) -> tuple[frozenset[str], dict[str, str]]:
    """Garantit l'injection des outils structurés `extract_invoice_totals`, `get_document_source`
    et `get_document_cell_evidence` lorsque le tenant possède `ocr` ou `accounting` actif
    et que la question porte sur une facture, un montant, un onglet ou un document."""
    if "data:read" not in permissions or "ai:use" not in permissions:
        return allowed_tools, authorized_tool_agents
    if not _DOCUMENT_INVOICE_QUERY_RE.search(query):
        return allowed_tools, authorized_tool_agents

    owner_agent = "ocr" if "ocr" in active_modules else ("accounting" if "accounting" in active_modules else None)
    if owner_agent is None:
        return allowed_tools, authorized_tool_agents

    extra_tools: list[str] = [
        "extract_invoice_totals",
        "get_document_source",
        "get_document_cell_evidence",
    ]
    if "ocr" in active_modules:
        extra_tools.extend(["search_documents", "get_document_detail", "get_ocr_document"])

    merged_names = list(allowed_tools)
    merged_agents = dict(authorized_tool_agents)
    for t_name in extra_tools:
        if t_name not in merged_names:
            merged_names.append(t_name)
        merged_agents.setdefault(t_name, owner_agent)

    # Conserver la priorité aux outils structurés documentaires dans la borne de sécurité (max 8)
    if len(merged_names) > 8:
        prioritized = [t for t in extra_tools if t in merged_names]
        for existing in merged_names:
            if existing not in prioritized and len(prioritized) < 8:
                prioritized.append(existing)
        merged_names = prioritized
        merged_agents = {t: merged_agents[t] for t in merged_names if t in merged_agents}

    return frozenset(merged_names), merged_agents


def _enrich_source_metadata(
    source_meta: dict[str, object],
    assessment: dict[str, Any],
    *,
    source_identifier: str | None = None,
    source_name: str | None = None,
    tool_call_results: Sequence[Any] = (),
) -> dict[str, object]:
    """Enrichit les métadonnées d'une source uniquement avec les preuves propres à cette source :
    ne marque JAMAIS `certified_grounding=True` sur un dataset/document non inspecté ou metadata-only."""
    meta = dict(source_meta or {})
    source_doc_id = str(meta.get("document_id") or source_identifier or "").strip()
    source_filename = str(meta.get("filename") or source_name or "").strip().casefold()
    source_tool = str(meta.get("tool") or "").strip()

    matched_results: list[Any] = []
    for cr in tool_call_results:
        res = getattr(cr, "result", None)
        if res is None or not getattr(res, "success", False):
            continue
        raw_cr_meta = getattr(res, "metadata", None)
        cr_meta: dict[str, Any] = raw_cr_meta if isinstance(raw_cr_meta, dict) else {}
        raw_cr_data = getattr(res, "data", None)
        cr_data: dict[str, Any] = raw_cr_data if isinstance(raw_cr_data, dict) else {}
        cr_doc_id = str(cr_meta.get("document_id") or cr_data.get("document_id") or "").strip()
        cr_fname = str(cr_meta.get("filename") or cr_data.get("filename") or "").strip().casefold()
        call_name = str(getattr(getattr(cr, "call", None), "name", "") or "")

        if source_doc_id and cr_doc_id and source_doc_id == cr_doc_id:
            matched_results.append(cr)
        elif source_filename and cr_fname and source_filename == cr_fname:
            matched_results.append(cr)
        elif source_tool and not cr_doc_id and not cr_fname and source_tool == call_name:
            matched_results.append(cr)

    if matched_results:
        scoped_assessment = compute_grounding_assessment(matched_results)
    elif source_tool and not tool_call_results:
        scoped_assessment = assessment
    else:
        scoped_assessment = {
            "grounding_status": "preview_only",
            "certified_grounding": False,
            "grounding_badge": "preview_only",
            "full_source_read": False,
            "math_verified": False,
            "provenance": [],
        }

    if "tool" in meta:
        meta["grounding_status"] = scoped_assessment["grounding_status"]
        meta["certified_grounding"] = scoped_assessment["certified_grounding"]
        meta["grounding_badge"] = scoped_assessment["grounding_badge"]
        meta["full_source_read"] = scoped_assessment["full_source_read"]
        meta["math_verified"] = scoped_assessment["math_verified"]
        if scoped_assessment.get("provenance"):
            meta["provenance"] = scoped_assessment["provenance"]
    else:
        # Source issue de `RetrievalService` (métadonnées seules `Dataset: name; lignes; colonnes`) :
        # ne reçoit un badge certifié QUE si un outil de lecture complète a vérifié CETTE source précise.
        if matched_results and scoped_assessment["certified_grounding"] and scoped_assessment["full_source_read"]:
            meta["grounding_status"] = scoped_assessment["grounding_status"]
            meta["certified_grounding"] = True
            meta["grounding_badge"] = scoped_assessment["grounding_badge"]
            meta["full_source_read"] = True
            meta["math_verified"] = scoped_assessment["math_verified"]
            if scoped_assessment.get("provenance"):
                meta["provenance"] = scoped_assessment["provenance"]
        else:
            meta["grounding_status"] = (
                scoped_assessment["grounding_status"]
                if matched_results and scoped_assessment["grounding_status"] in {"uncertain_candidates", "missing_after_full_read"}
                else "preview_only"
            )
            meta["certified_grounding"] = False
            meta["grounding_badge"] = str(meta["grounding_status"])
            meta["full_source_read"] = False
            meta["math_verified"] = False
            meta["is_metadata_preview"] = True
    return meta


def _retail_trusted_context(
    tenant: TenantContext,
    db: Session,
    sales: TenantSalesService,
    customers: TenantCustomersService,
) -> str:
    """Expose backend-computed Retail facts to Copilot without LLM inference."""

    try:
        source_service = RetailSourceService(db)
        selection = source_service.active_selection(tenant)
        all_sources = source_service.list_sources(tenant)
        enabled_sources = [s for s in all_sources if s.enabled]
        if not enabled_sources:
            return ""

        if selection is not None and getattr(selection, "source_type", None) == "all":
            source_display = "Toutes les sources consolidées"
            source_type = "all"
        else:
            active_source = next(
                (s for s in all_sources if s.active and s.enabled),
                None,
            )
            if active_source is None:
                if selection is None or getattr(selection, "source_type", None) == "all":
                    source_display = "Toutes les sources consolidées"
                    source_type = "all"
                else:
                    return ""
            else:
                source_display = active_source.display_name
                source_type = active_source.source_type

        sales_data = sales.build(tenant, period_key="all")
        summary = sales_data.get("summary") or {}
        customer_data = customers.build(tenant, page=1, page_size=1)
        customer_total = customer_data.get("pagination", {}).get("total", 0)
        return (
            "Retail facts computed server-side from the active tenant source:\n"
            f"source={source_display}\n"
            f"source_type={source_type}\n"
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
    return ConversationResponse(
        id=item.id,
        title=item.title,
        created_at=item.created_at,
        updated_at=item.updated_at,
        locale=item.locale,
    )


def _authorized_agent(
    query: str,
    page_context: str | None,
    tenant: TenantContext,
    db: Session,
    registry: AssistantRegistry,
):
    agent = CentralAIIntentRouter(registry).select(query, page_context=page_context)
    if agent is None:
        return None
    active_modules = frozenset(ModuleEntitlementService(db).get_active_modules(tenant))
    if not agent.status.is_executable or not agent_entitlements(agent).issubset(active_modules):
        raise HTTPException(status_code=403, detail="The requested AI agent is not available to this tenant.")
    return agent


@router.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create(
    request: CreateConversationRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    service: ConversationService = Depends(get_conversation_service),
):
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
def detail(
    conversation_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    service: ConversationService = Depends(get_conversation_service),
):
    try:
        item = service.get(tenant.company_id, identity.user.id, conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation introuvable") from exc
    messages = [
        MessageResponse(
            id=message.id,
            role=message.role.value,
            content=message.content,
            created_at=message.created_at,
        )
        for message in service.messages(tenant.company_id, item.id)
    ]
    return ConversationDetailResponse(**response(item).model_dump(), messages=messages)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ChatMessageResponse,
    dependencies=[Depends(require_active_subscription), Depends(rate_limit("ai_chat_message", "rate_limit_ai_per_minute"))],
)
async def message(
    conversation_id: UUID,
    request: SendMessageRequest,
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
    active_modules = frozenset(ModuleEntitlementService(db).get_active_modules(tenant))
    from backend.app.ai.central.universal_planner import UniversalCapabilityPlanner

    planner = UniversalCapabilityPlanner(agent_registry, getattr(service, "_tool_registry", None))
    planned = planner.plan_tool_scope(
        request.content,
        active_modules=active_modules,
        permissions=permissions,
        detected_agent=agent,
    )
    allowed_tools = (
        planned.allowed_tool_names
        if planned.allowed_tool_names
        else (agent.allowed_tool_names if agent is not None else frozenset())
    )
    authorized_tool_agents = dict(planned.authorized_tool_agents)
    if agent is not None:
        for t_name in allowed_tools:
            authorized_tool_agents.setdefault(t_name, agent.agent_id)
    allowed_tools, authorized_tool_agents = _augment_structured_document_tools(
        request.content,
        allowed_tools=allowed_tools,
        authorized_tool_agents=authorized_tool_agents,
        active_modules=active_modules,
        permissions=permissions,
    )

    trusted_context = (
        _retail_trusted_context(tenant, db, sales_service, customers_service)
        if (
            "retail" in active_modules
            and ((agent is not None and agent.module_code == "retail") or "retail" in planned.targeted_modules)
        )
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
            user_language=get_company_locale(db, company.id) or company.preferred_language,
            company_country=company.country or "",
            company_currency=getattr(company, "currency_code", None) or "USD",
            company_timezone=company.timezone or "UTC",
            selected_agent_id=agent.agent_id if agent is not None else None,
            allowed_tool_names=allowed_tools,
            authorized_tool_agents=authorized_tool_agents,
            retrieve_tenant_data=bool(allowed_tools) or agent is not None,
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation introuvable") from exc
    except AIQuotaExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except AIRequestConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AIServiceUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    tool_results = getattr(service, "last_tool_call_results", ())
    assessment = compute_grounding_assessment(tool_results)
    return ChatMessageResponse(
        id=item.id,
        role=item.role.value,
        content=strip_raw_triple_stars(item.content),
        created_at=item.created_at,
        sources=[
            SourceResponse(
                type=source.source_type,
                identifier=source.identifier,
                name=source.name,
                metadata=_enrich_source_metadata(
                    source.metadata,
                    assessment,
                    source_identifier=source.identifier,
                    source_name=source.name,
                    tool_call_results=tool_results,
                ),
            )
            for source in sources
        ],
    )


@router.post(
    "/conversations/{conversation_id}/messages/stream",
    dependencies=[Depends(require_active_subscription), Depends(rate_limit("ai_chat_message_stream", "rate_limit_ai_per_minute"))],
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
    active_modules = frozenset(ModuleEntitlementService(db).get_active_modules(tenant))
    from backend.app.ai.central.universal_planner import UniversalCapabilityPlanner

    planner = UniversalCapabilityPlanner(agent_registry, getattr(service, "_tool_registry", None))
    planned = planner.plan_tool_scope(
        request.content,
        active_modules=active_modules,
        permissions=permissions,
        detected_agent=agent,
    )
    allowed_tools = (
        planned.allowed_tool_names
        if planned.allowed_tool_names
        else (agent.allowed_tool_names if agent is not None else frozenset())
    )
    authorized_tool_agents = dict(planned.authorized_tool_agents)
    if agent is not None:
        for t_name in allowed_tools:
            authorized_tool_agents.setdefault(t_name, agent.agent_id)
    allowed_tools, authorized_tool_agents = _augment_structured_document_tools(
        request.content,
        allowed_tools=allowed_tools,
        authorized_tool_agents=authorized_tool_agents,
        active_modules=active_modules,
        permissions=permissions,
    )

    trusted_context = (
        _retail_trusted_context(tenant, db, sales_service, customers_service)
        if (
            "retail" in active_modules
            and ((agent is not None and agent.module_code == "retail") or "retail" in planned.targeted_modules)
        )
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
                user_language=get_company_locale(db, company.id) or company.preferred_language,
                company_country=company.country or "",
                company_currency=getattr(company, "currency_code", None) or "USD",
                company_timezone=company.timezone or "UTC",
                selected_agent_id=agent.agent_id if agent is not None else None,
                allowed_tool_names=allowed_tools,
                authorized_tool_agents=authorized_tool_agents,
                retrieve_tenant_data=bool(allowed_tools) or agent is not None,
            ):
                if event.kind == "delta":
                    yield f"data: {json.dumps(event.payload)}\n\n"
                elif event.kind == "status":
                    yield f"event: status\ndata: {json.dumps(event.payload)}\n\n"
                elif event.kind == "sources":
                    tool_results_seq = getattr(service, "last_tool_call_results", ())
                    assessment = compute_grounding_assessment(tool_results_seq)
                    raw_sources = event.payload.get("sources")
                    enriched_sources = (
                        [
                            {
                                **src,
                                "metadata": _enrich_source_metadata(
                                    dict(src.get("metadata") or {}) if isinstance(src.get("metadata"), dict) else {},
                                    assessment,
                                    source_identifier=str(src.get("identifier") or "") or None,
                                    source_name=str(src.get("name") or "") or None,
                                    tool_call_results=tool_results_seq,
                                ),
                            }
                            for src in raw_sources
                            if isinstance(src, dict)
                        ]
                        if isinstance(raw_sources, list)
                        else []
                    )
                    yield f"data: {json.dumps({'sources': enriched_sources, 'grounding': assessment})}\n\n"
                elif event.kind == "done":
                    assessment = compute_grounding_assessment(getattr(service, "last_tool_call_results", ()))
                    done_payload = {**event.payload, "grounding_status": assessment["grounding_status"], "certified_grounding": assessment["certified_grounding"]}
                    yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"
                elif event.kind == "error":
                    yield f"event: error\ndata: {json.dumps(event.payload)}\n\n"
        except (ConversationNotFoundError, AIServiceUnavailableError, AIQuotaExceededError, AIRequestConflictError) as exc:
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(
    conversation_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    service: ConversationService = Depends(get_conversation_service),
):
    try:
        service.delete(tenant.company_id, identity.user.id, conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation introuvable") from exc
