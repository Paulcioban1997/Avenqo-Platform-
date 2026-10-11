"""OCR AI et Legal AI — téléversement réel, extraction réelle."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, get_tenant_context
from backend.app.dependencies.subscription import require_active_subscription
from backend.app.services.document_ai_service import DocumentAIService, UnsupportedDocumentError
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from shared.ai_engine.contracts import TenantContext

ocr_router = APIRouter(prefix="/ocr", tags=["ocr"])
legal_router = APIRouter(prefix="/legal", tags=["legal"])


def _service(db: Session = Depends(get_db)) -> DocumentAIService:
    return DocumentAIService(db)


def _require_module(db: Session, tenant: TenantContext, key: str) -> None:
    if not ModuleEntitlementService(db).can_use_module(tenant, key):
        raise HTTPException(403, {"code": "module_inactive", "module": key})


def _payload(row) -> dict:
    import json

    try:
        analysis = json.loads(row.analysis_json) if row.analysis_json else None
    except json.JSONDecodeError:
        analysis = row.analysis_json
    return {
        "id": str(row.id),
        "filename": row.filename,
        "classification": row.classification,
        "byte_size": row.byte_size,
        "extracted_text": row.extracted_text,
        "analysis": analysis,
        "disclaimer": row.analysis_disclaimer,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@ocr_router.get("/documents")
def list_ocr(
    identity: CurrentIdentity = Depends(get_current_identity),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    service: DocumentAIService = Depends(_service),
    _: None = Depends(require_active_subscription),
) -> list[dict]:
    _require_module(db, tenant, "ocr")
    return [_payload(row) for row in service.list_documents(identity.user, "ocr")]


@ocr_router.post("/documents", status_code=201)
async def upload_ocr(
    file: UploadFile = File(...),
    identity: CurrentIdentity = Depends(get_current_identity),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    service: DocumentAIService = Depends(_service),
    _: None = Depends(require_active_subscription),
) -> dict:
    _require_module(db, tenant, "ocr")
    content = await file.read()
    try:
        row = service.ingest(
            identity.user,
            kind="ocr",
            filename=file.filename or "document.txt",
            content=content,
            content_type=file.content_type or "text/plain",
        )
    except UnsupportedDocumentError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _payload(row)


@ocr_router.get("/documents/{document_id}")
def get_ocr(
    document_id: UUID,
    identity: CurrentIdentity = Depends(get_current_identity),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    service: DocumentAIService = Depends(_service),
    _: None = Depends(require_active_subscription),
) -> dict:
    _require_module(db, tenant, "ocr")
    try:
        return _payload(service.get_document(identity.user, document_id))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@ocr_router.post("/documents/{document_id}/accounting-proposal", status_code=201)
def propose_accounting(
    document_id: UUID,
    identity: CurrentIdentity = Depends(get_current_identity),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    service: DocumentAIService = Depends(_service),
    _: None = Depends(require_active_subscription),
) -> dict:
    _require_module(db, tenant, "ocr")
    if not ModuleEntitlementService(db).can_use_module(tenant, "accounting"):
        raise HTTPException(403, {"code": "module_inactive", "module": "accounting"})
    try:
        invoice = service.propose_accounting_entry(identity.user, document_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "id": str(invoice.id),
        "invoice_number": invoice.invoice_number,
        "total_amount": invoice.total_amount,
        "is_confirmed": invoice.is_confirmed,
        "status": invoice.status,
        "notes": invoice.notes,
    }


@legal_router.get("/documents")
def list_legal(
    identity: CurrentIdentity = Depends(get_current_identity),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    service: DocumentAIService = Depends(_service),
    _: None = Depends(require_active_subscription),
) -> list[dict]:
    _require_module(db, tenant, "legal")
    return [_payload(row) for row in service.list_documents(identity.user, "legal")]


@legal_router.post("/documents", status_code=201)
async def upload_legal(
    file: UploadFile = File(...),
    identity: CurrentIdentity = Depends(get_current_identity),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    service: DocumentAIService = Depends(_service),
    _: None = Depends(require_active_subscription),
) -> dict:
    _require_module(db, tenant, "legal")
    content = await file.read()
    try:
        row = service.ingest(
            identity.user,
            kind="legal",
            filename=file.filename or "contract.txt",
            content=content,
            content_type=file.content_type or "text/plain",
        )
    except UnsupportedDocumentError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _payload(row)


@legal_router.post("/compare")
def compare_legal(
    left_id: UUID = Form(...),
    right_id: UUID = Form(...),
    identity: CurrentIdentity = Depends(get_current_identity),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    service: DocumentAIService = Depends(_service),
    _: None = Depends(require_active_subscription),
) -> dict:
    _require_module(db, tenant, "legal")
    try:
        return service.compare(identity.user, left_id, right_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
