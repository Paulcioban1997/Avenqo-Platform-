"""Soumission publique des demandes de devis Enterprise (landing)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from backend.app.core.error_localization import localized_api_message
from backend.app.core.rate_limit import rate_limit
from backend.app.dependencies.quotes import get_enterprise_quote_service
from backend.app.schemas.billing import (
    EnterpriseQuoteDeliveryReportRequest,
    EnterpriseQuoteResponse,
    PublicEnterpriseQuoteRequest,
)
from backend.app.services.enterprise_quote_service import EnterpriseQuoteService, QuoteSubmission

router = APIRouter(prefix="/public", tags=["public-quotes"])


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post(
    "/enterprise-quote",
    response_model=EnterpriseQuoteResponse,
    dependencies=[Depends(rate_limit("public_enterprise_quote", "rate_limit_quote_per_minute"))],
)
def submit_public_enterprise_quote(
    http_request: Request,
    request: PublicEnterpriseQuoteRequest,
    service: EnterpriseQuoteService = Depends(get_enterprise_quote_service),
) -> EnterpriseQuoteResponse:
    quote = service.submit(
        QuoteSubmission(
            source="landing",
            contact_name=request.name,
            contact_email=request.email,
            company_name=request.company,
            contact_phone=request.phone,
            need=request.need,
            message=request.message,
            requested_modules=[],
            estimated_users=None,
            monthly_volume=None,
            required_integrations=[],
            website=request.website,
        ),
        _client_key(http_request),
    )
    response = _response(http_request, quote)
    if quote.notification_status != "sent":
        payload = response.model_dump(mode="json")
        payload["detail"] = (
            f"La demande {quote.reference_id} a été enregistrée, mais l'envoi "
            "aux destinataires Avenqo n'a pas été confirmé."
        )
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload)
    return response


@router.post(
    "/enterprise-quote/{reference_id}/deliveries",
    response_model=EnterpriseQuoteResponse,
    dependencies=[Depends(rate_limit("public_enterprise_quote_report", "rate_limit_quote_per_minute"))],
)
def report_public_enterprise_quote_delivery(
    reference_id: str,
    request: EnterpriseQuoteDeliveryReportRequest,
    http_request: Request,
    service: EnterpriseQuoteService = Depends(get_enterprise_quote_service),
) -> EnterpriseQuoteResponse:
    if not request.deliveries:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Aucune livraison à enregistrer.")
    quote = service.mark_delivered(
        reference_id,
        [item.model_dump() for item in request.deliveries],
    )
    if quote.notification_status != "sent":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"La demande {quote.reference_id} n'a pas encore été confirmée par le fournisseur.",
        )
    return _response(http_request, quote)


def _response(http_request: Request, quote) -> EnterpriseQuoteResponse:
    return EnterpriseQuoteResponse(
        reference_id=quote.reference_id,
        status=quote.status,
        message=localized_api_message(
            http_request.headers.get("accept-language"), "enterprise_quote_received"
        ),
        created_at=quote.submitted_at or quote.created_at,
        notification_status=quote.notification_status,
        acknowledgment_status=quote.acknowledgment_status,
    )
