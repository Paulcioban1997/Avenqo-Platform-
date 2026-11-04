"""Contrôle centralisé de l'accès tenant selon l'abonnement synchronisé et la signature des contrats obligatoires."""

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.auth import get_tenant_context
from backend.app.models import BillingAccount, CompanyContract
from shared.ai_engine.contracts import TenantContext

ALLOWED_SUBSCRIPTION_STATUSES = frozenset({"active", "trialing"})
SUBSCRIPTION_REQUIRED_DETAIL = "Un abonnement actif est requis"
CONTRACT_SIGNATURE_REQUIRED_CODE = "contract_signature_required"


def require_active_subscription(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> TenantContext:
    """Autorise le tenant authentifié lorsque son abonnement le permet.
    
    Si des contrats obligatoires (NDA mutuel, contrat d'abonnement) sont enregistrés
    pour l'entreprise, leur signature effective est obligatoire pour activer les modules payants.
    """

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

    # Vérification conditionnelle de la signature des contrats obligatoires
    has_registered_contracts = db.scalar(
        select(CompanyContract.id).where(CompanyContract.company_id == tenant.company_id).limit(1)
    )
    if has_registered_contracts:
        from backend.app.services.contract_signature_service import ContractSignatureService
        service = ContractSignatureService(db)
        if not service.has_signed_mandatory_contracts(tenant.company_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": CONTRACT_SIGNATURE_REQUIRED_CODE,
                    "message": "La signature des documents juridiques obligatoires (NDA mutuel et contrat d'abonnement SaaS) est requise avant d'activer vos modules payants.",
                },
            )

    return tenant


def require_signed_mandatory_contracts(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> TenantContext:
    """Exige explicitement que tous les contrats obligatoires soient signés."""
    from backend.app.services.contract_signature_service import ContractSignatureService
    service = ContractSignatureService(db)
    if not service.has_signed_mandatory_contracts(tenant.company_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": CONTRACT_SIGNATURE_REQUIRED_CODE,
                "message": "La signature des documents juridiques obligatoires (NDA mutuel et contrat d'abonnement SaaS) est requise.",
            },
        )
    return tenant
