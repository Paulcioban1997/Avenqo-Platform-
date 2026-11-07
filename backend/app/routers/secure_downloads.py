"""Routes de téléchargement sécurisé de documents avec validation de jetons signés et gardes stricts."""

from __future__ import annotations

import hashlib
import html
import logging
from io import BytesIO
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config.settings import get_settings
from backend.app.core.permissions import permissions_for
from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity
from backend.app.models.accounting import AccountingInvoice
from backend.app.models.base import CompanyStatus
from backend.app.models.company import Company
from backend.app.models.company_contract import CompanyContract, ContractLifecycleStatus
from backend.app.models.user import User
from backend.app.models.workspace import TenantDocument
from backend.app.services.contract_signature_service import ContractSignatureService
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.services.secure_document_token_service import (
    ExpiredSecureTokenError,
    InvalidSecureTokenError,
    SecureDocumentTokenService,
    UnauthorizedSecureTokenError,
    mask_token,
)
from shared.ai_engine.contracts import TenantContext

logger = logging.getLogger("avenqo.secure_downloads")

router = APIRouter(prefix="/secure-downloads", tags=["secure-downloads"])

# Statuts pour lesquels le contrat est juridiquement engagé ou signé
SIGNED_CONTRACT_STATUSES: frozenset[str] = frozenset({
    ContractLifecycleStatus.SIGNED.value,
    ContractLifecycleStatus.CUSTOMER_SIGNED.value,
    ContractLifecycleStatus.FULLY_EXECUTED.value,
    ContractLifecycleStatus.PROVIDER_SIGNING_REQUIRED.value,
})


def _escape_xml(val: object) -> str:
    """Échappe rigoureusement tout texte utilisateur avant interpolation ReportLab."""
    if val is None:
        return ""
    return html.escape(str(val))


def _resolve_canonical_artifact_path(base_root: str | Path, relative_storage_path: str) -> Path:
    """Résout et valide de façon canonique un chemin de stockage en empêchant tout path traversal.

    Garanties :
    1. Rejette les caractères nuls et chaînes vides.
    2. Rejette les chemins absolus et les préfixes de lecteurs Windows (ex: C:).
    3. Résout le chemin canonique réel (.resolve()) incluant les liens symboliques.
    4. Vérifie l'appartenance stricte à base_root.
    5. Confirme l'existence physique en tant que fichier régulier.
    """
    if not relative_storage_path or "\0" in relative_storage_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chemin de stockage corrompu ou invalide.",
        )

    rel_path = Path(relative_storage_path)
    if rel_path.is_absolute() or rel_path.drive:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Les chemins absolus sont strictement interdits.",
        )

    root = Path(base_root).resolve()
    candidate = (root / rel_path).resolve()

    # Vérification d'évasion de répertoire (is_relative_to)
    try:
        is_subpath = candidate.is_relative_to(root)
    except AttributeError:
        is_subpath = str(candidate).startswith(str(root))

    if not is_subpath:
        logger.warning(
            "security_path_traversal_blocked root=%s candidate=%s",
            root,
            candidate,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tentative d'évasion de stockage interdite.",
        )

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artefact documentaire introuvable sur le stockage.",
        )

    return candidate


def _generate_invoice_pdf(invoice: AccountingInvoice, company: Company | None) -> bytes:
    """Génère un récapitulatif PDF d'écriture comptable avec échappement strict des données."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        name="InvoiceTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0f172a"),
    )
    body_style = ParagraphStyle(
        name="InvoiceBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#334155"),
    )
    bold_style = ParagraphStyle(
        name="InvoiceBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#0f172a"),
    )

    company_name = company.name if company else "Avenqo Enterprise"
    status_label = invoice.status.upper()
    confirmation_label = "Confirmée au grand livre" if invoice.is_confirmed else "Écriture provisoire non confirmée"

    story = [
        Paragraph(f"RELEVÉ DE FACTURE {_escape_xml(invoice.invoice_number)}", title_style),
        Paragraph(f"Statut : {_escape_xml(status_label)} | Type : {_escape_xml(invoice.invoice_type.capitalize())}", body_style),
        Paragraph(f"État comptable : {_escape_xml(confirmation_label)}", body_style),
        Spacer(1, 16),
    ]

    header_data = [
        [Paragraph("ÉMETTEUR / ENTREPRISE", bold_style), Paragraph("TIERS / CLIENT OU FOURNISSEUR", bold_style)],
        [Paragraph(f"<b>{_escape_xml(company_name)}</b>", body_style), Paragraph(f"<b>{_escape_xml(invoice.party_name)}</b>", body_style)],
        [
            Paragraph(f"Date d'émission : {_escape_xml(invoice.issue_date.strftime('%Y-%m-%d') if invoice.issue_date else 'N/A')}", body_style),
            Paragraph(f"Date d'échéance : {_escape_xml(invoice.due_date.strftime('%Y-%m-%d') if invoice.due_date else 'N/A')}", body_style),
        ],
    ]
    header_table = Table(header_data, colWidths=[270, 270])
    header_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    story.append(header_table)
    story.append(Spacer(1, 24))

    notes_text = invoice.notes or "Prestation commerciale"
    table_data = [
        [
            Paragraph("Description", bold_style),
            Paragraph("Total", bold_style),
            Paragraph("Payé", bold_style),
            Paragraph("Solde Restant", bold_style),
        ],
        [
            Paragraph(f"Facture référence {_escape_xml(invoice.invoice_number)} ({_escape_xml(notes_text)})", body_style),
            Paragraph(f"{invoice.total_amount:,.2f} {_escape_xml(invoice.currency)}", body_style),
            Paragraph(f"{invoice.paid_amount:,.2f} {_escape_xml(invoice.currency)}", body_style),
            Paragraph(f"<b>{invoice.remaining_amount:,.2f} {_escape_xml(invoice.currency)}</b>", bold_style),
        ],
    ]
    amount_table = Table(table_data, colWidths=[240, 100, 100, 100])
    amount_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ])
    )
    story.append(amount_table)
    story.append(Spacer(1, 30))
    story.append(
        Paragraph(
            "Relevé récapitulatif généré par Avenqo à partir des écritures comptables enregistrées.",
            ParagraphStyle(name="Disclaimer", parent=styles["Italic"], fontSize=8, textColor=colors.HexColor("#64748b")),
        )
    )

    doc.build(story)
    return buffer.getvalue()


def _generate_document_pdf(doc_record: TenantDocument) -> bytes:
    """Génère un PDF textuel propre si l'artefact original n'est pas directement présent en binaire."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()

    story = [
        Paragraph(f"Document : {_escape_xml(doc_record.filename)}", styles["Heading1"]),
        Paragraph(
            f"Classification : {_escape_xml(doc_record.classification or 'Général')} | Type : {_escape_xml(doc_record.kind.upper())}",
            styles["Normal"],
        ),
        Spacer(1, 14),
        Paragraph("<b>Extrait du texte analysé :</b>", styles["Heading3"]),
        Spacer(1, 8),
    ]

    for paragraph in (doc_record.extracted_text or "Aucun texte extrait.").split("\n\n"):
        clean = paragraph.strip()
        if clean:
            story.append(Paragraph(_escape_xml(clean).replace("\n", "<br/>"), styles["Normal"]))
            story.append(Spacer(1, 6))

    doc.build(story)
    return buffer.getvalue()


@router.get("/{token}")
def secure_download(
    token: str,
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> Response:
    """Téléchargement sécurisé réévaluant dynamiquement l'identité, les droits RBAC et les entitlements."""
    token_service = SecureDocumentTokenService()
    try:
        verified = token_service.verify_download_token(
            token,
            current_company_id=identity.user.company_id,
            current_user_id=identity.user.id,
            mark_as_used=True,
        )
    except ExpiredSecureTokenError as exc:
        logger.info("download_rejected_expired token=%s", mask_token(token))
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Le lien de téléchargement a expiré. Veuillez redemander le document à Central AI.",
        ) from exc
    except UnauthorizedSecureTokenError as exc:
        logger.warning(
            "download_rejected_unauthorized user=%s company=%s token=%s",
            identity.user.id,
            identity.user.company_id,
            mask_token(token),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès interdit : ce lien appartient à une autre session ou entreprise.",
        ) from exc
    except InvalidSecureTokenError as exc:
        logger.warning("download_rejected_invalid token=%s error=%s", mask_token(token), exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # 1. Revalidation de l'état actuel de l'utilisateur (révocation / désactivation)
    current_user = db.get(User, identity.user.id)
    if not current_user or not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Votre compte utilisateur a été désactivé ou révoqué.",
        )
    if current_user.company_id != identity.user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès interdit : votre rattachement d'entreprise a changé.",
        )

    # 2. Revalidation dynamique des permissions RBAC actuelles
    perms = permissions_for(current_user.role)
    if "data:read" not in perms:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissions insuffisantes pour télécharger ce document.",
        )

    # 3. Revalidation de l'entreprise
    company = db.get(Company, identity.user.company_id)
    if not company or company.status != CompanyStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="L'entreprise associée est inactive ou suspendue.",
        )

    # 4. Revalidation dynamique des modules / entitlements
    entitlement_service = ModuleEntitlementService(db)
    active_modules = set(entitlement_service.get_active_modules(TenantContext(identity.user.company_id)))

    doc_id: UUID = verified["doc_id"]
    doc_type: str = verified["doc_type"]
    filename: str = verified["filename"]
    settings = get_settings()

    # =========================================================================
    # 1. CONTRATS
    # =========================================================================
    if doc_type == "contract":
        # Vérification d'entitlement : module legal requis (ou plan Enterprise/Professional)
        if "legal" not in active_modules and (company.subscription_plan or "").lower() not in {"enterprise", "professional"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Le module Juridique / Contrats n'est pas activé pour votre compte.",
            )

        contract = db.scalar(
            select(CompanyContract).where(
                CompanyContract.id == doc_id,
                CompanyContract.company_id == identity.user.company_id,
            )
        )
        if contract is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contrat introuvable pour cette entreprise.",
            )

        is_signed = contract.status in SIGNED_CONTRACT_STATUSES

        # RÈGLE D'INTÉGRITÉ STRICTE : Si le contrat est signé, INTERDICTION de substituer un brouillon
        if is_signed:
            if not contract.storage_path:
                logger.error(
                    "signed_contract_missing_storage_path contract_id=%s company_id=%s",
                    contract.id,
                    contract.company_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="L'artefact contractuel original signé est introuvable sur le stockage sécurisé.",
                )

            safe_path = _resolve_canonical_artifact_path(settings.artifact_root, contract.storage_path)
            content_bytes = safe_path.read_bytes()

            # Vérification d'intégrité SHA256 si présente
            expected_hash = contract.pdf_sha256 or contract.sha256_hash
            if expected_hash:
                actual_hash = hashlib.sha256(content_bytes).hexdigest()
                if actual_hash.lower() != expected_hash.lower():
                    logger.error(
                        "contract_sha256_mismatch contract_id=%s expected=%s actual=%s",
                        contract.id,
                        expected_hash,
                        actual_hash,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Échec de vérification d'intégrité de l'artefact contractuel original.",
                    )

            return Response(
                content=content_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'inline; filename="{filename}"'},
            )

        # Contrat non signé (brouillon / en attente)
        if contract.storage_path:
            try:
                safe_path = _resolve_canonical_artifact_path(settings.artifact_root, contract.storage_path)
                return Response(
                    content=safe_path.read_bytes(),
                    media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{filename}"'},
                )
            except HTTPException:
                pass  # Fallback autorisé uniquement pour un brouillon non signé

        contract_service = ContractSignatureService(db)
        draft_pdf_bytes = contract_service.generate_draft_pdf(company, contract.contract_type)
        draft_filename = filename if filename.startswith("brouillon_") else f"brouillon_{filename}"
        return Response(
            content=draft_pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{draft_filename}"'},
        )

    # =========================================================================
    # 2. FACTURES COMPTABLES
    # =========================================================================
    if doc_type == "invoice":
        if "accounting" not in active_modules:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Le module Comptabilité n'est pas actif pour votre entreprise.",
            )

        invoice = db.scalar(
            select(AccountingInvoice).where(
                AccountingInvoice.id == doc_id,
                AccountingInvoice.company_id == identity.user.company_id,
            )
        )
        if invoice is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Facture introuvable pour cette entreprise.",
            )

        pdf_bytes = _generate_invoice_pdf(invoice, company)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )

    # =========================================================================
    # 3. DOCUMENTS OCR & FICHIERS INTERNES
    # =========================================================================
    if doc_type in {"document", "ocr", "legal"}:
        required_mod = "legal" if doc_type == "legal" else "ocr"
        if required_mod not in active_modules:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Le module '{required_mod.upper()}' n'est pas activé pour votre entreprise.",
            )

        doc_record = db.scalar(
            select(TenantDocument).where(
                TenantDocument.id == doc_id,
                TenantDocument.company_id == identity.user.company_id,
            )
        )
        if doc_record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document introuvable pour cette entreprise.",
            )

        if doc_record.storage_path:
            safe_path = _resolve_canonical_artifact_path(settings.artifact_root, doc_record.storage_path)
            return Response(
                content=safe_path.read_bytes(),
                media_type=doc_record.content_type or "application/pdf",
                headers={"Content-Disposition": f'inline; filename="{filename}"'},
            )

        pdf_bytes = _generate_document_pdf(doc_record)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Type de document non pris en charge.")
