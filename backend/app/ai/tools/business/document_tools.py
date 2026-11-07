"""Document and Contract AI tools for Central AI orchestration.

Provides secure document and contract querying, detail extraction,
and ephemeral signed download tokens for Central AI.
Guarantees strict tenant isolation and prompt-injection neutralization.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from pydantic import Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.ai.tools.base import LegalAITool, OCRAITool, ToolArguments
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.models.company_contract import CompanyContract
from backend.app.models.user import User
from backend.app.models.workspace import TenantDocument
from backend.app.services.document_ai_service import DocumentAIService, LEGAL_DISCLAIMER
from backend.app.services.secure_document_token_service import SecureDocumentTokenService


def _sanitize_untrusted_text(text: str | None) -> str:
    """Neutralise les balises fermantes et délimiteurs pour éviter les injections de prompt indirectes."""
    if not text:
        return ""
    # Neutraliser toute tentative de clore la balise de délimitation
    sanitized = text.replace("</untrusted_document_data>", "[TAG_NEUTRALIZED]")
    sanitized = sanitized.replace("<untrusted_document_data", "[TAG_NEUTRALIZED")
    # Neutraliser les tentatives de délimiteurs de prompt chatml / inst
    sanitized = sanitized.replace("<|im_end|>", "[TOKEN_NEUTRALIZED]")
    sanitized = sanitized.replace("<|im_start|>", "[TOKEN_NEUTRALIZED]")
    sanitized = sanitized.replace("[INST]", "[TOKEN_NEUTRALIZED]")
    sanitized = sanitized.replace("[/INST]", "[TOKEN_NEUTRALIZED]")
    return sanitized


# ============================================================================
# Arguments Pydantic
# ============================================================================


class SearchDocumentsArgs(ToolArguments):
    query: str = Field(default="", description="Mot-clé de recherche dans le texte ou nom de fichier.")
    kind: str | None = Field(default=None, description="Type de document filtré : 'ocr' ou 'legal'.")
    limit: int = Field(default=10, description="Nombre maximal de documents retournés (1 à 25).")


class GetDocumentDetailArgs(ToolArguments):
    document_id: str = Field(description="Identifiant UUID du document.")


class GetDocumentDownloadUrlArgs(ToolArguments):
    document_id: str = Field(description="Identifiant UUID du document à télécharger.")


class SearchContractsArgs(ToolArguments):
    query: str = Field(default="", description="Mot-clé dans le titre ou les clauses du contrat.")
    contract_type: str | None = Field(default=None, description="Type de contrat (ex: pilot, enterprise, custom).")
    status: str | None = Field(default=None, description="Statut du contrat (draft, pending_signature, active, signed).")
    limit: int = Field(default=10, description="Nombre maximal de contrats retournés (1 à 25).")


class GetContractDetailArgs(ToolArguments):
    contract_id: str = Field(description="Identifiant UUID du contrat.")


class GetContractDownloadUrlArgs(ToolArguments):
    contract_id: str = Field(description="Identifiant UUID du contrat à télécharger.")


class GetOCRDocumentArgs(ToolArguments):
    document_id: str = Field(description="Identifiant UUID du document OCR analysé.")


class ProposeAccountingFromOCRArgs(ToolArguments):
    document_id: str = Field(description="Identifiant UUID du document OCR pour lequel préparer une proposition d'écriture comptable.")


class AnalyzeLegalDocumentArgs(ToolArguments):
    document_id: str = Field(description="Identifiant UUID du document juridique ou contrat à analyser.")


# ============================================================================
# Outils Documents (OCR / Factures Scannées / Fichiers)
# ============================================================================


class SearchDocumentsTool(OCRAITool):
    name = "search_documents"
    description = (
        "Recherche parmi les documents, factures scannées et pièces justificatives enregistrées de l'entreprise. "
        "Filtre par mot-clé, classification ou type (ocr / legal)."
    )
    input_schema = SearchDocumentsArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: SearchDocumentsArgs) -> ToolResult:
        query = select(TenantDocument).where(TenantDocument.company_id == context.tenant.company_id)

        if arguments.kind:
            query = query.where(TenantDocument.kind == arguments.kind)

        search_term = arguments.query.strip()
        if search_term:
            query = query.where(
                or_(
                    TenantDocument.filename.ilike(f"%{search_term}%"),
                    TenantDocument.classification.ilike(f"%{search_term}%"),
                    TenantDocument.extracted_text.ilike(f"%{search_term}%"),
                )
            )

        limit = max(1, min(arguments.limit, 25))
        query = query.order_by(TenantDocument.created_at.desc()).limit(limit)

        records = self._session.scalars(query).all()
        results = [
            {
                "document_id": str(doc.id),
                "filename": doc.filename,
                "kind": doc.kind,
                "classification": doc.classification,
                "byte_size": doc.byte_size,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "snippet": _sanitize_untrusted_text((doc.extracted_text or "")[:200]),
            }
            for doc in records
        ]

        return ToolResult(
            success=True,
            data={
                "count": len(results),
                "documents": results,
                "message": (
                    f"{len(results)} document(s) trouvé(s) pour '{arguments.query}'."
                    if results
                    else f"Aucun document trouvé pour la recherche '{arguments.query}'."
                ),
            },
            source_refs=("tenant_documents",),
        )


class GetDocumentDetailTool(OCRAITool):
    name = "get_document_detail"
    description = (
        "Récupère le détail complet et le texte extrait d'un document spécifique de l'entreprise. "
        "Le contenu extrait est strictement encapsulé pour la sécurité."
    )
    input_schema = GetDocumentDetailArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: GetDocumentDetailArgs) -> ToolResult:
        try:
            doc_uuid = UUID(arguments.document_id)
        except ValueError:
            return ToolResult(success=False, error="Format UUID de document invalide")

        doc = self._session.scalar(
            select(TenantDocument).where(
                TenantDocument.id == doc_uuid,
                TenantDocument.company_id == context.tenant.company_id,
            )
        )
        if doc is None:
            return ToolResult(
                success=False,
                error="Document introuvable ou vous n'avez pas l'autorisation d'y accéder.",
            )

        analysis = {}
        if doc.analysis_json:
            try:
                analysis = json.loads(doc.analysis_json)
            except json.JSONDecodeError:
                analysis = {}

        raw_text = doc.extracted_text or ""
        sanitized_text = _sanitize_untrusted_text(raw_text)

        wrapped_text = (
            f"<untrusted_document_data source_document_id=\"{doc.id}\" filename=\"{doc.filename}\">\n"
            f"{sanitized_text}\n"
            f"</untrusted_document_data>"
        )

        return ToolResult(
            success=True,
            data={
                "document_id": str(doc.id),
                "filename": doc.filename,
                "kind": doc.kind,
                "classification": doc.classification,
                "byte_size": doc.byte_size,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "analysis": analysis,
                "extracted_content": wrapped_text,
                "has_download": bool(doc.storage_path or doc.extracted_text),
            },
            source_refs=("tenant_documents",),
        )


class GetDocumentDownloadUrlTool(OCRAITool):
    name = "get_document_download_url"
    description = (
        "Génère une URL de téléchargement PDF sécurisée et temporaire (15 minutes) pour un document de l'entreprise. "
        "Le jeton cryptographique HMAC est lié exclusivement à votre session et votre entreprise."
    )
    input_schema = GetDocumentDownloadUrlArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session
        self._token_service = SecureDocumentTokenService()

    async def run(self, context: ToolExecutionContext, arguments: GetDocumentDownloadUrlArgs) -> ToolResult:
        try:
            doc_uuid = UUID(arguments.document_id)
        except ValueError:
            return ToolResult(success=False, error="Format UUID de document invalide")

        doc = self._session.scalar(
            select(TenantDocument).where(
                TenantDocument.id == doc_uuid,
                TenantDocument.company_id == context.tenant.company_id,
            )
        )
        if doc is None:
            return ToolResult(
                success=False,
                error="Document introuvable ou vous n'avez pas l'autorisation d'y accéder.",
            )

        user_id = context.user_id or context.tenant.user_id
        if user_id is None:
            return ToolResult(
                success=False,
                error="Utilisateur non authentifié pour générer un lien de téléchargement sécurisé.",
            )

        download_filename = doc.filename
        if not download_filename.lower().endswith(".pdf"):
            download_filename = f"{download_filename}.pdf"

        token = self._token_service.generate_download_token(
            company_id=context.tenant.company_id,
            user_id=user_id,
            doc_id=doc.id,
            doc_type="document",
            filename=download_filename,
            expires_in_seconds=900,
        )

        download_url = f"/api/v1/secure-downloads/{token}"

        return ToolResult(
            success=True,
            data={
                "document_id": str(doc.id),
                "filename": download_filename,
                "download_url": download_url,
                "expires_in_seconds": 900,
                "message": (
                    f"Lien de téléchargement sécurisé généré pour '{download_filename}'. "
                    f"Ce lien est valable 15 minutes et accessible uniquement par votre compte."
                ),
            },
            source_refs=("tenant_documents",),
        )


# ============================================================================
# Outils Contrats (Company Contracts)
# ============================================================================


class SearchContractsTool(LegalAITool):
    name = "search_contracts"
    description = (
        "Recherche parmi les contrats et accords légaux de l'entreprise (contrats de pilote, enterprise, NDA, etc.). "
        "Filtre par mot-clé, type de contrat ou statut."
    )
    input_schema = SearchContractsArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: SearchContractsArgs) -> ToolResult:
        query = select(CompanyContract).where(CompanyContract.company_id == context.tenant.company_id)

        if arguments.contract_type:
            query = query.where(CompanyContract.contract_type == arguments.contract_type)

        if arguments.status:
            query = query.where(CompanyContract.status == arguments.status)

        search_term = arguments.query.strip()
        if search_term:
            query = query.where(
                or_(
                    CompanyContract.title.ilike(f"%{search_term}%"),
                    CompanyContract.contract_type.ilike(f"%{search_term}%"),
                    CompanyContract.content_text.ilike(f"%{search_term}%"),
                )
            )

        limit = max(1, min(arguments.limit, 25))
        query = query.order_by(CompanyContract.created_at.desc()).limit(limit)

        records = self._session.scalars(query).all()
        results = [
            {
                "contract_id": str(c.id),
                "title": c.title,
                "contract_type": c.contract_type,
                "status": c.status,
                "execution_state": c.execution_state,
                "version": c.version,
                "language": c.language,
                "signed_at": c.signed_at.isoformat() if c.signed_at else None,
                "provider_signed_at": c.provider_signed_at.isoformat() if c.provider_signed_at else None,
            }
            for c in records
        ]

        return ToolResult(
            success=True,
            data={
                "count": len(results),
                "contracts": results,
                "message": (
                    f"{len(results)} contrat(s) trouvé(s) pour cette entreprise."
                    if results
                    else f"Aucun contrat trouvé pour la recherche '{arguments.query}'."
                ),
            },
            source_refs=("company_contracts",),
        )


class GetContractDetailTool(LegalAITool):
    name = "get_contract_detail"
    description = (
        "Consulte le contenu textuel, les clauses, signataires et détails d'un contrat spécifique de l'entreprise. "
        "Le texte est protégé contre les injections et accompagné d'une mention juridique."
    )
    input_schema = GetContractDetailArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: GetContractDetailArgs) -> ToolResult:
        try:
            contract_uuid = UUID(arguments.contract_id)
        except ValueError:
            return ToolResult(success=False, error="Format UUID de contrat invalide")

        contract = self._session.scalar(
            select(CompanyContract).where(
                CompanyContract.id == contract_uuid,
                CompanyContract.company_id == context.tenant.company_id,
            )
        )
        if contract is None:
            return ToolResult(
                success=False,
                error="Contrat introuvable ou vous n'avez pas l'autorisation d'y accéder.",
            )

        raw_content = contract.content_text or ""
        sanitized_content = _sanitize_untrusted_text(raw_content)

        wrapped_content = (
            f"<untrusted_document_data source_contract_id=\"{contract.id}\" title=\"{contract.title}\">\n"
            f"{sanitized_content}\n"
            f"</untrusted_document_data>"
        )

        return ToolResult(
            success=True,
            data={
                "contract_id": str(contract.id),
                "title": contract.title,
                "contract_type": contract.contract_type,
                "status": contract.status,
                "execution_state": contract.execution_state,
                "version": contract.version,
                "language": contract.language,
                "signatory_name": contract.signatory_name,
                "signatory_email": contract.signatory_email,
                "signed_at": contract.signed_at.isoformat() if contract.signed_at else None,
                "provider_signed_at": contract.provider_signed_at.isoformat() if contract.provider_signed_at else None,
                "content": wrapped_content,
                "disclaimer": LEGAL_DISCLAIMER,
                "advisory_warning": "Cette consultation est fournie à titre indicatif et ne constitue pas un conseil juridique.",
            },
            source_refs=("company_contracts",),
        )


class GetContractDownloadUrlTool(LegalAITool):
    name = "get_contract_download_url"
    description = (
        "Génère une URL de téléchargement PDF sécurisée et temporaire (15 minutes) pour un contrat spécifique de l'entreprise. "
        "Le jeton cryptographique garantit l'intégrité et l'étanchéité multi-tenant."
    )
    input_schema = GetContractDownloadUrlArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session
        self._token_service = SecureDocumentTokenService()

    async def run(self, context: ToolExecutionContext, arguments: GetContractDownloadUrlArgs) -> ToolResult:
        try:
            contract_uuid = UUID(arguments.contract_id)
        except ValueError:
            return ToolResult(success=False, error="Format UUID de contrat invalide")

        contract = self._session.scalar(
            select(CompanyContract).where(
                CompanyContract.id == contract_uuid,
                CompanyContract.company_id == context.tenant.company_id,
            )
        )
        if contract is None:
            return ToolResult(
                success=False,
                error="Contrat introuvable ou vous n'avez pas l'autorisation d'y accéder.",
            )

        user_id = context.user_id or context.tenant.user_id
        if user_id is None:
            return ToolResult(
                success=False,
                error="Utilisateur non authentifié pour générer un lien de téléchargement sécurisé.",
            )

        filename = f"contrat_{contract.contract_type}_{contract.version}.pdf"
        token = self._token_service.generate_download_token(
            company_id=context.tenant.company_id,
            user_id=user_id,
            doc_id=contract.id,
            doc_type="contract",
            filename=filename,
            expires_in_seconds=900,
        )

        download_url = f"/api/v1/secure-downloads/{token}"

        return ToolResult(
            success=True,
            data={
                "contract_id": str(contract.id),
                "title": contract.title,
                "filename": filename,
                "download_url": download_url,
                "expires_in_seconds": 900,
                "message": (
                    f"Lien de téléchargement sécurisé généré pour '{contract.title}'. "
                    f"Ce lien est valable 15 minutes et strictement réservé à votre session."
                ),
            },
            source_refs=("company_contracts",),
        )


# ============================================================================
# Outils Préexistants (OCR & Legal AI)
# ============================================================================


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
                "extracted_text_snippet": _sanitize_untrusted_text((doc.extracted_text or "")[:500]),
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
                "summary": _sanitize_untrusted_text((doc.extracted_text or "")[:400]),
                "disclaimer": LEGAL_DISCLAIMER,
                "advisory_warning": "Cette analyse est informative et ne remplace pas l'avis d'un professionnel du droit.",
            },
            source_refs=("tenant_documents",),
        )
