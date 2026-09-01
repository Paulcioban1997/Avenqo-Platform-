from dataclasses import asdict
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.ai.chat.exceptions import AIServiceUnavailableError, ConversationNotFoundError
from backend.app.ai.central.service import CentralAIService
from backend.app.ai.tools.business.registry_factory import resolve_tenant_capabilities
from backend.app.core.permissions import permissions_for
from backend.app.core.rate_limit import rate_limit
from backend.app.database import get_db
from backend.app.dependencies.ai_engine import get_prediction_service
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, get_tenant_context
from backend.app.dependencies.central_ai import get_central_ai_service
from backend.app.schemas.central_ai import CentralAIRequest, CentralAIResponse
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.prediction.service import PredictionService

router = APIRouter(prefix="/ai/central", tags=["central-ai"])


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=CentralAIResponse,
    dependencies=[Depends(rate_limit("central_ai_message", "rate_limit_ai_per_minute"))],
)
async def message(
    conversation_id: UUID,
    request: CentralAIRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    service: CentralAIService = Depends(get_central_ai_service),
    db: Session = Depends(get_db),
    prediction_service: PredictionService = Depends(get_prediction_service),
) -> CentralAIResponse:
    if tenant.company_id != identity.user.company_id:
        raise HTTPException(status_code=403, detail="Contexte tenant invalide")
    company = identity.user.company
    try:
        result = await service.execute(
            tenant,
            identity.user.id,
            conversation_id,
            request.content,
            permissions=frozenset(permissions_for(identity.user.role)),
            plan_code=company.subscription_plan,
            capabilities=resolve_tenant_capabilities(db, tenant, prediction_service),
            request_id=str(uuid4()),
            user_language=company.preferred_language or "fr",
            company_country=company.country or "",
            company_currency=getattr(company, "currency_code", None) or "USD",
            company_timezone=company.timezone or "UTC",
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation introuvable") from exc
    except AIServiceUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return CentralAIResponse(**asdict(result), conversation_id=conversation_id)