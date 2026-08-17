"""Routes de facturation Stripe du tenant courant."""

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from backend.app.dependencies.auth import CurrentIdentity, require_permission
from backend.app.dependencies.billing import get_billing_service
from backend.app.schemas.billing import (
    ChangePlanRequest,
    CheckoutRequest,
    InvoiceResponse,
    PlanResponse,
    RedirectResponse,
    SubscriptionResponse,
)
from backend.app.services.billing_service import (
    BillingConfigurationError,
    BillingOperationError,
    BillingService,
)
from payments import PLANS

router = APIRouter(prefix="/billing", tags=["billing"])
manage_billing = require_permission("billing:manage")


def subscription_response(account) -> SubscriptionResponse:
    return SubscriptionResponse(
        plan_code=account.plan_code,
        status=account.status,
        current_period_end=account.current_period_end,
        cancel_at_period_end=account.cancel_at_period_end,
    )


@router.get("/plans", response_model=list[PlanResponse])
def plans() -> list[PlanResponse]:
    return [PlanResponse(
        code=plan.code.value,
        name=plan.name,
        requires_sales_contact=plan.requires_sales_contact,
    ) for plan in PLANS]


@router.get("/subscription", response_model=SubscriptionResponse)
def subscription(
    identity: CurrentIdentity = Depends(manage_billing),
    service: BillingService = Depends(get_billing_service),
) -> SubscriptionResponse:
    return subscription_response(service.get_account(identity.user.company_id))


@router.post("/checkout", response_model=RedirectResponse)
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
        return RedirectResponse(url=service.create_portal(identity.user.company_id))
    except BillingOperationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/invoices", response_model=list[InvoiceResponse])
def invoices(
    identity: CurrentIdentity = Depends(manage_billing),
    service: BillingService = Depends(get_billing_service),
) -> list[InvoiceResponse]:
    return [InvoiceResponse.model_validate(invoice) for invoice in service.list_invoices(identity.user.company_id)]


@router.post("/webhook", include_in_schema=False)
async def webhook(
    request: Request,
    stripe_signature: str = Header(alias="Stripe-Signature"),
    service: BillingService = Depends(get_billing_service),
) -> dict[str, bool]:
    try:
        processed = service.process_webhook(await request.body(), stripe_signature)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook Stripe invalide") from exc
    return {"processed": processed}