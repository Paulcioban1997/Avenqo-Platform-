"""Document AI tools for Central AI orchestration (Phase 8.1).

Covers OCR AI (text extraction, field parsing, accounting proposal) and Legal AI
(clause analysis, obligations, risks with mandatory legal disclaimer).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.tools.base import OCRAITool, LegalAITool, ToolArguments
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.models.workspace import TenantDocument
from backend.app.models.user import User
from backend.app.services.document_ai_service import DocumentAIService, LEGAL_DISCLAIMER


class GetOCRDocumentArgs(ToolArguments):
    document_id: str = Field(description="Identifiant UUID du document OCR analysé.")


class ProposeAccountingFromOCRArgs(ToolArguments):
    document_id: str = Field(description="Identifiant UUID du document OCR pour lequel préparer une proposition d'écriture comptable.")


class AnalyzeLegalDocumentArgs(ToolArguments):
    document_id: str = Field(description="Identifiant UUID du document juridique ou contrat à analyser.")


class GetOCRDocumentTool(OCRAITool):
    name = "get_ocr_document"
    description = (
        "Consulte les données extraites d'une facture ou document traité par OCR AI. "
        "Renvoie le texte extrait, la classification et les champs détectés (montant, date, émetteur)."
    )
    input_schema = GetOCRDocumentArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: GetOCRDocumentArgs) -> ToolResult:
        try:
            doc_uuid = UUID(arguments.document_id)
        except ValueError:
            return ToolResult(success=False, error="Format UUID de document invalide")

        doc = self._session.scalar(
            select(TenantDocument).where(
                TenantDocument.id == doc_uuid,
                TenantDocument.company_id == context.tenant.company_id,
                TenantDocument.kind == "ocr",
            )
        )
        if doc is None:
            return ToolResult(success=False, error="Document OCR introuvable pour cette entreprise")

        analysis = {}
        try:
            analysis = json.loads(doc.analysis_json or "{}")
        except json.JSONDecodeError:
            analysis = {}

        return ToolResult(
            success=True,
            data={
                "document_id": str(doc.id),
                "filename": doc.filename,
                "classification": doc.classification,
                "byte_size": doc.byte_size,
                "analysis": analysis,
                "extracted_text_snippet": (doc.extracted_text or "")[:500],
            },
            source_refs=("tenant_documents",),
        )


class ProposeAccountingFromOCRTool(OCRAITool):
    name = "propose_accounting_from_ocr"
    description = (
        "Prépare une proposition d'écriture comptable (AccountingInvoice) non confirmée à partir d'un document OCR. "
        "L'écriture nécessite une validation humaine obligatoire avant d'être actée dans le grand livre."
    )
    input_schema = ProposeAccountingFromOCRArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: ProposeAccountingFromOCRArgs) -> ToolResult:
        try:
            doc_uuid = UUID(arguments.document_id)
        except ValueError:
            return ToolResult(success=False, error="Format UUID de document invalide")

        actor = self._session.query(User).filter(User.id == context.tenant.user_id).first()
        if not actor:
            return ToolResult(success=False, error="Utilisateur introuvable")

        service = DocumentAIService(self._session)
        try:
            invoice = service.propose_accounting_entry(actor, doc_uuid)
        except LookupError as exc:
            return ToolResult(success=False, error=str(exc))
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))

        return ToolResult(
            success=True,
            data={
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "party_name": invoice.party_name,
                "total_amount": invoice.total_amount,
                "currency": invoice.currency,
                "is_confirmed": invoice.is_confirmed,
                "status": "pending_approval",
                "notes": invoice.notes,
                "message": "Proposition d'écriture préparée avec succès. Une validation humaine est requise avant comptabilisation.",
            },
            source_refs=("tenant_documents", "accounting_invoices"),
        )


class AnalyzeLegalDocumentTool(LegalAITool):
    name = "analyze_legal_document"
    description = (
        "Analyse un contrat ou document juridique de l'entreprise. "
        "Extrait les clauses, obligations et points d'attention avec la clause de non-responsabilité juridique obligatoire."
    )
    input_schema = AnalyzeLegalDocumentArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: AnalyzeLegalDocumentArgs) -> ToolResult:
        try:
            doc_uuid = UUID(arguments.document_id)
        except ValueError:
            return ToolResult(success=False, error="Format UUID de document invalide")

        doc = self._session.scalar(
            select(TenantDocument).where(
                TenantDocument.id == doc_uuid,
                TenantDocument.company_id == context.tenant.company_id,
                TenantDocument.kind == "legal",
            )
        )
        if doc is None:
            return ToolResult(success=False, error="Document juridique introuvable pour cette entreprise")

        analysis = {}
        try:
            analysis = json.loads(doc.analysis_json or "{}")
        except json.JSONDecodeError:
            analysis = {}

        return ToolResult(
            success=True,
            data={
                "document_id": str(doc.id),
                "filename": doc.filename,
                "classification": doc.classification,
                "analysis": analysis,
                "summary": (doc.extracted_text or "")[:400],
                "disclaimer": LEGAL_DISCLAIMER,
                "advisory_warning": "Cette analyse est informative et ne remplace pas l'avis d'un professionnel du droit.",
            },
            source_refs=("tenant_documents",),
        )
