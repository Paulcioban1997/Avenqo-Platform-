"""Document and Contract AI tools for Central AI orchestration.

Provides secure document and contract querying, lossless source reading,
structured `Decimal` invoice extraction with mathematical verification,
cell/page provenance evidence, and ephemeral signed download tokens for Central AI.
Guarantees strict tenant isolation (`company_id`), RBAC (`data:read`), and prompt-injection neutralization.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any
from uuid import UUID

from pydantic import Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.ai.tools.base import (
    AITool,
    LegalAITool,
    OCRAITool,
    PlatformContractAITool,
    ToolArguments,
)
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.config.settings import get_settings
from backend.app.models import Dataset, DatasetStatus
from backend.app.models.company_contract import CompanyContract
from backend.app.models.user import User
from backend.app.models.workspace import TenantDocument
from backend.app.services.contract_authorization_service import ContractAuthorizationService
from backend.app.services.document_ai_service import DocumentAIService, LEGAL_DISCLAIMER
from backend.app.services.document_extraction import (
    CellProvenance,
    DocumentExtractionBundle,
    EXCEL_SUFFIXES,
    extract_document_bundle,
)
from backend.app.services.invoice_extraction_service import (
    InvoiceExtractionReport,
    InvoiceExtractionService,
)
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.services.secure_document_token_service import SecureDocumentTokenService
from shared.ai_engine.contracts import TenantContext


def _sanitize_untrusted_text(text: str | None) -> str:
    """Neutralise les balises fermantes, délimiteurs d'injection et artefacts bruts `***`."""
    if not text:
        return ""
    sanitized = text.replace("</untrusted_document_data>", "[TAG_NEUTRALIZED]")
    sanitized = sanitized.replace("<untrusted_document_data", "[TAG_NEUTRALIZED")
    sanitized = sanitized.replace("<|im_end|>", "[TOKEN_NEUTRALIZED]")
    sanitized = sanitized.replace("<|im_start|>", "[TOKEN_NEUTRALIZED]")
    sanitized = sanitized.replace("[INST]", "[TOKEN_NEUTRALIZED]")
    sanitized = sanitized.replace("[/INST]", "[TOKEN_NEUTRALIZED]")
    sanitized = re.sub(r"\*{3,}", "", sanitized)
    return sanitized


def _clean_summary_snippet(text: str | None, max_len: int = 200) -> str:
    """Nettoie un extrait de résumé sans jamais laisser d'artefact markdown `***`."""
    cleaned = _sanitize_untrusted_text(text)
    compact = " ".join(cleaned.split()).strip()
    return compact[:max_len]


def _col_letters_to_index(letters: str) -> int:
    idx = 0
    for ch in letters.upper():
        if "A" <= ch <= "Z":
            idx = idx * 26 + (ord(ch) - 64)
    return max(1, idx)


def _parse_cell_or_range(ref: str) -> tuple[str | None, int, int, int, int] | None:
    """Parse `Facture!F42`, `F42`, `A12:F20`, ou `Transport!A12:F20` en `(sheet, r1, c1, r2, c2)`."""
    raw = ref.strip()
    if not raw:
        return None
    sheet_part: str | None = None
    coord_part = raw
    if "!" in raw:
        sheet_part, coord_part = raw.split("!", 1)
        sheet_part = sheet_part.strip().strip("'") or None
        coord_part = coord_part.strip()

    m_range = re.match(r"^([A-Za-z]+)(\d+)\s*:\s*([A-Za-z]+)(\d+)$", coord_part)
    if m_range:
        c1 = _col_letters_to_index(m_range.group(1))
        r1 = int(m_range.group(2))
        c2 = _col_letters_to_index(m_range.group(3))
        r2 = int(m_range.group(4))
        return sheet_part, min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2)

    m_single = re.match(r"^([A-Za-z]+)(\d+)$", coord_part)
    if m_single:
        col_str = m_single.group(1).upper()
        row_num = int(m_single.group(2))
        # Coordonnées textuelles PDF/DOCX type L14 ou P3
        if col_str in {"L", "P"} and sheet_part and (
            sheet_part.lower().startswith("page")
            or sheet_part.lower() in {"paragraphes", "texte", "ocr"}
        ):
            return sheet_part, row_num, 1, row_num, 1
        c1 = _col_letters_to_index(col_str)
        return sheet_part, row_num, c1, row_num, c1
    return None


def _resolve_tenant_document_or_dataset_bundle(
    session: Session,
    auth: ContractAuthorizationService,
    context: ToolExecutionContext,
    document_id_str: str,
) -> tuple[DocumentExtractionBundle | None, dict[str, Any] | None, str | None]:
    """Résout de façon strictement isolée par `company_id` un `TenantDocument` (ou un `Dataset` Excel/PDF)
    et retourne `(bundle, doc_meta, error_message)`."""
    if "data:read" not in context.permissions:
        return None, None, "Permissions insuffisantes pour consulter ce document."

    try:
        doc_uuid = UUID(document_id_str)
    except ValueError:
        return None, None, "Format UUID de document invalide"

    doc = session.scalar(
        select(TenantDocument).where(
            TenantDocument.id == doc_uuid,
            TenantDocument.company_id == context.tenant.company_id,
        )
    )
    if doc is not None:
        can_access, err = auth.can_access_document(context.tenant, doc, context.permissions)
        if not can_access:
            return None, None, err or "Document introuvable ou vous n'avez pas l'autorisation d'y accéder."
        service = DocumentAIService(session)
        bundle = service.load_source_bundle(doc)
        meta = {
            "document_id": str(doc.id),
            "source_kind": "tenant_document",
            "filename": doc.filename,
            "kind": doc.kind,
            "classification": doc.classification,
            "byte_size": doc.byte_size,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "source_ref": "tenant_documents",
        }
        return bundle, meta, None

    # Repli sécurisé vers un `Dataset` appartenant EXCLUSIVEMENT à la même entreprise (`company_id`)
    dataset = session.scalar(
        select(Dataset).where(
            Dataset.id == doc_uuid,
            Dataset.company_id == context.tenant.company_id,
        )
    )
    if dataset is not None:
        current_version = next((v for v in dataset.versions if v.is_current), None)
        raw_path = _find_dataset_raw_file(dataset, current_version)
        if raw_path is None:
            return None, None, "Le fichier source original de ce dataset n'est pas disponible sur le stockage."
        filename = (
            (current_version.file_name if current_version and current_version.file_name else None)
            or dataset.name
            or raw_path.name
        )
        bundle = extract_document_bundle(filename, raw_path.read_bytes())
        meta = {
            "document_id": str(dataset.id),
            "source_kind": "company_dataset",
            "filename": filename,
            "kind": "dataset",
            "classification": "workbook" if Path(filename).suffix.lower() in EXCEL_SUFFIXES else dataset.type,
            "byte_size": raw_path.stat().st_size,
            "created_at": dataset.uploaded_at.isoformat() if getattr(dataset, "uploaded_at", None) else None,
            "source_ref": str(dataset.id),
        }
        return bundle, meta, None

    return None, None, "Document introuvable ou vous n'avez pas l'autorisation d'y accéder."


def _find_dataset_raw_file(dataset: Dataset, current_version: Any) -> Path | None:
    artifact_str = (
        (current_version.artifact_path if current_version and current_version.artifact_path else None)
        or dataset.source
    )
    if not artifact_str:
        return None
    direct = Path(artifact_str)
    if direct.is_file():
        return direct
    settings = get_settings()
    norm = str(artifact_str).replace("\\", "/")
    candidates: list[Path] = [Path(settings.artifact_root) / artifact_str]
    if "company_datasets/" in norm:
        rel = norm.split("company_datasets/", 1)[1]
        candidates.extend([
            Path(settings.artifact_root) / "company_datasets" / rel,
            Path("var/artifacts/company_datasets") / rel,
            Path("artifacts/company_datasets") / rel,
        ])
    for cand in candidates:
        if cand.is_file():
            return cand
    return None


class StructuredDocumentAITool(AITool):
    """Outil de lecture intégrale et d'extraction financière vérifiée (`ocr`, `accounting`, `cross_agent`)."""

    agent_ids = frozenset({"ocr", "accounting", "cross_agent"})
    required_entitlements = frozenset()
    required_permissions = ("ai:use", "data:read")
    read_only = True
    mutates = False

    @staticmethod
    def _ensure_document_module_entitlement(session: Session, tenant: TenantContext) -> tuple[bool, str | None]:
        ent = ModuleEntitlementService(session)
        active = set(ent.get_active_modules(tenant))
        if active.intersection({"ocr", "accounting", "legal"}):
            return True, None
        return False, "Un module documentaire ou comptable actif (OCR AI ou Accounting AI) est requis."


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


class GetDocumentSourceArgs(ToolArguments):
    document_id: str = Field(description="Identifiant UUID du document ou classeur Excel.")
    sheet_name: str | None = Field(
        default=None,
        description="Nom optionnel d'un onglet Excel, tableau DOCX ('Table 1') ou page PDF ('Page 1') spécifique.",
    )
    offset: int = Field(default=0, ge=0, description="Décalage en caractères pour parcourir un très grand document.")
    max_chars: int = Field(
        default=4500,
        ge=200,
        le=6000,
        description="Fenêtre maximale de texte source retournée dans cet appel (200 à 6000).",
    )


class ExtractInvoiceTotalsArgs(ToolArguments):
    document_id: str = Field(description="Identifiant UUID du document de facture (Excel, PDF, DOCX, CSV ou OCR).")
    sheet_name: str | None = Field(
        default=None,
        description="Filtre optionnel sur un onglet spécifique d'un classeur multi-feuilles.",
    )
    invoice_number: str | None = Field(
        default=None,
        description="Filtre optionnel par numéro de facture ou numéro de bon de commande (PO).",
    )


class GetDocumentCellEvidenceArgs(ToolArguments):
    document_id: str = Field(description="Identifiant UUID du document ou classeur Excel.")
    sheet_name: str | None = Field(default=None, description="Nom optionnel de l'onglet Excel ou de la page/table.")
    cell_ref: str | None = Field(
        default=None,
        description="Référence de cellule ou plage (ex: 'Facture!F42', 'F42', 'A12:F20').",
    )
    search_term: str | None = Field(
        default=None,
        description="Terme optionnel à rechercher dans les cellules (ex: 'TOTAL', '17175', 'TPS').",
    )
    limit: int = Field(default=25, ge=1, le=60, description="Nombre maximal de cellules retournées (1 à 60).")


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
    document_id: str = Field(
        description="Identifiant UUID du document OCR pour lequel préparer une proposition d'écriture comptable."
    )


class AnalyzeLegalDocumentArgs(ToolArguments):
    document_id: str = Field(description="Identifiant UUID du document juridique ou contrat à analyser.")


# ============================================================================
# Outils Documents (OCR / Factures Scannées / Classeurs Excel / Fichiers)
# ============================================================================


class SearchDocumentsTool(OCRAITool):
    name = "search_documents"
    description = (
        "Recherche parmi les documents, factures scannées, classeurs Excel et pièces justificatives de l'entreprise. "
        "ATTENTION : le champ `snippet` est un aperçu tronqué (200 caractères). Appelez TOUJOURS `extract_invoice_totals` "
        "ou `get_document_source` avant d'affirmer qu'un montant ou champ est absent."
    )
    input_schema = SearchDocumentsArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session
        self._auth = ContractAuthorizationService(session)

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
        query = query.order_by(TenantDocument.created_at.desc())

        all_records = list(self._session.scalars(query).all())
        records = self._auth.filter_accessible_documents(context.tenant, all_records, context.permissions)[:limit]

        results = [
            {
                "document_id": str(doc.id),
                "filename": doc.filename,
                "kind": doc.kind,
                "classification": doc.classification,
                "byte_size": doc.byte_size,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "snippet": _clean_summary_snippet(doc.extracted_text, 200),
                "is_truncated_preview": True,
            }
            for doc in records
        ]

        workbook_datasets: list[dict[str, Any]] = []
        if "data:read" in context.permissions and arguments.kind in (None, "ocr"):
            ds_query = select(Dataset).where(
                Dataset.company_id == context.tenant.company_id,
                Dataset.status == DatasetStatus.READY,
                Dataset.type.in_(["xlsx", "xlsm", "xls", "pdf"]),
            )
            if search_term:
                ds_query = ds_query.where(Dataset.name.ilike(f"%{search_term}%"))
            for ds in self._session.scalars(ds_query.limit(5)).all():
                workbook_datasets.append(
                    {
                        "document_id": str(ds.id),
                        "filename": ds.name,
                        "source_kind": "company_dataset",
                        "type": ds.type,
                        "is_truncated_preview": True,
                    }
                )

        payload: dict[str, Any] = {
            "count": len(results),
            "documents": results,
            "is_truncated_preview": True,
            "grounding_status": "preview_only",
            "grounding_note": (
                "Les aperçus de recherche sont tronqués à 200 caractères. "
                "Consultez `extract_invoice_totals` ou `get_document_source` sur le `document_id` complet avant toute conclusion sur un montant."
            ),
            "message": (
                f"{len(results)} document(s) trouvé(s) pour '{arguments.query}'."
                if results
                else f"Aucun document trouvé pour la recherche '{arguments.query}'."
            ),
        }
        if workbook_datasets:
            payload["workbook_datasets"] = workbook_datasets

        return ToolResult(
            success=True,
            data=payload,
            source_refs=("tenant_documents",),
            metadata={
                "grounding_status": "preview_only",
                "certified_grounding": False,
                "is_truncated_preview": True,
                "full_source_read": False,
            },
        )


class GetDocumentDetailTool(OCRAITool):
    name = "get_document_detail"
    description = (
        "Récupère le détail complet, l'analyse structurée et le texte extrait d'un document spécifique de l'entreprise. "
        "Le contenu extrait est strictement encapsulé pour la sécurité."
    )
    input_schema = GetDocumentDetailArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session
        self._auth = ContractAuthorizationService(session)

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

        can_access, err = self._auth.can_access_document(context.tenant, doc, context.permissions)
        if not can_access:
            return ToolResult(
                success=False,
                error=err or "Document introuvable ou vous n'avez pas l'autorisation d'y accéder.",
            )

        analysis: dict[str, Any] = {}
        if doc.analysis_json:
            try:
                analysis = json.loads(doc.analysis_json)
            except json.JSONDecodeError:
                analysis = {}

        doc_service = DocumentAIService(self._session)
        bundle = doc_service.load_source_bundle(doc)
        full_raw_text = bundle.full_text or doc.extracted_text or ""
        sanitized_text = _sanitize_untrusted_text(full_raw_text)

        is_windowed = False
        if len(sanitized_text) > 4200:
            sanitized_text = sanitized_text[:4200] + "\n[... SUITE DISPONIBLE VIA get_document_source(offset=4200) ...]"
            is_windowed = True

        wrapped_text = (
            f"<untrusted_document_data source_document_id=\"{doc.id}\" filename=\"{doc.filename}\">\n"
            f"{sanitized_text}\n"
            f"</untrusted_document_data>"
        )

        inv_summary: dict[str, Any] | None = None
        grounding_status = "source_accessible"
        certified = not is_windowed
        math_verified = False

        if doc.kind == "ocr" or (doc.classification in {"invoice", "receipt", "statement"}):
            inv_report = InvoiceExtractionService().extract_from_bundle(bundle)
            inv_summary = _compact_invoice_report_dict(inv_report)
            if inv_report.verification_status != "no_amount_found" or doc.classification == "invoice":
                grounding_status = inv_report.grounding_status
                certified = inv_report.certified_grounding
                math_verified = bool(inv_report.primary_invoice and inv_report.primary_invoice.math_verified)

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
                "invoice_extraction": inv_summary,
                "sheets": [s.to_summary_dict() for s in bundle.sheets],
                "extracted_content": wrapped_text,
                "full_source_read": True,
                "is_content_windowed": is_windowed,
                "grounding_status": grounding_status,
                "has_download": bool(doc.storage_path or doc.extracted_text),
            },
            source_refs=("tenant_documents",),
            metadata={
                "grounding_status": grounding_status,
                "certified_grounding": certified,
                "full_source_read": True,
                "math_verified": math_verified,
                "document_id": str(doc.id),
                "filename": doc.filename,
            },
        )


class GetDocumentSourceTool(StructuredDocumentAITool):
    name = "get_document_source"
    description = (
        "Lit la source intégrale non tronquée d'un document ou classeur Excel (tous les onglets visibles et financiers masqués, "
        "tableaux Word, pages PDF, formules et avertissements). À utiliser systématiquement lorsqu'un aperçu est incomplet."
    )
    input_schema = GetDocumentSourceArgs

    def __init__(self, session: Session) -> None:
        self._session = session
        self._auth = ContractAuthorizationService(session)

    async def run(self, context: ToolExecutionContext, arguments: GetDocumentSourceArgs) -> ToolResult:
        ok_ent, ent_err = self._ensure_document_module_entitlement(self._session, context.tenant)
        if not ok_ent:
            return ToolResult(success=False, error=ent_err)

        bundle, meta, err = _resolve_tenant_document_or_dataset_bundle(
            self._session, self._auth, context, arguments.document_id
        )
        if bundle is None or meta is None:
            return ToolResult(success=False, error=err or "Document introuvable")

        target_text = bundle.full_text
        selected_sheet: str | None = None
        if arguments.sheet_name:
            target_fold = arguments.sheet_name.strip().casefold()
            matched_sheet = next(
                (s for s in bundle.sheets if s.sheet_name.strip().casefold() == target_fold),
                None,
            )
            if matched_sheet is None:
                return ToolResult(
                    success=False,
                    error=(
                        f"Onglet ou section '{arguments.sheet_name}' introuvable dans '{bundle.file_name}'. "
                        f"Onglets disponibles : {[s.sheet_name for s in bundle.sheets]}."
                    ),
                )
            selected_sheet = matched_sheet.sheet_name
            target_text = matched_sheet.rendered_text

        sanitized = _sanitize_untrusted_text(target_text)
        total_chars = len(sanitized)
        window = sanitized[arguments.offset : arguments.offset + arguments.max_chars]
        has_more = (arguments.offset + arguments.max_chars) < total_chars

        wrapped = (
            f"<untrusted_document_data source_document_id=\"{meta['document_id']}\" filename=\"{meta['filename']}\">\n"
            f"{window}\n"
            f"</untrusted_document_data>"
        )

        grounding_status = (
            "uncertain_candidates"
            if bundle.extraction_mode == "pdf_scanned_unreadable" or bundle.has_uncached_formulas
            else "source_accessible"
        )
        certified = grounding_status == "source_accessible" and not has_more

        return ToolResult(
            success=True,
            data={
                **meta,
                "extraction_mode": bundle.extraction_mode,
                "selected_sheet": selected_sheet,
                "sheets": [s.to_summary_dict() for s in bundle.sheets],
                "has_uncached_formulas": bundle.has_uncached_formulas,
                "uncached_formula_refs": list(bundle.uncached_formula_refs),
                "warnings": list(bundle.warnings),
                "total_chars": total_chars,
                "offset": arguments.offset,
                "has_more": has_more,
                "next_offset": (arguments.offset + arguments.max_chars) if has_more else None,
                "full_source_read": not has_more,
                "grounding_status": grounding_status,
                "source_content": wrapped,
            },
            source_refs=(str(meta["source_ref"]),),
            metadata={
                "grounding_status": grounding_status,
                "certified_grounding": certified,
                "full_source_read": not has_more,
                "is_truncated_preview": has_more,
                "document_id": meta["document_id"],
                "filename": meta["filename"],
            },
        )


class ExtractInvoiceTotalsTool(StructuredDocumentAITool):
    name = "extract_invoice_totals"
    description = (
        "Extrait de façon déterministe en `Decimal` tous les montants, taxes (TPS/TVQ/GST/QST/HST), sous-total, "
        "remise, montant payé, solde dû, numéro de facture/PO, dates et coordonnées exactes d'onglet/cellule "
        "sur l'intégralité du document source, avec vérification mathématique certifiée."
    )
    input_schema = ExtractInvoiceTotalsArgs

    def __init__(self, session: Session) -> None:
        self._session = session
        self._auth = ContractAuthorizationService(session)
        self._extractor = InvoiceExtractionService()

    async def run(self, context: ToolExecutionContext, arguments: ExtractInvoiceTotalsArgs) -> ToolResult:
        ok_ent, ent_err = self._ensure_document_module_entitlement(self._session, context.tenant)
        if not ok_ent:
            return ToolResult(success=False, error=ent_err)

        bundle, meta, err = _resolve_tenant_document_or_dataset_bundle(
            self._session, self._auth, context, arguments.document_id
        )
        if bundle is None or meta is None:
            return ToolResult(success=False, error=err or "Document introuvable")

        report = self._extractor.extract_from_bundle(
            bundle,
            sheet_filter=arguments.sheet_name,
            invoice_filter=arguments.invoice_number,
        )
        compact = _compact_invoice_report_dict(report)

        provenance_summary: dict[str, Any] = {"file_name": bundle.file_name, "sheet_names": list(report.sheet_names)}
        if report.primary_invoice and report.primary_invoice.total_amount:
            tot = report.primary_invoice.total_amount
            provenance_summary.update(
                {
                    "sheet_name": tot.sheet_name,
                    "cell_ref": tot.cell_ref,
                    "coordinate": tot.coordinate,
                    "total_amount": tot.normalized_value,
                    "currency": report.primary_invoice.currency or tot.currency,
                    "verification_status": report.verification_status,
                }
            )

        return ToolResult(
            success=True,
            data={
                "document_id": meta["document_id"],
                "filename": meta["filename"],
                "source_kind": meta["source_kind"],
                **compact,
            },
            source_refs=(str(meta["source_ref"]),),
            metadata={
                "grounding_status": report.grounding_status,
                "certified_grounding": report.certified_grounding,
                "verification_status": report.verification_status,
                "math_verified": bool(report.primary_invoice and report.primary_invoice.math_verified),
                "full_source_read": report.full_source_read,
                "is_truncated_preview": False,
                "provenance": provenance_summary,
                "document_id": meta["document_id"],
                "filename": meta["filename"],
            },
        )


class GetDocumentCellEvidenceTool(StructuredDocumentAITool):
    name = "get_document_cell_evidence"
    description = (
        "Retourne la preuve exacte de provenance cellule par cellule (`file_name`, `sheet_name`, `cell_ref`, "
        "`raw_value`, `cached_value`, `normalized_value`, `formula`, `uncached_formula`, `merged_range`, "
        "`confidence`, `verification_status`) pour une coordonnée, une plage (`A12:F20`) ou un mot-clé."
    )
    input_schema = GetDocumentCellEvidenceArgs

    def __init__(self, session: Session) -> None:
        self._session = session
        self._auth = ContractAuthorizationService(session)

    async def run(self, context: ToolExecutionContext, arguments: GetDocumentCellEvidenceArgs) -> ToolResult:
        ok_ent, ent_err = self._ensure_document_module_entitlement(self._session, context.tenant)
        if not ok_ent:
            return ToolResult(success=False, error=ent_err)

        bundle, meta, err = _resolve_tenant_document_or_dataset_bundle(
            self._session, self._auth, context, arguments.document_id
        )
        if bundle is None or meta is None:
            return ToolResult(success=False, error=err or "Document introuvable")

        cells = list(bundle.cells)
        explicit_sheet = arguments.sheet_name.strip() if arguments.sheet_name else None

        parsed_range = _parse_cell_or_range(arguments.cell_ref) if arguments.cell_ref else None
        if parsed_range is not None:
            rng_sheet, r1, c1, r2, c2 = parsed_range
            eff_sheet = rng_sheet or explicit_sheet
            if eff_sheet:
                cells = [c for c in cells if (c.sheet_name or "").casefold() == eff_sheet.casefold()]
            cells = [
                c
                for c in cells
                if not (c.end_row < r1 or c.row > r2 or c.end_column < c1 or c.column > c2)
            ]
        else:
            if explicit_sheet:
                cells = [c for c in cells if (c.sheet_name or "").casefold() == explicit_sheet.casefold()]
            if arguments.cell_ref:
                needle_ref = arguments.cell_ref.strip().casefold()
                cells = [
                    c
                    for c in cells
                    if needle_ref in c.cell_ref.casefold() or needle_ref == c.coordinate.casefold()
                ]

        if arguments.search_term:
            term = arguments.search_term.strip().casefold()
            cells = [
                c
                for c in cells
                if term in str(c.raw_value or "").casefold()
                or term in str(c.normalized_value or "").casefold()
                or term in str(c.formula or "").casefold()
                or term in c.cell_ref.casefold()
            ]

        selected: list[CellProvenance] = cells[: arguments.limit]
        has_uncached = any(c.uncached_formula for c in selected)
        grounding_status = "uncertain_candidates" if has_uncached else "source_accessible"

        return ToolResult(
            success=True,
            data={
                "document_id": meta["document_id"],
                "filename": meta["filename"],
                "sheet_names": [s.sheet_name for s in bundle.sheets],
                "matched_count": len(cells),
                "returned_count": len(selected),
                "cells": [
                    {
                        **c.to_dict(),
                        "raw_value": _sanitize_untrusted_text(str(c.raw_value))
                        if isinstance(c.raw_value, str)
                        else c.to_dict()["raw_value"],
                        "normalized_value": _sanitize_untrusted_text(c.normalized_value)
                        if isinstance(c.normalized_value, str)
                        else c.normalized_value,
                    }
                    for c in selected
                ],
                "grounding_status": grounding_status,
            },
            source_refs=(str(meta["source_ref"]),),
            metadata={
                "grounding_status": grounding_status,
                "certified_grounding": not has_uncached and bool(selected),
                "full_source_read": True,
                "is_truncated_preview": False,
                "document_id": meta["document_id"],
                "filename": meta["filename"],
            },
        )


def _compact_invoice_report_dict(report: InvoiceExtractionReport) -> dict[str, Any]:
    """Sérialise un `InvoiceExtractionReport` sous les 8 000 caractères de `ToolExecutor`
    sans jamais tronquer les totaux, taxes, candidats ambigus ou références de cellules."""
    data = report.to_dict()
    if data.get("primary_invoice") and isinstance(data["primary_invoice"].get("line_items"), list):
        items = data["primary_invoice"]["line_items"]
        if len(items) > 25:
            data["primary_invoice"]["line_items_total_count"] = len(items)
            data["primary_invoice"]["line_items"] = items[:25]
    if isinstance(data.get("invoices"), list):
        if len(data["invoices"]) > 6:
            data["invoices_total_count"] = len(data["invoices"])
            data["invoices"] = data["invoices"][:6]
        for inv in data["invoices"]:
            if isinstance(inv.get("line_items"), list) and len(inv["line_items"]) > 15:
                inv["line_items_total_count"] = len(inv["line_items"])
                inv["line_items"] = inv["line_items"][:15]
    return data


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
        self._auth = ContractAuthorizationService(session)
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

        can_access, err = self._auth.can_access_document(context.tenant, doc, context.permissions)
        if not can_access:
            return ToolResult(
                success=False,
                error=err or "Document introuvable ou vous n'avez pas l'autorisation d'y accéder.",
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
# Outils Contrats (Company Contracts - Socle Plateforme Avenqo)
# ============================================================================


class SearchContractsTool(PlatformContractAITool):
    name = "search_contracts"
    description = (
        "Recherche parmi les contrats et accords légaux de l'entreprise (contrats de pilote, enterprise, NDA, etc.). "
        "Filtre par mot-clé, type de contrat ou statut."
    )
    input_schema = SearchContractsArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session
        self._auth = ContractAuthorizationService(session)

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
        query = query.order_by(CompanyContract.created_at.desc())

        all_records = list(self._session.scalars(query).all())
        records = self._auth.filter_accessible_contracts(context.tenant, all_records, context.permissions)[:limit]

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


class GetContractDetailTool(PlatformContractAITool):
    name = "get_contract_detail"
    description = (
        "Consulte le contenu textuel, les clauses, signataires et détails d'un contrat spécifique de l'entreprise. "
        "Le texte est protégé contre les injections et accompagné d'une mention juridique."
    )
    input_schema = GetContractDetailArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session
        self._auth = ContractAuthorizationService(session)

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

        can_access, err = self._auth.can_access_contract(context.tenant, contract, context.permissions)
        if not can_access:
            return ToolResult(
                success=False,
                error=err or "Contrat introuvable ou vous n'avez pas l'autorisation d'y accéder.",
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
            metadata={
                "grounding_status": "source_accessible",
                "certified_grounding": True,
                "full_source_read": True,
            },
        )


class GetContractDownloadUrlTool(PlatformContractAITool):
    name = "get_contract_download_url"
    description = (
        "Génère une URL de téléchargement PDF sécurisée et temporaire (15 minutes) pour un contrat spécifique de l'entreprise. "
        "Le jeton cryptographique garantit l'intégrité et l'étanchéité multi-tenant."
    )
    input_schema = GetContractDownloadUrlArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session
        self._auth = ContractAuthorizationService(session)
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

        can_access, err = self._auth.can_access_contract(context.tenant, contract, context.permissions)
        if not can_access:
            return ToolResult(
                success=False,
                error=err or "Contrat introuvable ou vous n'avez pas l'autorisation d'y accéder.",
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
# Outils Préexistants enrichis (OCR & Legal AI)
# ============================================================================


class GetOCRDocumentTool(OCRAITool):
    name = "get_ocr_document"
    description = (
        "Consulte les données complètes extraites d'une facture ou document traité par OCR AI. "
        "Analyse l'intégralité du document source (y compris tous les onglets Excel), renvoie la classification, "
        "l'extraction financière vérifiée en `Decimal` et la provenance exacte cellule/onglet."
    )
    input_schema = GetOCRDocumentArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session
        self._auth = ContractAuthorizationService(session)

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

        can_access, err = self._auth.can_access_document(context.tenant, doc, context.permissions)
        if not can_access:
            return ToolResult(success=False, error=err or "Permissions insuffisantes pour consulter ce document.")

        analysis: dict[str, Any] = {}
        try:
            analysis = json.loads(doc.analysis_json or "{}")
        except json.JSONDecodeError:
            analysis = {}

        service = DocumentAIService(self._session)
        inv_report = service.extract_structured_invoice(doc)
        compact_inv = _compact_invoice_report_dict(inv_report)

        return ToolResult(
            success=True,
            data={
                "document_id": str(doc.id),
                "filename": doc.filename,
                "classification": doc.classification,
                "byte_size": doc.byte_size,
                "analysis": analysis,
                "invoice_extraction": compact_inv,
                "full_source_read": inv_report.full_source_read,
                "grounding_status": inv_report.grounding_status,
                "extracted_text_snippet": _clean_summary_snippet(doc.extracted_text, 500),
            },
            source_refs=("tenant_documents",),
            metadata={
                "grounding_status": inv_report.grounding_status,
                "certified_grounding": inv_report.certified_grounding,
                "verification_status": inv_report.verification_status,
                "math_verified": bool(inv_report.primary_invoice and inv_report.primary_invoice.math_verified),
                "full_source_read": inv_report.full_source_read,
                "is_truncated_preview": False,
                "document_id": str(doc.id),
                "filename": doc.filename,
            },
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

        actor = self._session.query(User).filter(
            User.id == context.tenant.user_id,
            User.company_id == context.tenant.company_id,
        ).first()
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
        self._auth = ContractAuthorizationService(session)

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

        can_access, err = self._auth.can_access_document(context.tenant, doc, context.permissions)
        if not can_access:
            return ToolResult(success=False, error=err or "Permissions insuffisantes pour consulter ce document.")

        analysis: dict[str, Any] = {}
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
                "summary": _clean_summary_snippet(doc.extracted_text, 400),
                "is_truncated_preview": len(doc.extracted_text or "") > 400,
                "disclaimer": LEGAL_DISCLAIMER,
                "advisory_warning": "Cette analyse est informative et ne remplace pas l'avis d'un professionnel du droit.",
            },
            source_refs=("tenant_documents",),
            metadata={
                "grounding_status": "preview_only" if len(doc.extracted_text or "") > 400 else "source_accessible",
                "certified_grounding": len(doc.extracted_text or "") <= 400,
                "full_source_read": len(doc.extracted_text or "") <= 400,
                "is_truncated_preview": len(doc.extracted_text or "") > 400,
            },
        )
