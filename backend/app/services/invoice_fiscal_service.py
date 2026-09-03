"""Deterministic tenant invoice queries and accountant-ready exports."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import BytesIO, StringIO
from uuid import UUID

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
        raise InvoiceExportFormatError("Supported invoice exports are CSV and XLSX")

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