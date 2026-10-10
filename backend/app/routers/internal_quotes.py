"""Réessai interne des envois de devis Enterprise."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.dependencies.internal import require_internal_service_token
from backend.app.dependencies.quotes import get_enterprise_quote_service
from backend.app.services.enterprise_quote_service import EnterpriseQuoteService

router = APIRouter(tags=["internal-quotes"])


@router.post("/enterprise-quotes/retry", dependencies=[Depends(require_internal_service_token)])
def retry_enterprise_quote_deliveries(
    service: EnterpriseQuoteService = Depends(get_enterprise_quote_service),
) -> dict[str, int]:
    return {"sent": service.dispatch_pending()}
