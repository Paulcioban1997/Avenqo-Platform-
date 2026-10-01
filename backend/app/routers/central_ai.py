from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from backend.app.ai.chat.exceptions import AIServiceUnavailableError, ConversationNotFoundError
from backend.app.ai.usage.exceptions import AIRequestConflictError
from backend.app.ai.request_identity import reconcile_idempotency_keys, resolve_ai_request_id
from backend.app.ai.central.service import CentralAIService
from backend.app.ai.tools.business.registry_factory import resolve_tenant_capabilities
from backend.app.core.permissions import permissions_for
from backend.app.core.locale_catalog import resolve_locale
from backend.app.core.rate_limit import rate_limit
from backend.app.database import get_db
from backend.app.dependencies.ai_engine import get_prediction_service
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, get_tenant_context
from backend.app.dependencies.ai_authorization import get_active_ai_membership
from backend.app.dependencies.central_ai import get_central_ai_service
from backend.app.schemas.central_ai import CentralAIRequest, CentralAIResponse
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.prediction.service import PredictionService

router = APIRouter(
    prefix="/ai/central",
    tags=["central-ai"],
    dependencies=[Depends(get_active_ai_membership)],
)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=CentralAIResponse,
    dependencies=[Depends(rate_limit("central_ai_message", "rate_limit_ai_per_minute"))],
)
async def message(
    conversation_id: UUID,
    request: CentralAIRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    membership=Depends(get_active_ai_membership),
    service: CentralAIService = Depends(get_central_ai_service),
    db: Session = Depends(get_db),
    prediction_service: PredictionService = Depends(get_prediction_service),
) -> CentralAIResponse:
    try:
        client_idempotency_key = reconcile_idempotency_keys(idempotency_key, request.idempotency_key)
        request_id = resolve_ai_request_id(
            client_idempotency_key,
            tenant_id=tenant.company_id,
            user_id=identity.user.id,
            conversation_id=conversation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Idempotency-Key invalide") from exc
    if tenant.company_id != identity.user.company_id:
        raise HTTPException(status_code=403, detail="Contexte tenant invalide")
    company = identity.user.company
    from backend.app.services.retail_source_service import RetailSourceService
    active_source_name = None
    active_source_id_str = None
    source_service = RetailSourceService(db)
    if request.active_source_id and request.source_type:
        try:
            from uuid import UUID as PyUUID
            src = source_service.select_source(
                tenant, source_type=request.source_type, source_id=PyUUID(request.active_source_id)
            )
            if src.enabled:
                active_source_name = src.display_name
                active_source_id_str = str(src.source_id)
        except Exception:
            pass

    if not active_source_name:
        enabled_sources = [
            source for source in source_service.list_sources(tenant) if source.enabled
        ]
        if enabled_sources:
            active_source_name = ", ".join(
                source.display_name for source in enabled_sources
            )
            if len(enabled_sources) == 1:
                active_source_id_str = str(enabled_sources[0].source_id)

    try:
        result = await service.execute(
            tenant,
            identity.user.id,
            conversation_id,
            request.content,
            permissions=frozenset(permissions_for(membership.role)),
            capabilities=resolve_tenant_capabilities(db, tenant, prediction_service),
            request_id=request_id,
            user_language=resolve_locale(request.locale or company.preferred_language or "fr"),
            company_country=company.country or "",
            company_currency=getattr(company, "currency_code", None) or "USD",
            company_timezone=company.timezone or "UTC",
            page_context=request.page_context,
            locale_explicit=request.locale is not None,
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation introuvable") from exc
    except AIServiceUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AIRequestConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return CentralAIResponse(
        **asdict(result),
        conversation_id=conversation_id,
        grounded_source=f"Analyse basée sur : [{active_source_name}]" if active_source_name else None,
        source_id=active_source_id_str,
    )