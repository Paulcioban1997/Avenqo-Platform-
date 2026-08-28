"""Contrôle centralisé de l'accès tenant selon l'abonnement synchronisé."""

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.auth import get_tenant_context
from backend.app.models import BillingAccount
from shared.ai_engine.contracts import TenantContext

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
    if subscription_status not in ALLOWED_SUBSCRIPTION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=SUBSCRIPTION_REQUIRED_DETAIL,
        )
    return tenant