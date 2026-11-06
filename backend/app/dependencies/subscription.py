"""Subscription access and separate prospective contract-onboarding gate."""

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.auth import get_tenant_context
from backend.app.models import BillingAccount
from shared.ai_engine.contracts import TenantContext
from ..services.contract_signature_service import ContractAuthorityError, ContractSignatureService

ALLOWED_SUBSCRIPTION_STATUSES = frozenset({"active", "trialing"})
SUBSCRIPTION_REQUIRED_DETAIL = "Un abonnement actif est requis"
CONTRACT_SIGNATURE_REQUIRED_CODE = "contract_signature_required"


def require_active_subscription(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> TenantContext:
    """Preserve established paid entitlements independently of new contract onboarding."""

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


def require_signed_mandatory_contracts(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> TenantContext:
    """Exige explicitement que tous les contrats obligatoires soient signés."""
    service = ContractSignatureService(db)
    try:
        service.require_legal_release()
    except ContractAuthorityError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
            "code": "contract_governance_unavailable", "message": str(exc),
        }) from exc
    if not service.has_signed_mandatory_contracts(tenant.company_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": CONTRACT_SIGNATURE_REQUIRED_CODE,
                "message": "La signature des documents juridiques obligatoires (NDA mutuel et contrat d'abonnement SaaS) est requise.",
            },
        )
    return tenant
