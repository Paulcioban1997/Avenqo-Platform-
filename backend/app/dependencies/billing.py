"""Dépendances FastAPI de la facturation Stripe."""

from typing import cast
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.app.config.settings import get_settings
from backend.app.ai.usage.policy import AIQuotaPolicy
from backend.app.ai.usage.service import AIUsageService
from backend.app.database import get_db
from backend.app.dependencies.auth import get_account_notifier
from backend.app.services.account_notifications import AccountNotifier
from backend.app.services.billing_service import BillingService
from backend.app.services.invoice_fiscal_service import InvoiceFiscalService
from backend.app.services.stripe_gateway import BillingProvider, StripeGateway


def get_billing_provider() -> BillingProvider:
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe n'est pas configuré",
        )
    return StripeGateway(settings.stripe_secret_key, automatic_tax_enabled=settings.stripe_automatic_tax_enabled)


def get_billing_provider_optional(request: Request) -> BillingProvider | None:
    if get_billing_provider in request.app.dependency_overrides:
        override = request.app.dependency_overrides[get_billing_provider]
        result = override() if callable(override) else override
        return cast(BillingProvider | None, result)
    settings = get_settings()
    if not settings.stripe_secret_key:
        return None
    return StripeGateway(settings.stripe_secret_key, automatic_tax_enabled=settings.stripe_automatic_tax_enabled)


def get_billing_service(
    db: Session = Depends(get_db),
    provider: BillingProvider = Depends(get_billing_provider),
    notifier: AccountNotifier = Depends(get_account_notifier),
) -> BillingService:
    settings = get_settings()
    return BillingService(
        db,
        provider,
        settings,
        AIUsageService(
            db,
            AIQuotaPolicy(settings),
            settings.avenqo_provider_cost_per_credit_usd,
            settings.ai_credit_reservation_ttl_minutes,
        ),
        notifier,
    )


def get_credit_balance_service(
    db: Session = Depends(get_db),
    notifier: AccountNotifier = Depends(get_account_notifier),
) -> BillingService:
    """Read the tenant ledger without requiring or invoking Stripe."""
    settings = get_settings()
    return BillingService(
        db, None, settings,
        AIUsageService(db, AIQuotaPolicy(settings), settings.avenqo_provider_cost_per_credit_usd, settings.ai_credit_reservation_ttl_minutes),
        notifier,
    )


def get_invoice_fiscal_service(
    db: Session = Depends(get_db),
) -> InvoiceFiscalService:
    return InvoiceFiscalService(db)
