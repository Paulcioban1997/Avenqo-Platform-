"""Deterministic tenant invoice queries and accountant-ready exports."""

from __future__ import annotations

import csv
from datetime import datetime, timezone, timedelta
from io import BytesIO, StringIO
from uuid import UUID, uuid4

from openpyxl import Workbook
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import BillingInvoice, Company
from backend.app.config.settings import get_settings


class InvoiceNotFoundError(LookupError):
    pass


class InvoiceExportFormatError(ValueError):
    pass


class InvoiceFiscalService:
    """Provides trusted Stripe-derived values without LLM calculation."""

    EXPORT_COLUMNS = (
        "invoice_number",
        "invoice_date",
        "period_start",
        "period_end",
        "plan_product",
        "subtotal",
        "discounts",
        "tax",
        "total",
        "amount_paid",
        "amount_due",
        "currency",
        "payment_status",
        "stripe_reference",
    )

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_company_invoices(
        self,
        company_id: UUID,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        fiscal_year: int | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[BillingInvoice], int]:
        filters = self._filters(company_id, start=start, end=end, fiscal_year=fiscal_year)
        total = self._session.scalar(
            select(func.count()).select_from(BillingInvoice).where(*filters)
        ) or 0
        invoices = list(
            self._session.scalars(
                select(BillingInvoice)
                .where(*filters)
                .order_by(BillingInvoice.issued_at.desc())
                .offset(max(offset, 0))
                .limit(min(max(limit, 1), 200))
            )
        )
        return invoices, int(total)

    def get_invoice(self, company_id: UUID, invoice_id: UUID) -> BillingInvoice:
        invoice = self._session.scalar(
            select(BillingInvoice).where(
                BillingInvoice.id == invoice_id,
                BillingInvoice.company_id == company_id,
            )
        )
        if invoice is None:
            raise InvoiceNotFoundError("Invoice not found")
        return invoice

    def get_paid_subscription_totals(self, company_id: UUID, fiscal_year: int) -> dict:
        invoices = self._all_company_invoices(company_id, fiscal_year=fiscal_year)
        paid = [invoice for invoice in invoices if invoice.status == "paid"]
        totals_by_currency: dict[str, dict[str, int | str]] = {}
        for invoice in paid:
            currency = invoice.currency.upper()
            totals = totals_by_currency.setdefault(
                currency,
                {
                    "currency": currency,
                    "subscription_expense": 0,
                    "taxes_paid": 0,
                    "total_paid": 0,
                },
            )
            totals["subscription_expense"] += invoice.subtotal
            totals["taxes_paid"] += invoice.tax_total
            totals["total_paid"] += invoice.amount_paid
        return {
            "fiscal_year": fiscal_year,
            "invoices_paid": len(paid),
            "totals_by_currency": list(totals_by_currency.values()),
            "missing_or_unpaid_invoices": len(invoices) - len(paid),
        }

    def get_tax_totals(self, company_id: UUID, fiscal_year: int) -> dict[str, int]:
        invoices = self._all_company_invoices(company_id, fiscal_year=fiscal_year)
        totals: dict[str, int] = {}
        for invoice in invoices:
            if invoice.status == "paid":
                currency = invoice.currency.upper()
                totals[currency] = totals.get(currency, 0) + invoice.tax_total
        return totals

    def get_billing_currency(self, company_id: UUID) -> list[str]:
        return list(
            self._session.scalars(
                select(BillingInvoice.currency)
                .where(BillingInvoice.company_id == company_id)
                .distinct()
                .order_by(BillingInvoice.currency)
            )
        )

    def get_invoice_export(
        self,
        company_id: UUID,
        export_format: str,
        *,
        invoice_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        fiscal_year: int | None = None,
    ) -> tuple[bytes, str, str]:
        if invoice_id is not None:
            invoices = [self.get_invoice(company_id, invoice_id)]
        else:
            invoices = self._all_company_invoices(
                company_id,
                start=start,
                end=end,
                fiscal_year=fiscal_year,
            )
        rows = [self._export_row(invoice) for invoice in invoices]
        suffix = f"-{fiscal_year}" if fiscal_year else ""
        if export_format == "csv":
            output = StringIO(newline="")
            writer = csv.DictWriter(output, fieldnames=self.EXPORT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
            return output.getvalue().encode("utf-8-sig"), "text/csv", f"avenqo-invoices{suffix}.csv"
        if export_format == "xlsx":
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Invoices"
            sheet.append(self.EXPORT_COLUMNS)
            for row in rows:
                sheet.append([row[column] for column in self.EXPORT_COLUMNS])
            output = BytesIO()
            workbook.save(output)
            return (
                output.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                f"avenqo-invoices{suffix}.xlsx",
            )
        if export_format == "pdf":
            if invoice_id is not None and invoices:
                return self.generate_invoice_pdf(invoices[0])
            company = self._session.get(Company, company_id)
            return self.generate_invoices_summary_pdf(invoices, company)
        raise InvoiceExportFormatError("Supported invoice exports are CSV, XLSX and PDF")

    def generate_invoice_pdf(
        self,
        invoice: BillingInvoice,
        company: Company | None = None,
    ) -> tuple[bytes, str, str]:
        """Render every persisted charge; never calculate prices with an LLM."""
        from decimal import Decimal
        from xml.sax.saxutils import escape
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

        company = company or self._session.get(Company, invoice.company_id)
        number = invoice.number or f"AVQ-{str(invoice.id)[:8].upper()}"
        currency = (invoice.currency or "CAD").upper()
        settings = get_settings()
        output = BytesIO()
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name="InvoiceBody", fontName="Helvetica", fontSize=10,
                                  leading=15, textColor=colors.HexColor("#23324D")))
        styles.add(ParagraphStyle(name="InvoiceSmall", parent=styles["InvoiceBody"], fontSize=8, leading=12))
        styles.add(ParagraphStyle(name="InvoiceTitle", parent=styles["InvoiceBody"], fontSize=25, leading=32))
        body = styles["InvoiceBody"]
        small = styles["InvoiceSmall"]
        def paragraph(value, style=body):
            return Paragraph(escape(str(value or "")), style)
        def money(cents):
            amount = Decimal(int(cents or 0)) / Decimal(100)
            return f"{amount:,.2f}".replace(",", " ").replace(".", ",") + f" {currency}"
        def date(value):
            return value.strftime("%Y-%m-%d") if value else "Non renseignée"
        status = {"paid": "PAYÉE", "open": "À PAYER", "draft": "BROUILLON",
                  "void": "ANNULÉE", "uncollectible": "IRRÉCOUVRABLE"}.get(invoice.status, invoice.status)
        # Stripe amount_due is the original payable amount, not the outstanding balance.
        remaining = 0 if invoice.status in {"paid", "void"} else max(
            int(invoice.amount_due or 0) - int(invoice.amount_paid or 0), 0)
        story = [paragraph(f"Facture {number}", styles["InvoiceTitle"]),
                 paragraph(f"{status} | Émise le {date(invoice.issued_at)}"), Spacer(1, 16)]
        if settings.stripe_secret_key and settings.stripe_secret_key.startswith("sk_test_"):
            story += [paragraph("ENVIRONNEMENT TEST - Aucun débit réel", small), Spacer(1, 10)]
        issuer = [settings.billing_legal_business_name or "Avenqo",
                  settings.billing_business_address or "", settings.billing_support_email or "", "avenqo.ca"]
        details = invoice.billing_details or {}
        customer = [details.get("name") or (company.name if company else "Client Avenqo"), invoice.customer_email or ""]
        address = details.get("address") or {}
        customer += [str(address.get(k) or "") for k in ("line1", "line2", "city", "state", "postal_code", "country")]
        addresses = Table([[paragraph("ÉMETTEUR"), paragraph("FACTURÉ À")],
                           [paragraph(" | ".join(filter(None, issuer))), paragraph(" | ".join(filter(None, customer)))]],
                          colWidths=[256, 256], hAlign="LEFT")
        addresses.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"),
                                        ("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 18)]))
        story += [addresses, Spacer(1, 20)]
        if invoice.plan_code:
            plan_name = {"base": "Base", "demo": "Base", "professional": "Professional", "enterprise": "Enterprise"}.get(invoice.plan_code, invoice.plan_code)
            story += [paragraph(f"Forfait enregistré : {plan_name}", small), Spacer(1, 8)]
        if invoice.period_start and invoice.period_end:
            story += [paragraph(f"Période : {date(invoice.period_start)} au {date(invoice.period_end)}", small), Spacer(1, 10)]
        rows = [[paragraph("SERVICE / SUPPLÉMENT"), paragraph("QTÉ"), paragraph("MONTANT")]]
        for item in invoice.line_items or []:
            description = item.get("description") or "Service Avenqo"
            if invoice.plan_code in {"base", "demo"} and "Avenqo - Demo" in description:
                description = "Abonnement Avenqo Base · Mensuel"
            rows.append([paragraph(description),
                         paragraph(item.get("quantity") if item.get("quantity") is not None else "-"),
                         paragraph(money(item.get("amount")))])
        if len(rows) == 1:
            rows.append([paragraph(f"Abonnement Avenqo - {invoice.plan_code or 'Service'}"), paragraph("1"), paragraph(money(invoice.subtotal))])
        table = Table(rows, colWidths=[352, 40, 120], repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#EAF3FF")),
                                  ("VALIGN",(0,0),(-1,-1),"TOP"), ("TOPPADDING",(0,0),(-1,-1),10),
                                  ("BOTTOMPADDING",(0,0),(-1,-1),10),
                                  ("LINEBELOW",(0,0),(-1,-1),0.4,colors.HexColor("#DCE5F1"))]))
        story += [table, Spacer(1, 18)]
        totals = [("Sous-total", invoice.subtotal), ("Réductions", -(invoice.discount_total or 0)),
                  ("Taxes enregistrées", invoice.tax_total), ("Total", invoice.total),
                  ("Montant payé", invoice.amount_paid), ("Solde à payer", remaining)]
        total_table = Table([[paragraph(label), paragraph(money(value))] for label,value in totals],
                            colWidths=[170, 130], hAlign="RIGHT")
        total_table.setStyle(TableStyle([("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#EAF3FF")),
                                        ("TOPPADDING",(0,0),(-1,-1),5), ("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        story += [total_table, Spacer(1, 16)]
        if invoice.paid_at:
            story.append(paragraph(f"Paiement confirmé le {date(invoice.paid_at)}", small))
        elif invoice.due_at:
            story.append(paragraph(f"Échéance : {date(invoice.due_at)}", small))
        story.append(paragraph(f"Référence Stripe : {invoice.stripe_invoice_id}", small))
        usage = self.invoice_usage(invoice)
        if usage is not None:
            story += [Spacer(1, 20), paragraph("Utilisation IA pendant la période"),
                      paragraph(f"{usage['included']} crédits inclus consommés | {usage['purchased']} crédits achetés consommés", small),
                      paragraph("Relevé informatif actualisé au téléchargement. Ces crédits ne constituent pas une facturation additionnelle.", small)]
        story += [Spacer(1, 16), paragraph("Document Avenqo établi à partir de la facture et du paiement enregistrés. Les services et suppléments ci-dessus reprennent les lignes de facturation ; aucune nouvelle somme n'est ajoutée.", small)]
        def decorate(doc_canvas, document):
            doc_canvas.saveState()
            doc_canvas.setFillColor(colors.HexColor("#087CF0"))
            doc_canvas.rect(0, 742, 612, 50, fill=1, stroke=0)
            doc_canvas.setFillColor(colors.white)
            doc_canvas.setFont("Helvetica-Bold", 17)
            doc_canvas.drawString(50, 762, "AVENQO")
            doc_canvas.setFont("Helvetica", 8)
            doc_canvas.setFillColor(colors.HexColor("#627089"))
            doc_canvas.drawString(50, 30, "Facturation Avenqo | " + number)
            doc_canvas.drawRightString(562, 30, f"Page {document.page}")
            doc_canvas.restoreState()
        document = SimpleDocTemplate(output, pagesize=letter, rightMargin=50, leftMargin=50,
                                     topMargin=76, bottomMargin=54, title=f"Facture {number}", author="Avenqo")
        document.build(story, onFirstPage=decorate, onLaterPages=decorate)
        return output.getvalue(), "application/pdf", f"avenqo-facture-{number}.pdf"

    def invoice_usage(self, invoice: BillingInvoice) -> dict[str, int] | None:
        """Tenant-scoped funded consumption; never charge provider costs twice."""
        from backend.app.models import TenantAICreditLedgerEntry
        if not invoice.period_start or not invoice.period_end:
            return None
        row = self._session.execute(select(
            func.sum(TenantAICreditLedgerEntry.included_delta),
            func.sum(TenantAICreditLedgerEntry.purchased_delta),
        ).where(
            TenantAICreditLedgerEntry.company_id == invoice.company_id,
            TenantAICreditLedgerEntry.transaction_type.in_(["ai_usage", "ai_settlement"]),
            TenantAICreditLedgerEntry.created_at >= invoice.period_start,
            TenantAICreditLedgerEntry.created_at < invoice.period_end,
        )).one()
        return {"included": max(-int(row[0] or 0), 0), "purchased": max(-int(row[1] or 0), 0)}

    def generate_invoices_summary_pdf(
        self,
        invoices: list[BillingInvoice],
        company: Company | None,
    ) -> tuple[bytes, str, str]:
        company_name = company.name if company else "Entreprise Avenqo"
        output = BytesIO()
        doc = canvas.Canvas(output, pagesize=letter)
        doc.setTitle(f"Relevé des factures — {company_name}")

        doc.setFillColorRGB(0.03, 0.49, 0.94)
        doc.rect(0, 750, 612, 42, fill=1, stroke=0)
        doc.setFillColorRGB(1, 1, 1)
        doc.setFont("Helvetica-Bold", 15)
        doc.drawString(50, 764, f"AVENQO — RELEVÉ DE FACTURATION : {company_name.upper()}")

        doc.setFillColorRGB(0.1, 0.1, 0.15)
        doc.setFont("Helvetica-Bold", 14)
        doc.drawString(50, 705, f"Historique des factures émises ({len(invoices)} document(s))")

        y = 660
        doc.setFont("Helvetica-Bold", 10)
        doc.setFillColorRGB(0.2, 0.25, 0.35)
        doc.drawString(50, y, "N° FACTURE")
        doc.drawString(170, y, "DATE")
        doc.drawString(260, y, "PLAN")
        doc.drawString(350, y, "STATUT")
        doc.drawString(450, y, "MONTANT TOTAL")
        y -= 15
        doc.setStrokeColorRGB(0.85, 0.88, 0.92)
        doc.line(50, y, 562, y)
        y -= 18

        doc.setFont("Helvetica", 9)
        for inv in invoices:
            inv_num = inv.number or f"AVQ-{str(inv.id)[:8].upper()}"
            d_str = inv.issued_at.strftime("%Y-%m-%d") if inv.issued_at else "—"
            plan = (inv.plan_code or "Demo").capitalize()
            stat = (inv.status or "paid").upper()
            amt = f"{(inv.total or 0) / 100:,.2f} {(inv.currency or 'CAD').upper()}"
            doc.setFillColorRGB(0.15, 0.15, 0.2)
            doc.drawString(50, y, inv_num)
            doc.drawString(170, y, d_str)
            doc.drawString(260, y, plan)
            doc.drawString(350, y, stat)
            doc.drawString(450, y, amt)
            y -= 20
            if y < 100:
                doc.showPage()
                y = 720

        doc.save()
        return output.getvalue(), "application/pdf", f"avenqo-releve-factures.pdf"

    def ensure_company_invoices(self, company_id: UUID) -> list[BillingInvoice]:
        """Returns persisted invoices; never fabricates a billing document."""
        existing = list(
            self._session.scalars(
                select(BillingInvoice)
                .where(
                    BillingInvoice.company_id == company_id,
                    BillingInvoice.stripe_invoice_id.not_like("in_seed_%"),
                )
                .order_by(BillingInvoice.issued_at.desc())
            )
        )
        if existing:
            return existing

        company = self._session.get(Company, company_id)
        if company is None:
            return []
        # Stripe is the source of truth. Without a synced invoice, report empty
        # history rather than inventing plan, price, tax, payment, or references.
        return []

    def get_fiscal_summary_pdf(
        self,
        company_id: UUID,
        fiscal_year: int,
    ) -> tuple[bytes, str, str]:
        company = self._session.get(Company, company_id)
        if company is None:
            raise InvoiceNotFoundError("Company not found")
        summary = self.get_paid_subscription_totals(company_id, fiscal_year)
        output = BytesIO()
        document = canvas.Canvas(output, pagesize=letter)
        document.setTitle(f"Avenqo fiscal summary {fiscal_year}")
        document.drawString(72, 750, "Avenqo - Accountant preparation summary")
        document.drawString(72, 730, f"Company: {company.name}")
        document.drawString(72, 710, f"Fiscal year: {fiscal_year}")
        document.drawString(72, 690, f"Invoices paid: {summary['invoices_paid']}")
        document.drawString(
            72,
            670,
            f"Missing or unpaid invoices: {summary['missing_or_unpaid_invoices']}",
        )
        y = 640
        for totals in summary["totals_by_currency"]:
            document.drawString(72, y, f"Currency: {totals['currency']}")
            document.drawString(92, y - 18, f"Subscription subtotal: {totals['subscription_expense']}")
            document.drawString(92, y - 36, f"Taxes paid: {totals['taxes_paid']}")
            document.drawString(92, y - 54, f"Total paid: {totals['total_paid']}")
            y -= 90
        document.drawString(
            72,
            72,
            "Preparation only. This report is not tax advice or proof of legal compliance.",
        )
        document.save()
        return output.getvalue(), "application/pdf", f"avenqo-fiscal-summary-{fiscal_year}.pdf"

    def get_admin_company_summary(self, company_id: UUID, fiscal_year: int) -> dict:
        company = self._session.get(Company, company_id)
        if company is None:
            raise InvoiceNotFoundError("Company not found")
        invoices = self._all_company_invoices(company_id)
        latest = invoices[0] if invoices else None
        return {
            "company_id": company.id,
            "company_name": company.name,
            "plan_code": company.subscription_plan,
            "invoice_count": len(invoices),
            "latest_invoice": InvoiceFiscalService._summary_invoice(latest),
            "fiscal_totals": self.get_paid_subscription_totals(company_id, fiscal_year),
        }

    @staticmethod
    def _filters(
        company_id: UUID,
        *,
        start: datetime | None,
        end: datetime | None,
        fiscal_year: int | None,
    ) -> list:
        filters = [
            BillingInvoice.company_id == company_id,
            BillingInvoice.stripe_invoice_id.not_like("in_seed_%"),
        ]
        if fiscal_year is not None:
            start = datetime(fiscal_year, 1, 1, tzinfo=timezone.utc)
            end = datetime(fiscal_year + 1, 1, 1, tzinfo=timezone.utc)
        if start is not None:
            filters.append(BillingInvoice.issued_at >= start)
        if end is not None:
            filters.append(BillingInvoice.issued_at < end)
        return filters

    def _all_company_invoices(
        self,
        company_id: UUID,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        fiscal_year: int | None = None,
    ) -> list[BillingInvoice]:
        return list(
            self._session.scalars(
                select(BillingInvoice)
                .where(*self._filters(company_id, start=start, end=end, fiscal_year=fiscal_year))
                .order_by(BillingInvoice.issued_at.desc())
            )
        )

    @staticmethod
    def _export_row(invoice: BillingInvoice) -> dict:
        descriptions = "; ".join(
            str(item.get("description") or item.get("product_id") or "")
            for item in invoice.line_items
        ).strip("; ")
        return {
            "invoice_number": invoice.number or "",
            "invoice_date": invoice.issued_at.isoformat(),
            "period_start": invoice.period_start.isoformat() if invoice.period_start else "",
            "period_end": invoice.period_end.isoformat() if invoice.period_end else "",
            "plan_product": descriptions or invoice.plan_code or "",
            "subtotal": invoice.subtotal,
            "discounts": invoice.discount_total,
            "tax": invoice.tax_total,
            "total": invoice.total,
            "amount_paid": invoice.amount_paid,
            "amount_due": invoice.amount_due,
            "currency": invoice.currency.upper(),
            "payment_status": invoice.status,
            "stripe_reference": invoice.stripe_invoice_id,
        }

    @staticmethod
    def _summary_invoice(invoice: BillingInvoice | None) -> dict | None:
        if invoice is None:
            return None
        return {
            "id": invoice.id,
            "number": invoice.number,
            "status": invoice.status,
            "amount_paid": invoice.amount_paid,
            "currency": invoice.currency.upper(),
            "issued_at": invoice.issued_at,
        }
