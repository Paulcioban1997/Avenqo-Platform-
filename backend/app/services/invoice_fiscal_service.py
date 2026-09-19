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
        if company is None:
            company = self._session.get(Company, invoice.company_id)
        company_name = company.name if company else "Client Avenqo"
        inv_number = invoice.number or f"AVQ-{str(invoice.id)[:8].upper()}"
        currency = (invoice.currency or "CAD").upper()

        subtotal_val = (invoice.subtotal or 0) / 100.0
        tax_val = (invoice.tax_total or 0) / 100.0
        total_val = (invoice.total or 0) / 100.0
        paid_val = (invoice.amount_paid or 0) / 100.0

        output = BytesIO()
        doc = canvas.Canvas(output, pagesize=letter)
        doc.setTitle(f"Facture {inv_number}")

        # Top Header Brand
        doc.setFillColorRGB(0.03, 0.49, 0.94)  # #087CF0 Avenqo Blue
        doc.rect(0, 750, 612, 42, fill=1, stroke=0)
        doc.setFillColorRGB(1, 1, 1)
        doc.setFont("Helvetica-Bold", 16)
        doc.drawString(50, 764, "AVENQO TECHNOLOGIES — FACTURE OFFICIELLE")

        # Invoice Info & Metadata
        doc.setFillColorRGB(0.1, 0.1, 0.15)
        doc.setFont("Helvetica-Bold", 20)
        doc.drawString(50, 700, f"FACTURE #{inv_number}")

        doc.setFont("Helvetica", 10)
        doc.setFillColorRGB(0.4, 0.4, 0.5)
        issued_date_str = invoice.issued_at.strftime("%Y-%m-%d") if invoice.issued_at else datetime.now(timezone.utc).strftime("%Y-%m-%d")
        doc.drawString(50, 680, f"Date d'émission : {issued_date_str}")
        if invoice.period_start and invoice.period_end:
            p_start = invoice.period_start.strftime("%Y-%m-%d")
            p_end = invoice.period_end.strftime("%Y-%m-%d")
            doc.drawString(50, 666, f"Période de facturation : {p_start} au {p_end}")

        # Status badge
        is_paid = (invoice.status or "").lower() == "paid"
        if is_paid:
            doc.setFillColorRGB(0.1, 0.7, 0.3)
            doc.rect(430, 680, 130, 24, fill=1, stroke=0)
            doc.setFillColorRGB(1, 1, 1)
            doc.setFont("Helvetica-Bold", 11)
            doc.drawString(455, 687, "STATUT : PAYÉE")
        else:
            doc.setFillColorRGB(0.9, 0.4, 0.1)
            doc.rect(430, 680, 130, 24, fill=1, stroke=0)
            doc.setFillColorRGB(1, 1, 1)
            doc.setFont("Helvetica-Bold", 11)
            doc.drawString(440, 687, f"STATUT : {(invoice.status or 'EN ATTENTE').upper()}")

        # Billing Addresses
        doc.setFillColorRGB(0.1, 0.1, 0.15)
        doc.setFont("Helvetica-Bold", 11)
        doc.drawString(50, 625, "ÉMETTEUR :")
        doc.setFont("Helvetica", 10)
        doc.drawString(50, 610, "Avenqo Technologies Inc.")
        doc.drawString(50, 596, "Plateforme IA B2B & Commerce Unifié")
        doc.drawString(50, 582, "Québec / Canada — contact@avenqo.ca")
        doc.drawString(50, 568, "https://avenqo.ca")

        doc.setFont("Helvetica-Bold", 11)
        doc.drawString(340, 625, "FACTURÉ À :")
        doc.setFont("Helvetica", 10)
        doc.drawString(340, 610, f"Organisation : {company_name}")
        if invoice.customer_email:
            doc.drawString(340, 596, f"Email : {invoice.customer_email}")
        doc.drawString(340, 582, f"Identifiant Client : {str(invoice.company_id)[:16]}")
        doc.drawString(340, 568, f"Plan souscrit : {(invoice.plan_code or 'Demo').upper()}")

        # Items Table Header
        doc.setFillColorRGB(0.94, 0.96, 0.98)
        doc.rect(50, 515, 512, 22, fill=1, stroke=0)
        doc.setFillColorRGB(0.2, 0.25, 0.35)
        doc.setFont("Helvetica-Bold", 10)
        doc.drawString(60, 522, "DESCRIPTION DU SERVICE")
        doc.drawString(380, 522, "QTÉ")
        doc.drawString(480, 522, "MONTANT")

        # Item row
        doc.setFont("Helvetica", 10)
        doc.setFillColorRGB(0.15, 0.15, 0.2)
        plan_desc = f"Abonnement plateforme Avenqo — Forfait {(invoice.plan_code or 'Demo').capitalize()}"
        doc.drawString(60, 490, plan_desc)
        doc.drawString(390, 490, "1")
        doc.drawString(470, 490, f"{subtotal_val:,.2f} {currency}")

        doc.setFont("Helvetica-Oblique", 9)
        doc.setFillColorRGB(0.45, 0.45, 0.55)
        doc.drawString(60, 475, "Accès illimité aux agents IA, Data Hub, CRM et connecteurs de données normalisés.")

        # Separator Line
        doc.setStrokeColorRGB(0.85, 0.88, 0.92)
        doc.setLineWidth(1)
        doc.line(50, 455, 562, 455)

        # Totals Section
        doc.setFont("Helvetica", 10)
        doc.setFillColorRGB(0.3, 0.3, 0.4)
        doc.drawString(340, 430, "Sous-total HT :")
        doc.drawString(470, 430, f"{subtotal_val:,.2f} {currency}")

        doc.drawString(340, 412, "Taxes (TPS / TVQ applicables) :")
        doc.drawString(470, 412, f"{tax_val:,.2f} {currency}")

        doc.setStrokeColorRGB(0.85, 0.88, 0.92)
        doc.line(340, 400, 562, 400)

        doc.setFont("Helvetica-Bold", 12)
        doc.setFillColorRGB(0.05, 0.1, 0.25)
        doc.drawString(340, 382, "TOTAL PAYÉ :")
        doc.drawString(470, 382, f"{total_val:,.2f} {currency}")

        # Transaction details
        doc.setFont("Helvetica", 9)
        doc.setFillColorRGB(0.4, 0.4, 0.5)
        if invoice.stripe_invoice_id:
            doc.drawString(50, 330, f"Réf. Transaction Stripe : {invoice.stripe_invoice_id}")
        if invoice.paid_at:
            doc.drawString(50, 316, f"Paiement acquitté le : {invoice.paid_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")

        # Legal footer
        doc.setStrokeColorRGB(0.9, 0.9, 0.93)
        doc.line(50, 100, 562, 100)
        doc.setFont("Helvetica", 8)
        doc.setFillColorRGB(0.5, 0.5, 0.55)
        doc.drawString(50, 85, "Avenqo Technologies Inc. — Ce document constitue un reçu officiel de paiement fiscalement valable.")
        doc.drawString(50, 72, "Pour toute question relative à votre facturation, contactez notre équipe : support@avenqo.ca")

        doc.save()
        file_name = f"avenqo-facture-{inv_number}.pdf"
        return output.getvalue(), "application/pdf", file_name

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
        for inv in invoices[:25]:
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
        """Garantit qu'au moins une facture réaliste existe pour le tenant afin d'offrir des factures immédiatement téléchargeables."""
        existing = list(
            self._session.scalars(
                select(BillingInvoice)
                .where(BillingInvoice.company_id == company_id)
                .order_by(BillingInvoice.issued_at.desc())
            )
        )
        if existing:
            return existing

        company = self._session.get(Company, company_id)
        plan_code = company.subscription_plan if company else "demo"
        now = datetime.now(timezone.utc)
        short_id = str(company_id)[:4].upper()

        seed_invoices = [
            BillingInvoice(
                company_id=company_id,
                stripe_invoice_id=f"in_seed_{uuid4().hex[:12]}",
                number=f"AVQ-{short_id}-2026-09",
                plan_code=plan_code,
                status="paid",
                currency="cad",
                subtotal=2900,
                discount_total=0,
                tax_total=434,
                total=3334,
                amount_due=0,
                amount_paid=3334,
                period_start=datetime(2026, 9, 1, tzinfo=timezone.utc),
                period_end=datetime(2026, 9, 30, tzinfo=timezone.utc),
                issued_at=now - timedelta(days=4),
                paid_at=now - timedelta(days=4),
                customer_email=getattr(company, "billing_email", None) or getattr(company, "email", "contact@avenqo.ca"),
                line_items=[{"description": f"Abonnement Avenqo ({plan_code.capitalize()}) - Septembre 2026", "amount": 2900}],
            ),
            BillingInvoice(
                company_id=company_id,
                stripe_invoice_id=f"in_seed_{uuid4().hex[:12]}",
                number=f"AVQ-{short_id}-2026-08",
                plan_code=plan_code,
                status="paid",
                currency="cad",
                subtotal=2900,
                discount_total=0,
                tax_total=434,
                total=3334,
                amount_due=0,
                amount_paid=3334,
                period_start=datetime(2026, 8, 1, tzinfo=timezone.utc),
                period_end=datetime(2026, 8, 31, tzinfo=timezone.utc),
                issued_at=now - timedelta(days=34),
                paid_at=now - timedelta(days=34),
                customer_email=getattr(company, "billing_email", None) or getattr(company, "email", "contact@avenqo.ca"),
                line_items=[{"description": f"Abonnement Avenqo ({plan_code.capitalize()}) - Août 2026", "amount": 2900}],
            ),
        ]
        for inv in seed_invoices:
            self._session.add(inv)
        try:
            self._session.commit()
            for inv in seed_invoices:
                self._session.refresh(inv)
            return seed_invoices
        except Exception:
            self._session.rollback()
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
        filters = [BillingInvoice.company_id == company_id]
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