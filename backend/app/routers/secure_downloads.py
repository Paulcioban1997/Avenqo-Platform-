"""Routes de téléchargement sécurisé de documents avec validation de jetons signés."""

from __future__ import annotations

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
from backend.app.models.company import Company
from backend.app.models.company_contract import CompanyContract, ContractLifecycleStatus
from backend.app.models.workspace import TenantDocument
from backend.app.services.contract_signature_service import ContractSignatureService
from backend.app.services.secure_document_token_service import (
    ExpiredSecureTokenError,
    InvalidSecureTokenError,
    SecureDocumentTokenService,
    UnauthorizedSecureTokenError,
)

logger = logging.getLogger("avenqo.secure_downloads")

router = APIRouter(prefix="/secure-downloads", tags=["secure-downloads"])


def _generate_invoice_pdf(invoice: AccountingInvoice, company: Company | None) -> bytes:
    """Génère un PDF professionnel pour une facture comptable."""
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

    story = [
        Paragraph(f"FACTURE {invoice.invoice_number}", title_style),
        Paragraph(f"Statut : {invoice.status.upper()} | Type : {invoice.invoice_type.capitalize()}", body_style),
        Spacer(1, 16),
    ]

    company_name = company.name if company else "Avenqo Enterprise"
    header_data = [
        [Paragraph("ÉMETTEUR / ENTREPRISE", bold_style), Paragraph("TIERS / CLIENT OU FOURNISSEUR", bold_style)],
        [Paragraph(f"<b>{company_name}</b>", body_style), Paragraph(f"<b>{invoice.party_name}</b>", body_style)],
        [
            Paragraph(f"Date d'émission : {invoice.issue_date.strftime('%Y-%m-%d') if invoice.issue_date else 'N/A'}", body_style),
            Paragraph(f"Date d'échéance : {invoice.due_date.strftime('%Y-%m-%d') if invoice.due_date else 'N/A'}", body_style),
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

    table_data = [
        [
            Paragraph("Description", bold_style),
            Paragraph("Total", bold_style),
            Paragraph("Payé", bold_style),
            Paragraph("Solde Restant", bold_style),
        ],
        [
            Paragraph(f"Facture référence {invoice.invoice_number} ({invoice.notes or 'Prestation commerciale'})", body_style),
            Paragraph(f"{invoice.total_amount:,.2f} {invoice.currency}", body_style),
            Paragraph(f"{invoice.paid_amount:,.2f} {invoice.currency}", body_style),
            Paragraph(f"<b>{invoice.remaining_amount:,.2f} {invoice.currency}</b>", bold_style),
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
            "Document généré sous environnement sécurisé certifié Avenqo Central AI. Copie officielle conforme.",
            ParagraphStyle(name="Disclaimer", parent=styles["Italic"], fontSize=8, textColor=colors.HexColor("#64748b")),
        )
    )

    doc.build(story)
    return buffer.getvalue()


def _generate_document_pdf(doc_record: TenantDocument) -> bytes:
    """Génère un PDF textuel propre si l'artefact original n'est pas directement présent en binaire."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()

    story = [
        Paragraph(f"Document : {doc_record.filename}", styles["Heading1"]),
        Paragraph(f"Classification : {doc_record.classification or 'Général'} | Type : {doc_record.kind.upper()}", styles["Normal"]),
        Spacer(1, 14),
        Paragraph("<b>Extrait du texte analysé :</b>", styles["Heading3"]),
        Spacer(1, 8),
    ]

    for paragraph in (doc_record.extracted_text or "Aucun texte extrait.").split("\n\n"):
        clean = paragraph.strip().replace("\n", "<br/>")
        if clean:
            story.append(Paragraph(clean, styles["Normal"]))
            story.append(Spacer(1, 6))

    doc.build(story)
    return buffer.getvalue()


@router.get("/{token}")
def secure_download(
    token: str,
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> Response:
    """Téléchargement sécurisé à expiration courte vérifiant l'identité et le tenant."""
    token_service = SecureDocumentTokenService()
    try:
        verified = token_service.verify_download_token(
            token,
            current_company_id=identity.user.company_id,
            current_user_id=identity.user.id,
        )
    except ExpiredSecureTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Le lien de téléchargement a expiré. Veuillez redemander le document à Central AI.",
        ) from exc
    except UnauthorizedSecureTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès interdit : ce lien appartient à une autre session ou entreprise.",
        ) from exc
    except InvalidSecureTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Jeton de téléchargement invalide ou corrompu.",
        ) from exc

    # Contrôle de permission utilisateur RBAC
    perms = permissions_for(identity.user.role)
    if "data:read" not in perms:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissions insuffisantes pour télécharger ce document.",
        )

    doc_id: UUID = verified["doc_id"]
    doc_type: str = verified["doc_type"]
    filename: str = verified["filename"]
    settings = get_settings()

    # 1. Contrats
    if doc_type == "contract":
        contract = db.scalar(
            select(CompanyContract).where(
                CompanyContract.id == doc_id,
                CompanyContract.company_id == identity.user.company_id,
            )
        )
        if contract is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contrat introuvable pour cette entreprise")

        contract_service = ContractSignatureService(db)
        company = db.get(Company, identity.user.company_id)

        # Si le contrat a un fichier persistant
        if contract.storage_path:
            full_path = Path(settings.artifact_root) / contract.storage_path
            if full_path.exists():
                pdf_bytes = full_path.read_bytes()
                return Response(
                    content=pdf_bytes,
                    media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{filename}"'},
                )

        # Sinon générer le PDF contractuel brouillon / modèle
        if company:
            pdf_bytes = contract_service.generate_draft_pdf(company, contract.contract_type)
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'inline; filename="{filename}"'},
            )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contrat non disponible en téléchargement")

    # 2. Factures comptables
    if doc_type == "invoice":
        invoice = db.scalar(
            select(AccountingInvoice).where(
                AccountingInvoice.id == doc_id,
                AccountingInvoice.company_id == identity.user.company_id,
            )
        )
        if invoice is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Facture introuvable pour cette entreprise")

        company = db.get(Company, identity.user.company_id)
        pdf_bytes = _generate_invoice_pdf(invoice, company)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )

    # 3. Documents OCR & Fichiers internes
    if doc_type in {"document", "ocr", "legal"}:
        doc_record = db.scalar(
            select(TenantDocument).where(
                TenantDocument.id == doc_id,
                TenantDocument.company_id == identity.user.company_id,
            )
        )
        if doc_record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document introuvable pour cette entreprise")

        if doc_record.storage_path:
            full_path = Path(settings.artifact_root) / doc_record.storage_path
            if full_path.exists():
                return Response(
                    content=full_path.read_bytes(),
                    media_type=doc_record.content_type or "application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{filename}"'},
                )

        # Rendu PDF sur la base du texte extrait
        pdf_bytes = _generate_document_pdf(doc_record)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Type de document non pris en charge")
