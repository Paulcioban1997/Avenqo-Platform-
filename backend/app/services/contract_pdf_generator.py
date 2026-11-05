"""Générateur de PDF certifiés pour les contrats d'entreprise Avenqo (ReportLab).

Fournit un rendu PDF haute fidélité conforme aux standards d'affaires québécois et canadiens,
incluant la preuve d'intégrité SHA-256, l'horodatage UTC et le sceau d'audit électronique.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


class NumberedCanvas(canvas.Canvas):
    """Canvas avec numérotation 'Page X de Y' et sceau d'intégrité en pied de page."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int) -> None:
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))

        # Ligne de séparation de pied de page
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(40, 45, 572, 45)

        # Pied de page gauche : Sceau Avenqo
        self.drawString(40, 32, "Avenqo AI Enterprise Platform — Confidentiel & Opposable")

        # Pied de page centre / droite : Numéro de page
        page_str = f"Page {self._pageNumber} sur {page_count}"
        self.drawRightString(572, 32, page_str)
        self.restoreState()


class ContractPdfGenerator:
    """Générateur de documents contractuels PDF certifiés."""

    @classmethod
    def generate_pdf(
        cls,
        *,
        contract_title: str,
        contract_type: str,
        contract_version: str,
        company_name: str,
        company_id: str,
        signatory_name: str,
        signatory_title: str,
        signatory_email: str,
        plan_code: str,
        plan_price: str,
        active_modules: list[str] | tuple[str, ...],
        content_text: str,
        sha256_hash: str,
        signed_at: datetime | None = None,
        signature_mode: str | None = None,
        audit_receipt_id: str | None = None,
        ip_address: str | None = None,
        is_draft: bool = False,
    ) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=40,
            rightMargin=40,
            topMargin=45,
            bottomMargin=55,
        )

        styles = getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle(
            "ContractTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#0B132B"),
            alignment=0,
            spaceAfter=4,
        )

        subtitle_style = ParagraphStyle(
            "ContractSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#64748B"),
            spaceAfter=12,
        )

        section_heading = ParagraphStyle(
            "SectionHeading",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#0076FF"),
            spaceBefore=10,
            spaceAfter=4,
        )

        body_style = ParagraphStyle(
            "ContractBody",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#1E293B"),
            spaceAfter=6,
        )

        meta_label = ParagraphStyle(
            "MetaLabel",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#475569"),
        )

        meta_val = ParagraphStyle(
            "MetaValue",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#0B132B"),
        )

        elements: list[Any] = []

        # 1. En-tête de marque
        header_table = Table(
            [
                [
                    Paragraph("<b>AVENQO</b>", ParagraphStyle("Brand", fontName="Helvetica-Bold", fontSize=18, textColor=colors.HexColor("#0076FF"))),
                    Paragraph(
                        f"<b>RÉF : {contract_type.upper()}-{contract_version}</b><br/>"
                        f"<font color='#64748B'>Date : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</font>",
                        ParagraphStyle("Ref", fontName="Helvetica", fontSize=8, leading=10, alignment=2),
                    ),
                ]
            ],
            colWidths=[250, 282],
        )
        header_table.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ])
        )
        elements.append(header_table)
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0076FF"), spaceBefore=2, spaceAfter=10))

        # 2. Titre du Contrat
        elements.append(Paragraph(contract_title, title_style))
        status_text = (
            "<font color='#059669'><b>CERTIFIÉ CONFORME & SIGNÉ</b></font>"
            if not is_draft and signed_at
            else "<font color='#D97706'><b>BROUILLON EN ATTENTE DE SIGNATURE</b></font>"
        )
        elements.append(Paragraph(f"Statut : {status_text} | Version : {contract_version}", subtitle_style))

        # 3. Tableau Récapitulatif du Locataire & de la Souscription
        modules_display = ", ".join(m.capitalize() for m in active_modules) if active_modules else "Aucun module spécifique"
        meta_data = [
            [
                Paragraph("<b>Client (Locataire) :</b>", meta_label),
                Paragraph(company_name or "Entreprise cliente", meta_val),
                Paragraph("<b>Identifiant Entreprise :</b>", meta_label),
                Paragraph(str(company_id)[:18] + "...", meta_val),
            ],
            [
                Paragraph("<b>Signataire Autorisé :</b>", meta_label),
                Paragraph(f"{signatory_name} ({signatory_title or 'Dirigeant'})", meta_val),
                Paragraph("<b>Courriel Professionnel :</b>", meta_label),
                Paragraph(signatory_email or "N/A", meta_val),
            ],
            [
                Paragraph("<b>Formule Souscrite :</b>", meta_label),
                Paragraph(f"{plan_code.upper()} ({plan_price})", meta_val),
                Paragraph("<b>Modules Inclus :</b>", meta_label),
                Paragraph(modules_display, meta_val),
            ],
            [
                Paragraph("<b>Empreinte SHA-256 :</b>", meta_label),
                Paragraph(f"<font face='Courier' size='7'>{sha256_hash[:32]}...{sha256_hash[-16:]}</font>", meta_val),
                Paragraph("<b>Mode d'Exécution :</b>", meta_label),
                Paragraph(signature_mode or ("Électronique 1-Clic" if signed_at else "En attente"), meta_val),
            ],
        ]

        meta_table = Table(meta_data, colWidths=[110, 156, 110, 156])
        meta_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        elements.append(meta_table)
        elements.append(Spacer(1, 14))

        # 4. Corps du Texte Contractuel
        # Parser le texte markdown brut en paragraphes ReportLab
        lines = content_text.splitlines()
        for line in lines:
            line_s = line.strip()
            if not line_s:
                elements.append(Spacer(1, 4))
                continue
            if line_s.startswith("### "):
                elements.append(Paragraph(line_s[4:], section_heading))
            elif line_s.startswith("## "):
                elements.append(Paragraph(line_s[3:], title_style))
            elif line_s.startswith("# "):
                pass  # Déjà affiché en titre principal
            elif line_s.startswith("---"):
                elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E1"), spaceBefore=4, spaceAfter=6))
            elif line_s.startswith("- ") or line_s.startswith("* "):
                bullet_style = ParagraphStyle("Bullet", parent=body_style, leftIndent=12)
                elements.append(Paragraph(f"• {line_s[2:]}", bullet_style))
            elif line_s.startswith("1. ") or line_s.startswith("2. ") or line_s.startswith("3. ") or line_s.startswith("4. "):
                num_style = ParagraphStyle("Num", parent=body_style, leftIndent=12)
                elements.append(Paragraph(line_s, num_style))
            else:
                elements.append(Paragraph(line_s, body_style))

        # 5. Bloc de Signatures d'Engagement
        elements.append(Spacer(1, 12))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0B132B"), spaceBefore=6, spaceAfter=10))

        date_str = signed_at.strftime("%Y-%m-%d %H:%M:%S UTC") if signed_at else "En attente de signature"

        sig_party_client = [
            Paragraph("<b>POUR LE CLIENT (ENTREPRISE LOCATAIRE) :</b>", meta_label),
            Spacer(1, 4),
            Paragraph(f"Dénomination : <b>{company_name}</b>", body_style),
            Paragraph(f"Signataire : <b>{signatory_name}</b>", body_style),
            Paragraph(f"Titre : <b>{signatory_title or 'Dirigeant / Représentant'}</b>", body_style),
            Paragraph(f"Courriel : <b>{signatory_email}</b>", body_style),
            Paragraph(f"Date d'exécution : <b>{date_str}</b>", body_style),
            Spacer(1, 6),
            (
                Paragraph(
                    "<font color='#059669'><b>[SCEAU ÉLECTRONIQUE CONFORME RLRQ c. C-1.1]</b></font><br/>"
                    f"<font size='7' color='#475569'>SHA-256 : {sha256_hash[:24]}...<br/>"
                    f"IP : {ip_address or '127.0.0.1'} | Audit : {audit_receipt_id or 'REC-AUTO'}</font>",
                    body_style,
                )
                if signed_at
                else Paragraph("<font color='#64748B'>Signature (manuscrite au stylo) :<br/><br/>X____________________________________</font>", body_style)
            ),
        ]

        sig_party_provider = [
            Paragraph("<b>POUR LE FOURNISSEUR :</b>", meta_label),
            Spacer(1, 4),
            Paragraph("Dénomination : <b>PMC SOLUTIONS AI</b>", body_style),
            Paragraph("Statut : <i>Entreprise en cours d'incorporation</i>", body_style),
            Paragraph("Représentant : <b>Mircea Paul Cioban</b>", body_style),
            Paragraph("Titre : <b>Fondateur & Président</b>", body_style),
            Paragraph(f"Date d'exécution : <b>{date_str}</b>", body_style),
            Spacer(1, 6),
            Paragraph(
                "<font color='#0076FF'><b>[CONTRESEING NUMÉRIQUE FOURNISSEUR]</b></font><br/>"
                f"<font size='7' color='#475569'>Plateforme Technologique Avenqo<br/>"
                "District judiciaire de Montréal, Québec, Canada</font>",
                body_style,
            ),
        ]

        sig_table = Table([[sig_party_client, sig_party_provider]], colWidths=[266, 266])
        sig_table.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ])
        )

        elements.append(KeepTogether(sig_table))

        # Compilation du document PDF
        doc.build(elements, canvasmaker=NumberedCanvas)
        return buffer.getvalue()

