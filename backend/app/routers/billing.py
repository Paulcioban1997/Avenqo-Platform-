"""Routes de facturation Stripe du tenant courant."""

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse as HTTPRedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings, get_settings
from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, require_permission
from backend.app.dependencies.billing import get_billing_provider, get_billing_service, get_invoice_fiscal_service
from backend.app.core.rate_limit import rate_limit
from backend.app.schemas.billing import (
    AICreditBalanceResponse,
    AICreditBreakdownItem,
    AICreditBreakdownResponse,
    AICreditHistoryItem,
    AICreditHistoryResponse,
    ChangePlanRequest,
    CheckoutRequest,
    CreditPackCheckoutRequest,
    CreditPackResponse,
    EnterpriseQuoteRequest,
    EnterpriseQuoteResponse,
    InvoiceResponse,
    InvoiceFiscalSummaryResponse,
    InvoiceHistoryResponse,
    PaymentMethodSummary,
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
from backend.app.models import BillingAccount, Company, TenantAIProviderAttempt
from payments import PLANS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])
manage_billing = require_permission("billing:manage")


def subscription_response(account, company: Company | None = None) -> SubscriptionResponse:
    plan_obj = next((p for p in PLANS if p.code.value == account.plan_code), None)
    plan_name = plan_obj.name if plan_obj else account.plan_code.capitalize()
    price = plan_obj.monthly_price_usd if plan_obj else 49
    comp_name = company.name if company else None
    pm = PaymentMethodSummary() if account.status in {"active", "trialing"} else None
    return SubscriptionResponse(
        plan_code=account.plan_code,
        status=(
            "canceling_at_period_end"
            if account.cancel_at_period_end and account.status in {"active", "trialing"}
            else account.status
        ),
        current_period_end=account.current_period_end,
        cancel_at_period_end=account.cancel_at_period_end,
        plan_name=plan_name,
        monthly_price_usd=price,
        billing_frequency="monthly",
        currency="USD",
        company_name=comp_name,
        payment_method=pm,
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
        plan_obj = next((p for p in PLANS if p.code.value == identity.user.company.subscription_plan), None)
        return SubscriptionResponse(
            plan_code=identity.user.company.subscription_plan,
            status="inactive",
            current_period_end=None,
            cancel_at_period_end=False,
            plan_name=plan_obj.name if plan_obj else identity.user.company.subscription_plan.capitalize(),
            monthly_price_usd=plan_obj.monthly_price_usd if plan_obj else 0,
            billing_frequency="monthly",
            currency="USD",
            company_name=identity.user.company.name,
            payment_method=None,
        )
    return subscription_response(account, company=identity.user.company)


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
    if total == 0 and offset == 0:
        items = service.ensure_company_invoices(identity.user.company_id)
        total = len(items)

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
) -> Response:
    try:
        invoice = service.get_invoice(identity.user.company_id, invoice_id)
    except InvoiceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if invoice.invoice_pdf and invoice.invoice_pdf.startswith("http"):
        return HTTPRedirectResponse(invoice.invoice_pdf, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    # Génération officielle PDF déterministe via ReportLab si Stripe PDF indisponible
    content, media_type, file_name = service.generate_invoice_pdf(invoice)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


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


@router.get("/ai-credits/breakdown", response_model=AICreditBreakdownResponse)
def ai_credits_breakdown(
    period: str = Query(default="billing_period"),
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> AICreditBreakdownResponse:
    attempts = db.scalars(
        select(TenantAIProviderAttempt)
        .where(TenantAIProviderAttempt.company_id == identity.user.company_id)
    ).all()

    module_counts: dict[str, int] = {
        "Retail AI": 0,
        "CRM AI": 0,
        "Copilot": 0,
        "OCR AI": 0,
        "Marketing AI": 0,
        "Autre": 0,
    }

    total = 0
    for att in attempts:
        op = (att.operation or "").lower()
        creds = att.avenqo_credits or 0
        if "retail" in op or "sales" in op:
            module_counts["Retail AI"] += creds
        elif "crm" in op or "appointment" in op:
            module_counts["CRM AI"] += creds
        elif "copilot" in op or "chat" in op:
            module_counts["Copilot"] += creds
        elif "ocr" in op or "document" in op:
            module_counts["OCR AI"] += creds
        elif "marketing" in op:
            module_counts["Marketing AI"] += creds
        else:
            module_counts["Autre"] += creds
        total += creds

    items = []
    for mod, count in module_counts.items():
        pct = round((count / total * 100), 1) if total > 0 else 0.0
        items.append(AICreditBreakdownItem(module=mod, credits_used=count, percentage=pct))

    return AICreditBreakdownResponse(
        period=period,
        total_used=total,
        items=items,
    )


@router.get("/ai-credits/history", response_model=AICreditHistoryResponse)
def ai_credits_history(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> AICreditHistoryResponse:
    query = (
        select(TenantAIProviderAttempt)
        .where(TenantAIProviderAttempt.company_id == identity.user.company_id)
        .order_by(TenantAIProviderAttempt.id.desc())
    )
    total = (
        db.scalar(
            select(func.count())
            .select_from(TenantAIProviderAttempt)
            .where(TenantAIProviderAttempt.company_id == identity.user.company_id)
        )
        or 0
    )

    attempts = db.scalars(query.offset(offset).limit(limit)).all()
    items = []
    for att in attempts:
        op = (att.operation or "Requête IA").replace("_", " ").title()
        mod = "CRM AI" if "crm" in op.lower() else ("Retail AI" if "retail" in op.lower() else "Copilot")
        items.append(
            AICreditHistoryItem(
                id=str(att.id),
                date="Aujourd'hui",
                module=mod,
                operation=op,
                credits_used=att.avenqo_credits or 10,
                user=f"{identity.user.first_name} {identity.user.last_name}",
            )
        )
    return AICreditHistoryResponse(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
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


@router.post("/enterprise-quote", response_model=EnterpriseQuoteResponse)
def request_enterprise_quote(
    request: EnterpriseQuoteRequest,
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> EnterpriseQuoteResponse:
    from backend.app.models.audit_log import AuditLogEntry
    from backend.app.models.billing import EnterpriseQuote

    reference_id = f"EQ-{uuid4().hex[:8].upper()}"
    now = datetime.now(timezone.utc)

    quote = EnterpriseQuote(
        reference_id=reference_id,
        company_id=identity.user.company_id,
        user_id=identity.user.id,
        contact_name=request.contact_name or f"{identity.user.first_name} {identity.user.last_name}",
        contact_email=request.contact_email or identity.user.email,
        contact_phone=request.contact_phone,
        requested_modules=request.requested_modules or [],
        estimated_users=request.estimated_users,
        monthly_volume=request.monthly_volume,
        required_integrations=request.required_integrations or [],
        notes=request.notes,
        status="received",
    )
    db.add(quote)

    safe_lead_metadata = {
        "reference_id": reference_id,
        "company_name": identity.user.company.name,
        "company_id": str(identity.user.company_id),
        "requester_name": quote.contact_name,
        "requester_email": quote.contact_email,
        "contact_phone": request.contact_phone,
        "requested_modules": request.requested_modules,
        "estimated_users": request.estimated_users,
        "monthly_volume": request.monthly_volume,
        "required_integrations": request.required_integrations,
        "notes": request.notes,
        "submitted_at": now.isoformat(),
    }

    entry = AuditLogEntry(
        actor_user_id=identity.user.id,
        action="billing.enterprise_quote_requested",
        target_type="company",
        target_id=str(identity.user.company_id),
        company_id=identity.user.company_id,
        safe_metadata=safe_lead_metadata,
        created_at=now,
    )
    db.add(entry)
    db.commit()

    logger.info(
        "Enterprise quote request %s recorded for tenant %s",
        reference_id,
        identity.user.company_id,
    )

    return EnterpriseQuoteResponse(
        reference_id=reference_id,
        status="received",
        message="Votre demande de devis Enterprise a été enregistrée avec succès. Notre équipe vous contactera sous 24h ouvrées.",
        created_at=now,
    )


@router.get("/enterprise-quote", response_model=list[EnterpriseQuoteResponse])
def list_enterprise_quotes(
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> list[EnterpriseQuoteResponse]:
    from backend.app.models.billing import EnterpriseQuote

    quotes = db.scalars(
        select(EnterpriseQuote)
        .where(EnterpriseQuote.company_id == identity.user.company_id)
        .order_by(EnterpriseQuote.created_at.desc())
    ).all()
    return [
        EnterpriseQuoteResponse(
            reference_id=q.reference_id,
            status=q.status,
            message=f"Demande {q.reference_id} ({q.status}).",
            created_at=q.created_at,
        )
        for q in quotes
    ]



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
