"""Routes API pour l'espace 'Mes contrats', le parcours d'onboarding juridique 4 étapes et la signature."""

from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.auth import (
    CurrentIdentity,
    get_account_notifier,
    get_current_identity,
    get_tenant_context,
    require_platform_admin,
)
from backend.app.models.company import Company
from backend.app.models.company_contract import (
    ContractExecutionPartyState,
    ContractLifecycleStatus,
)
from backend.app.models.company_legal_profile import CompanyLegalProfile
from backend.app.services.account_notifications import AccountNotifier
from backend.app.services.audit_log_service import AuditLogService
from backend.app.services.commercial_reconciler import CommercialReconciler
from backend.app.services.company_legal_profile_service import (
    CompanyLegalProfileService,
    LegalProfileValidationError,
)
from backend.app.services.signing_challenge_service import SigningChallengeService
from ..services.contract_signature_service import (
    CommercialConfigMismatchError,
    ContractAlreadySignedError,
    ContractAuthorityError,
    ContractNotFoundError,
    ContractSignatureService,
)
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/contracts", tags=["contracts"])
logger = logging.getLogger(__name__)


class LegalProfilePayload(BaseModel):
    legal_name: str = Field(..., min_length=2, max_length=255)
    trade_name: str | None = None
    country: str = Field(..., min_length=2, max_length=100)
    province_state: str = Field(..., min_length=2, max_length=100)
    registration_number: str | None = None
    business_number: str | None = None
    tax_id_gst: str | None = None
    tax_id_qst: str | None = None
    tax_id_other: str | None = None
    registered_address_street: str = Field(..., min_length=2, max_length=255)
    registered_address_city: str = Field(..., min_length=2, max_length=100)
    registered_address_state_province: str = Field(..., min_length=2, max_length=100)
    registered_address_postal_code: str = Field(..., min_length=2, max_length=32)
    registered_address_country: str = Field(..., min_length=2, max_length=100)
    mailing_address_same: bool = True
    mailing_address_street: str | None = None
    mailing_address_city: str | None = None
    mailing_address_state_province: str | None = None
    mailing_address_postal_code: str | None = None
    mailing_address_country: str | None = None
    website: str | None = None
    phone: str = Field(..., min_length=7, max_length=32)
    general_email: str = Field(..., min_length=5, max_length=255)
    billing_email: str = Field(..., min_length=5, max_length=255)
    industry: str = Field("Technologies", max_length=120)
    legal_entity_type: str = Field("Corporation", max_length=100)
    preferred_language: str = Field("fr", max_length=10)
    authorized_representative_first_name: str = Field(..., min_length=1, max_length=100)
    authorized_representative_last_name: str = Field(..., min_length=1, max_length=100)
    authorized_representative_email: str = Field(..., min_length=5, max_length=255)
    authorized_representative_title: str = Field(..., min_length=2, max_length=120)
    authorized_representative_capacity: str = Field("Owner", max_length=100)
    authorized_representative_authority_confirmed: bool = Field(...)


class ContractSignRequest(BaseModel):
    signatory_title: str = Field(..., min_length=2, max_length=120, description="Titre ou fonction légale du signataire (ex: Président, CEO)")
    declared_authority: bool = Field(..., description="Déclaration expresse d'autorité pour engager l'entreprise")
    consent_checkbox: bool = Field(..., description="Consentement exprès et explicite aux termes du contrat")
    challenge_id: str | None = None
    challenge_code: str | None = None


class CountersignRequest(BaseModel):
    provider_name: str = Field("Mircea Paul Cioban", max_length=255)
    provider_title: str = Field("Président Fondateur", max_length=255)


class ContractItemResponse(BaseModel):
    id: str
    company_id: str
    contract_type: str
    title: str
    status: str
    execution_state: str
    version: str
    language: str
    signature_mode: str | None
    signatory_name: str | None
    signatory_title: str | None
    signatory_email: str | None
    signed_at: str | None
    provider_signed_at: str | None
    sha256_hash: str
    has_pdf: bool


def _get_service(
    db: Session = Depends(get_db),
    notifier: AccountNotifier = Depends(get_account_notifier),
) -> ContractSignatureService:
    return ContractSignatureService(db, audit_service=AuditLogService(db), notifier=notifier)


# --------------------------------------------------------------------------
# PARCOURS 4 ÉTAPES (WIZARD D'ONBOARDING JURIDIQUE ET COMMERCIAL)
# --------------------------------------------------------------------------

@router.get("/wizard/status")
def get_wizard_status(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    service: ContractSignatureService = Depends(_get_service),
) -> dict[str, Any]:
    """Retourne l'avancement du parcours d'onboarding contractuel en 4 étapes."""
    company = db.get(Company, tenant.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Entreprise introuvable")

    legal_svc = CompanyLegalProfileService(db)
    profile = legal_svc.get_profile(company.id)
    step1_complete = profile is not None and profile.authorized_representative_authority_confirmed

    schedule = CommercialReconciler.reconcile(company, service._settings)
    step2_complete = not schedule.is_blocked

    contracts = service.ensure_contracts_for_company(company)
    mandatory_signed = service.has_signed_mandatory_contracts(company.id)
    all_signed = all(
        c.status in (ContractLifecycleStatus.SIGNED.value, ContractLifecycleStatus.CUSTOMER_SIGNED.value, ContractLifecycleStatus.FULLY_EXECUTED.value)
        for c in contracts
    )

    current_step = 1
    if step1_complete:
        current_step = 2
    if step1_complete and step2_complete:
        current_step = 3
    if step1_complete and step2_complete and mandatory_signed:
        current_step = 4

    return {
        "current_step": current_step,
        "step_1_legal_profile": {
            "is_complete": step1_complete,
            "profile": {
                "legal_name": profile.legal_name if profile else company.name,
                "country": profile.country if profile else company.country,
                "province_state": profile.province_state if profile else "",
                "registration_number": profile.registration_number if profile else None,
                "authorized_representative": (
                    f"{profile.authorized_representative_first_name} {profile.authorized_representative_last_name}"
                    if profile else ""
                ),
                "authorized_representative_capacity": profile.authorized_representative_capacity if profile else "Owner",
            } if profile else None,
        },
        "step_2_commercial_order": {
            "is_complete": step2_complete,
            "reconciliation_status": schedule.reconciliation_status,
            "is_blocked": schedule.is_blocked,
            "mismatches": schedule.mismatches,
            "schedule": schedule.to_dict(),
        },
        "step_3_review_agreements": {
            "contracts_count": len(contracts),
            "contracts": [
                {
                    "contract_type": c.contract_type,
                    "title": c.title,
                    "version": c.version,
                    "status": c.status,
                    "execution_state": c.execution_state,
                    "draft_pdf_available": True,
                }
                for c in contracts
            ],
        },
        "step_4_verify_and_sign": {
            "mandatory_signed": mandatory_signed,
            "all_signed": all_signed,
            "provider_incorporation_status": service._settings.provider_incorporation_status,
            "is_sandbox_ready": True,
        },
    }


@router.get("/legal-profile")
def get_company_legal_profile(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, Any] | None:
    """Récupère le profil juridique de l'entreprise cliente."""
    legal_svc = CompanyLegalProfileService(db)
    profile = legal_svc.get_profile(tenant.company_id)
    if not profile:
        company = db.get(Company, tenant.company_id)
        return {
            "legal_name": company.name if company else "",
            "country": company.country if company else "Canada",
            "province_state": "Québec" if (company and company.country == "Canada") else "",
            "phone": company.phone or "",
            "general_email": company.email if company else "",
            "billing_email": company.billing_email if company else "",
            "preferred_language": company.preferred_language if company else "fr",
            "is_persisted": False,
        }
    return {
        "id": str(profile.id),
        "legal_name": profile.legal_name,
        "trade_name": profile.trade_name,
        "country": profile.country,
        "province_state": profile.province_state,
        "registration_number": profile.registration_number,
        "business_number": profile.business_number,
        "tax_id_gst": profile.tax_id_gst,
        "tax_id_qst": profile.tax_id_qst,
        "tax_id_other": profile.tax_id_other,
        "registered_address_street": profile.registered_address_street,
        "registered_address_city": profile.registered_address_city,
        "registered_address_state_province": profile.registered_address_state_province,
        "registered_address_postal_code": profile.registered_address_postal_code,
        "registered_address_country": profile.registered_address_country,
        "mailing_address_same": profile.mailing_address_same,
        "mailing_address_street": profile.mailing_address_street,
        "mailing_address_city": profile.mailing_address_city,
        "mailing_address_state_province": profile.mailing_address_state_province,
        "mailing_address_postal_code": profile.mailing_address_postal_code,
        "mailing_address_country": profile.mailing_address_country,
        "website": profile.website,
        "phone": profile.phone,
        "general_email": profile.general_email,
        "billing_email": profile.billing_email,
        "industry": profile.industry,
        "legal_entity_type": profile.legal_entity_type,
        "preferred_language": profile.preferred_language,
        "authorized_representative_first_name": profile.authorized_representative_first_name,
        "authorized_representative_last_name": profile.authorized_representative_last_name,
        "authorized_representative_email": profile.authorized_representative_email,
        "authorized_representative_title": profile.authorized_representative_title,
        "authorized_representative_capacity": profile.authorized_representative_capacity,
        "authorized_representative_authority_confirmed": profile.authorized_representative_authority_confirmed,
        "is_persisted": True,
    }


@router.post("/legal-profile")
def save_company_legal_profile(
    payload: LegalProfilePayload,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Enregistre ou met à jour le profil juridique vérifié de l'entreprise cliente."""
    role_str = str(getattr(identity.user, "role", "") or "").lower()
    if role_str not in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs ou propriétaires peuvent modifier le profil juridique de l'entreprise.",
        )

    legal_svc = CompanyLegalProfileService(db)
    try:
        profile = legal_svc.upsert_profile(tenant.company_id, payload.model_dump())
        return {
            "success": True,
            "message": "Profil juridique corporatif validé et enregistré avec succès.",
            "profile_id": str(profile.id),
        }
    except LegalProfileValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.errors)


@router.get("/commercial-order")
def get_commercial_order(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    service: ContractSignatureService = Depends(_get_service),
) -> dict[str, Any]:
    """Réconcilie et retourne le bordereau de commande commerciale dynamique."""
    company = db.get(Company, tenant.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Entreprise introuvable")

    schedule = CommercialReconciler.reconcile(company, service._settings)
    return schedule.to_dict()


@router.post("/signing-challenge")
def create_signing_challenge(
    contract_type: str,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
) -> dict[str, Any]:
    """Émet un défi de signature à usage unique avec code de sécurité éphémère (anti-rejeu)."""
    challenge = SigningChallengeService.create_challenge(
        company_id=tenant.company_id,
        user_id=identity.user.id,
        contract_type=contract_type,
    )
    return {
        "challenge_id": challenge.challenge_id,
        "contract_type": challenge.contract_type,
        "expires_at": challenge.expires_at.isoformat(),
        "verification_code": challenge.code,
    }


# --------------------------------------------------------------------------
# CONSULTATION ET GESTION DES CONTRATS
# --------------------------------------------------------------------------

@router.get("", response_model=list[ContractItemResponse])
def list_company_contracts(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    service: ContractSignatureService = Depends(_get_service),
) -> list[ContractItemResponse]:
    """Liste tous les contrats d'un tenant. Provisionne automatiquement les contrats s'ils n'existent pas encore."""
    company = db.get(Company, tenant.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Entreprise introuvable")

    contracts = service.ensure_contracts_for_company(company)
    return [
        ContractItemResponse(
            id=str(c.id),
            company_id=str(c.company_id),
            contract_type=c.contract_type,
            title=c.title,
            status=c.status,
            execution_state=c.execution_state,
            version=c.version,
            language=c.language,
            signature_mode=c.signature_mode,
            signatory_name=c.signatory_name,
            signatory_title=c.signatory_title,
            signatory_email=c.signatory_email,
            signed_at=c.signed_at.isoformat() if c.signed_at else None,
            provider_signed_at=c.provider_signed_at.isoformat() if c.provider_signed_at else None,
            sha256_hash=c.sha256_hash,
            has_pdf=bool(c.storage_path),
        )
        for c in contracts
    ]


@router.get("/status/mandatory")
def check_mandatory_status(
    tenant: TenantContext = Depends(get_tenant_context),
    service: ContractSignatureService = Depends(_get_service),
) -> dict[str, bool]:
    """Vérifie si tous les contrats obligatoires sont signés pour le locataire."""
    signed = service.has_signed_mandatory_contracts(tenant.company_id)
    return {"mandatory_signed": signed}


@router.get("/{contract_type}")
def get_contract_detail(
    contract_type: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    service: ContractSignatureService = Depends(_get_service),
) -> dict:
    """Récupère le texte complet interpolé et les métadonnées d'un contrat pour consultation avant signature."""
    company = db.get(Company, tenant.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Entreprise introuvable")

    service.ensure_contracts_for_company(company)
    try:
        contract = service.get_contract(tenant.company_id, contract_type)
    except ContractNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "id": str(contract.id),
        "company_id": str(contract.company_id),
        "contract_type": contract.contract_type,
        "title": contract.title,
        "status": contract.status,
        "execution_state": contract.execution_state,
        "version": contract.version,
        "language": contract.language,
        "signature_mode": contract.signature_mode,
        "signatory_name": contract.signatory_name,
        "signatory_title": contract.signatory_title,
        "signatory_email": contract.signatory_email,
        "signed_at": contract.signed_at.isoformat() if contract.signed_at else None,
        "provider_signed_at": contract.provider_signed_at.isoformat() if contract.provider_signed_at else None,
        "sha256_hash": contract.sha256_hash,
        "content_text": contract.content_text,
        "has_pdf": bool(contract.storage_path),
        "completion_record": contract.completion_record_json,
    }


@router.post("/{contract_type}/sign")
def sign_contract_electronic(
    contract_type: str,
    payload: ContractSignRequest,
    request: Request,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
    service: ContractSignatureService = Depends(_get_service),
) -> dict:
    """Exécute la signature électronique numérique avec preuve d'audit, PDF certifié et courriel."""
    company = db.get(Company, tenant.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Entreprise introuvable")

    service.ensure_contracts_for_company(company)
    user = identity.user

    ip_address = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "Avenqo-Web/1.0")

    try:
        receipt = service.sign_contract_electronic(
            company=company,
            user=user,
            contract_type=contract_type,
            signatory_title=payload.signatory_title.strip(),
            declared_authority=payload.declared_authority,
            consent_checkbox=payload.consent_checkbox,
            ip_address=ip_address,
            user_agent=user_agent,
            challenge_id=payload.challenge_id,
            challenge_code=payload.challenge_code,
        )
        return receipt
    except ContractAuthorityError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ContractNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (CommercialConfigMismatchError, ContractAlreadySignedError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{contract_type}/countersign")
def countersign_contract_provider(
    contract_type: str,
    company_id: UUID,
    payload: CountersignRequest,
    identity: CurrentIdentity = Depends(require_platform_admin),
    service: ContractSignatureService = Depends(_get_service),
) -> dict[str, Any]:
    """Réservé aux administrateurs de plateforme Avenqo pour contresigner un contrat client."""
    try:
        updated = service.countersign_contract_provider(
            company_id=company_id,
            contract_type=contract_type,
            provider_user=identity.user,
            provider_name=payload.provider_name,
            provider_title=payload.provider_title,
        )
        return {
            "success": True,
            "contract_id": str(updated.id),
            "contract_type": updated.contract_type,
            "status": updated.status,
            "execution_state": updated.execution_state,
            "provider_signed_at": updated.provider_signed_at.isoformat() if updated.provider_signed_at else None,
            "provider_signatory": f"{updated.provider_signatory_name} ({updated.provider_signatory_title})",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{contract_type}/completion-record")
def get_completion_record(
    contract_type: str,
    tenant: TenantContext = Depends(get_tenant_context),
    service: ContractSignatureService = Depends(_get_service),
) -> dict[str, Any]:
    """Retourne le registre d'achèvement électronique et la preuve cryptographique."""
    contract = service.get_contract(tenant.company_id, contract_type)
    if not contract.completion_record_json:
        raise HTTPException(status_code=404, detail="Aucun registre d'achèvement généré pour ce contrat.")
    return contract.completion_record_json


@router.post("/{contract_type}/upload-manuscript")
async def upload_manuscript_signature(
    contract_type: str,
    request: Request,
    file: UploadFile = File(...),
    signatory_title: str = Form("Dirigeant"),
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
    service: ContractSignatureService = Depends(_get_service),
) -> dict:
    """Téléverse un contrat scanné signé à la main au stylo."""
    company = db.get(Company, tenant.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Entreprise introuvable")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Fichier vide téléversé.")

    ip_address = request.client.host if request and request.client else "127.0.0.1"

    try:
        receipt = service.upload_wet_ink_signature(
            company=company,
            user=identity.user,
            contract_type=contract_type,
            signatory_title=signatory_title,
            file_bytes=content,
            filename=file.filename or "contract_signed.pdf",
            ip_address=ip_address,
        )
        return receipt
    except ContractAuthorityError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ContractNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{contract_type}/download")
def download_contract_pdf(
    contract_type: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    service: ContractSignatureService = Depends(_get_service),
) -> Response:
    """Télécharge le PDF certifié signé ou le PDF brouillon pré-rempli pour impression."""
    company = db.get(Company, tenant.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Entreprise introuvable")

    contract = service.get_contract(tenant.company_id, contract_type)

    # Si document déjà signé ou soumis pour vérification : FAIL-CLOSED strict
    signed_statuses = {
        ContractLifecycleStatus.SIGNED.value,
        ContractLifecycleStatus.CUSTOMER_SIGNED.value,
        ContractLifecycleStatus.FULLY_EXECUTED.value,
        ContractLifecycleStatus.PENDING_VERIFICATION.value,
        ContractLifecycleStatus.UPLOADED_FOR_REVIEW.value,
    }
    if contract.status in signed_statuses:
        if not contract.storage_path:
            logger.critical(
                "Document %s absent du stockage en base pour company_id=%s, type=%s",
                contract.status,
                tenant.company_id,
                contract_type,
            )
            raise HTTPException(
                status_code=500,
                detail="Document signé introuvable dans le stockage sécurisé. Un incident d'intégrité a été consigné.",
            )
        from pathlib import Path
        full_path = Path(service._settings.artifact_root) / contract.storage_path
        if not full_path.exists():
            logger.critical(
                "Fichier introuvable sur le disque: %s pour company_id=%s",
                full_path,
                tenant.company_id,
            )
            raise HTTPException(
                status_code=500,
                detail="Fichier certifié manquant sur le disque persistant. Un incident d'intégrité a été consigné.",
            )
        pdf_bytes = full_path.read_bytes()
        media_type = "application/pdf"
        filename = f"{contract_type}_{contract.status}_{contract.version}.pdf"
        return Response(
            content=pdf_bytes,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # Document brouillon / vierge pré-rempli
    if contract.status in (ContractLifecycleStatus.PENDING_SIGNATURE.value, ContractLifecycleStatus.DRAFT.value, ContractLifecycleStatus.READY_FOR_SIGNATURE.value):
        pdf_bytes = service.generate_draft_pdf(company, contract_type)
        filename = f"{contract_type}_Brouillon_{contract.version}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    raise HTTPException(
        status_code=400,
        detail=f"Statut contractuel invalide pour le téléchargement ({contract.status}).",
    )


class VerifyWetInkRequest(BaseModel):
    approved: bool
    rejection_reason: str | None = None


@router.post("/{contract_type}/verify-wet-ink")
def verify_wet_ink_contract(
    contract_type: str,
    payload: VerifyWetInkRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    service: ContractSignatureService = Depends(_get_service),
) -> dict:
    """Permet au dirigeant / admin de valider ou rejeter un document manuscrit soumis."""
    user = identity.user
    role_str = str(getattr(user, "role", "") or "").lower()
    if role_str not in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seul un propriétaire ou un administrateur peut valider une signature manuscrite.",
        )

    try:
        updated = service.verify_wet_ink_signature(
            company_id=tenant.company_id,
            contract_type=contract_type,
            approved=payload.approved,
            verifier_user=user,
            rejection_reason=payload.rejection_reason,
        )
        return {
            "contract_id": str(updated.id),
            "contract_type": updated.contract_type,
            "status": updated.status,
            "signature_mode": updated.signature_mode,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
