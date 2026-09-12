"""Modèles de données canoniques pour le module Accounting AI (Phase 14).

Sépare strictement les écritures comptables confirmées des prédictions et estimations IA.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class AccountingTransaction(TimestampMixin, Base):
    """Transaction financière ou écriture de recettes/dépenses."""

    __tablename__ = "accounting_transactions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # revenue, expense
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # sales, cogs, marketing, payroll, software, utilities, tax, other
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="CAD")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="confirmed", index=True)  # confirmed, pending, reconciled
    is_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # True = confirmed, False = projection
    tax_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reference_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extra_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class AccountingInvoice(TimestampMixin, Base):
    """Facture client (créance) ou fournisseur (dette)."""

    __tablename__ = "accounting_invoices"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    invoice_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # receivable (client), payable (fournisseur)
    party_name: Mapped[str] = mapped_column(String(255), nullable=False)
    issue_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    paid_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="CAD")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="unpaid", index=True)  # paid, unpaid, overdue, partial
    is_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def remaining_amount(self) -> float:
        return max(0.0, self.total_amount - self.paid_amount)
