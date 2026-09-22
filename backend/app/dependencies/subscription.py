"""Contrôle centralisé de l'accès tenant selon l'abonnement synchronisé."""

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.auth import get_tenant_context
from backend.app.models import BillingAccount
from shared.ai_engine.contracts import TenantContext
from backend.app.config.settings import get_settings
from backend.app.services.stripe_gateway import StripeGateway
from backend.app.services.subscription_reconciliation import reconcile_subscription

ALLOWED_SUBSCRIPTION_STATUSES = frozenset({"active", "trialing"})
SUBSCRIPTION_REQUIRED_DETAIL = "Un abonnement actif est requis"


def require_active_subscription(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> TenantContext:
    """Autorise le tenant authentifié lorsque son abonnement le permet."""

    account = db.scalar(
        select(BillingAccount).where(
            BillingAccount.company_id == tenant.company_id,
        )
    )
    subscription_status = account.status.strip().lower() if account else "inactive"
    if subscription_status not in ALLOWED_SUBSCRIPTION_STATUSES and account is not None:
        settings = get_settings()
        if settings.stripe_secret_key and account.stripe_subscription_id and account.stripe_customer_id:
            try:
                if reconcile_subscription(account, StripeGateway(settings.stripe_secret_key), settings):
                    db.commit()
                    subscription_status = account.status
            except Exception:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="La verification de l'abonnement Stripe est temporairement indisponible. Reessayez.",
                )
    if subscription_status not in ALLOWED_SUBSCRIPTION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=SUBSCRIPTION_REQUIRED_DETAIL,
        )
    return tenant
