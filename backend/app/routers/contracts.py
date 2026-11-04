"""Routes API pour l'espace 'Mes contrats' et la signature des contrats d'entreprise Avenqo."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, get_tenant_context
from backend.app.models.company import Company
from backend.app.services.account_notifications import AccountNotifier
from backend.app.services.audit_log_service import AuditLogService
from backend.app.services.contract_signature_service import (
    ContractAuthorityError,
    ContractNotFoundError,
    ContractSignatureService,
)
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/contracts", tags=["contracts"])


class ContractSignRequest(BaseModel):
    signatory_title: str = Field(..., min_length=2, max_length=120, description="Titre ou fonction légale du signataire (ex: Président, CEO)")
    declared_authority: bool = Field(..., description="Déclaration expresse d'autorité pour engager l'entreprise")
    consent_checkbox: bool = Field(..., description="Consentement exprès et explicite aux termes du contrat")


class ContractItemResponse(BaseModel):
    id: str
    company_id: str
    contract_type: str
    title: str
    status: str
    version: str
    language: str
    signature_mode: str | None
    signatory_name: str | None
    signatory_title: str | None
    signatory_email: str | None
    signed_at: str | None
    sha256_hash: str
    has_pdf: bool


def _get_service(db: Session = Depends(get_db)) -> ContractSignatureService:
    return ContractSignatureService(db, audit_service=AuditLogService(db), notifier=AccountNotifier())


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
            version=c.version,
            language=c.language,
            signature_mode=c.signature_mode,
            signatory_name=c.signatory_name,
            signatory_title=c.signatory_title,
            signatory_email=c.signatory_email,
            signed_at=c.signed_at.isoformat() if c.signed_at else None,
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
        "version": contract.version,
        "language": contract.language,
        "signature_mode": contract.signature_mode,
        "signatory_name": contract.signatory_name,
        "signatory_title": contract.signatory_title,
        "signatory_email": contract.signatory_email,
        "signed_at": contract.signed_at.isoformat() if contract.signed_at else None,
        "sha256_hash": contract.sha256_hash,
        "content_text": contract.content_text,
        "has_pdf": bool(contract.storage_path),
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
        )
        return receipt
    except ContractAuthorityError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ContractNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{contract_type}/upload-manuscript")
async def upload_manuscript_signature(
    contract_type: str,
    file: UploadFile = File(...),
    signatory_title: str = Form("Dirigeant"),
    request: Request = None,
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

    # Si déjà signé et stocké sur disque
    if contract.storage_path:
        from pathlib import Path
        full_path = Path(service._settings.artifact_root) / contract.storage_path
        if full_path.exists():
            pdf_bytes = full_path.read_bytes()
            media_type = "application/pdf"
            filename = f"{contract_type}_Signe_{contract.version}.pdf"
            return Response(
                content=pdf_bytes,
                media_type=media_type,
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

    # Sinon générer le PDF brouillon / d'impression
    pdf_bytes = service.generate_draft_pdf(company, contract_type)
    filename = f"{contract_type}_Brouillon_{contract.version}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
