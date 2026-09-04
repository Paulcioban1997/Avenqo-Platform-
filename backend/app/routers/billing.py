"""Routes de facturation Stripe du tenant courant."""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse as HTTPRedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings, get_settings
from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, require_permission
from backend.app.dependencies.billing import get_billing_provider, get_billing_service, get_invoice_fiscal_service
from backend.app.core.rate_limit import rate_limit
from backend.app.schemas.billing import (
    AICreditBalanceResponse,
    ChangePlanRequest,
    CheckoutRequest,
    CreditPackCheckoutRequest,
    CreditPackResponse,
    InvoiceResponse,
    InvoiceFiscalSummaryResponse,
    InvoiceHistoryResponse,
    PlanResponse,
    RedirectResponse,
    SubscriptionResponse,
)
from backend.app.services.billing_service import (
    BillingConfigurationError,
    BillingOperationError,
    BillingService,
)
from backend.app.services.invoice_fiscal_service import (
    InvoiceExportFormatError,
    InvoiceFiscalService,
    InvoiceNotFoundError,
)
from backend.app.services.stripe_gateway import BillingProvider
from backend.app.services.stripe_invoice_sync import sync_customer_invoices
from backend.app.models import BillingAccount
from payments import PLANS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])
manage_billing = require_permission("billing:manage")


def subscription_response(account) -> SubscriptionResponse:
    return SubscriptionResponse(
        plan_code=account.plan_code,
        status=(
            "canceling_at_period_end"
            if account.cancel_at_period_end and account.status in {"active", "trialing"}
            else account.status
        ),
        current_period_end=account.current_period_end,
        cancel_at_period_end=account.cancel_at_period_end,
    )


def _backfill_stripe_invoices(
    db: Session,
    provider: BillingProvider,
    settings: Settings,
    company_id: UUID,
) -> None:
    try:
        sync_customer_invoices(db, provider, settings, company_id)
    except Exception:
        # L'historique local reste disponible même si Stripe est momentanément indisponible.
        logger.exception("Stripe invoice backfill failed for tenant %s", company_id)


@router.get("/plans", response_model=list[PlanResponse])
def plans() -> list[PlanResponse]:
    return [PlanResponse(
        code=plan.code.value,
        name=plan.name,
        requires_sales_contact=plan.requires_sales_contact,
        monthly_price_usd=plan.monthly_price_usd,
    ) for plan in PLANS]


@router.get("/subscription", response_model=SubscriptionResponse)
def subscription(
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> SubscriptionResponse:
    account = db.scalar(
        select(BillingAccount).where(
            BillingAccount.company_id == identity.user.company_id,
        )
    )
    if account is None:
        return SubscriptionResponse(
            plan_code=identity.user.company.subscription_plan,
            status="inactive",
            current_period_end=None,
            cancel_at_period_end=False,
        )
    return subscription_response(account)


@router.post(
    "/checkout",
    response_model=RedirectResponse,
    dependencies=[Depends(rate_limit("billing_checkout", "rate_limit_billing_per_minute"))],
)
def checkout(
    request: CheckoutRequest,
    identity: CurrentIdentity = Depends(manage_billing),
    service: BillingService = Depends(get_billing_service),
) -> RedirectResponse:
    try:
        return RedirectResponse(url=service.create_checkout(identity.user.company, request.plan_code))
    except BillingConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except (BillingOperationError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/change-plan", response_model=SubscriptionResponse)
def change_plan(
    request: ChangePlanRequest,
    identity: CurrentIdentity = Depends(manage_billing),
    service: BillingService = Depends(get_billing_service),
) -> SubscriptionResponse:
    try:
        return subscription_response(service.change_plan(identity.user.company_id, request.plan_code))
    except BillingConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except (BillingOperationError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/cancel", response_model=SubscriptionResponse)
def cancel(
    identity: CurrentIdentity = Depends(manage_billing),
    service: BillingService = Depends(get_billing_service),
) -> SubscriptionResponse:
    try:
        return subscription_response(service.cancel(identity.user.company_id))
    except BillingOperationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/portal", response_model=RedirectResponse)
def portal(
    identity: CurrentIdentity = Depends(manage_billing),
    service: BillingService = Depends(get_billing_service),
) -> RedirectResponse:
    try:
        return RedirectResponse(url=service.create_portal(identity.user.company))
    except BillingOperationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/invoices", response_model=list[InvoiceResponse])
def invoices(
    identity: CurrentIdentity = Depends(manage_billing),
    service: BillingService = Depends(get_billing_service),
    db: Session = Depends(get_db),
    provider: BillingProvider = Depends(get_billing_provider),
    settings: Settings = Depends(get_settings),
    skip: int = 0,
    limit: int = 50,
) -> list[InvoiceResponse]:
    limit = min(max(limit, 1), 200)
    skip = max(skip, 0)
    _backfill_stripe_invoices(db, provider, settings, identity.user.company_id)
    items = [InvoiceResponse.model_validate(invoice) for invoice in service.list_invoices(identity.user.company_id)]
    return items[skip : skip + limit]


@router.get("/invoices/history", response_model=InvoiceHistoryResponse)
def invoice_history(
    identity: CurrentIdentity = Depends(manage_billing),
    service: InvoiceFiscalService = Depends(get_invoice_fiscal_service),
    db: Session = Depends(get_db),
    provider: BillingProvider = Depends(get_billing_provider),
    settings: Settings = Depends(get_settings),
    offset: int = 0,
    limit: int = 20,
    start: datetime | None = None,
    end: datetime | None = None,
    fiscal_year: int | None = Query(default=None, ge=2000, le=2200),
) -> InvoiceHistoryResponse:
    # Le frontend Avenqo charge cet endpoint, donc le backfill doit être fait ici aussi.
    _backfill_stripe_invoices(db, provider, settings, identity.user.company_id)
    items, total = service.get_company_invoices(
        identity.user.company_id,
        start=start,
        end=end,
        fiscal_year=fiscal_year,
        offset=offset,
        limit=limit,
    )
    bounded_limit = min(max(limit, 1), 200)
    return InvoiceHistoryResponse(
        items=[InvoiceResponse.model_validate(invoice) for invoice in items],
        total=total,
        offset=max(offset, 0),
        limit=bounded_limit,
    )


@router.get("/invoices/export/{export_format}")
def invoice_history_export(
    export_format: str,
    identity: CurrentIdentity = Depends(manage_billing),
    service: InvoiceFiscalService = Depends(get_invoice_fiscal_service),
    start: datetime | None = None,
    end: datetime | None = None,
    fiscal_year: int | None = Query(default=None, ge=2000, le=2200),
) -> Response:
    try:
        content, media_type, file_name = service.get_invoice_export(
            identity.user.company_id,
            export_format.lower(),
            start=start,
            end=end,
            fiscal_year=fiscal_year,
        )
    except InvoiceExportFormatError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get("/invoices/fiscal/{fiscal_year}", response_model=InvoiceFiscalSummaryResponse)
def invoice_fiscal_summary(
    fiscal_year: int,
    identity: CurrentIdentity = Depends(manage_billing),
    service: InvoiceFiscalService = Depends(get_invoice_fiscal_service),
) -> InvoiceFiscalSummaryResponse:
    if fiscal_year < 2000 or fiscal_year > 2200:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid fiscal year")
    return InvoiceFiscalSummaryResponse.model_validate(
        service.get_paid_subscription_totals(identity.user.company_id, fiscal_year)
    )


@router.get("/invoices/fiscal/{fiscal_year}/pdf")
def invoice_fiscal_pdf(
    fiscal_year: int,
    identity: CurrentIdentity = Depends(manage_billing),
    service: InvoiceFiscalService = Depends(get_invoice_fiscal_service),
) -> Response:
    if fiscal_year < 2000 or fiscal_year > 2200:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid fiscal year")
    content, media_type, file_name = service.get_fiscal_summary_pdf(
        identity.user.company_id,
        fiscal_year,
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
def invoice_detail(
    invoice_id: UUID,
    identity: CurrentIdentity = Depends(manage_billing),
    service: InvoiceFiscalService = Depends(get_invoice_fiscal_service),
) -> InvoiceResponse:
    try:
        return InvoiceResponse.model_validate(
            service.get_invoice(identity.user.company_id, invoice_id)
        )
    except InvoiceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/invoices/{invoice_id}/pdf")
def official_invoice_pdf(
    invoice_id: UUID,
    identity: CurrentIdentity = Depends(manage_billing),
    service: InvoiceFiscalService = Depends(get_invoice_fiscal_service),
) -> HTTPRedirectResponse:
    try:
        invoice = service.get_invoice(identity.user.company_id, invoice_id)
    except InvoiceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if not invoice.invoice_pdf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Official Stripe PDF unavailable")
    return HTTPRedirectResponse(invoice.invoice_pdf, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/invoices/{invoice_id}/export/{export_format}")
def single_invoice_export(
    invoice_id: UUID,
    export_format: str,
    identity: CurrentIdentity = Depends(manage_billing),
    service: InvoiceFiscalService = Depends(get_invoice_fiscal_service),
) -> Response:
    try:
        content, media_type, file_name = service.get_invoice_export(
            identity.user.company_id,
            export_format.lower(),
            invoice_id=invoice_id,
        )
    except InvoiceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvoiceExportFormatError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get("/ai-credits", response_model=AICreditBalanceResponse)
def ai_credit_balance(
    identity: CurrentIdentity = Depends(get_current_identity),
    service: BillingService = Depends(get_billing_service),
) -> AICreditBalanceResponse:
    return AICreditBalanceResponse.model_validate(
        service.get_credit_balance(
            identity.user.company_id,
            identity.user.company.subscription_plan,
        )
    )


@router.get("/credit-packs", response_model=list[CreditPackResponse])
def credit_packs(
    identity: CurrentIdentity = Depends(get_current_identity),
    service: BillingService = Depends(get_billing_service),
) -> list[CreditPackResponse]:
    return [
        CreditPackResponse.model_validate(pack)
        for pack in service.list_credit_packs(
            identity.user.company_id,
            identity.user.company.subscription_plan,
        )
    ]


@router.post("/credit-packs/checkout", response_model=RedirectResponse)
def credit_pack_checkout(
    request: CreditPackCheckoutRequest,
    identity: CurrentIdentity = Depends(manage_billing),
    service: BillingService = Depends(get_billing_service),
) -> RedirectResponse:
    try:
        return RedirectResponse(
            url=service.create_credit_checkout(identity.user.company, request.pack_code)
        )
    except BillingConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except BillingOperationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/webhook", include_in_schema=False)
async def webhook(
    request: Request,
    stripe_signature: str = Header(alias="Stripe-Signature"),
    service: BillingService = Depends(get_billing_service),
) -> dict[str, bool]:
    try:
        processed = service.process_webhook(await request.body(), stripe_signature)
    except Exception:
        logger.exception("Stripe webhook processing failed")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook Stripe invalide")
    return {"processed": processed}
