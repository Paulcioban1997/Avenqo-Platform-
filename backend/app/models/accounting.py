"""Modèles de données canoniques pour le module Accounting AI (Phases 14 & D/E Unification).

Sépare strictement les écritures comptables confirmées des propositions IA (`to_verify` / `proposed`),
des commandes commerciales, des paiements encaissés, des remboursements, des notes de crédit (avoirs)
et des prévisions prédictives, avec traçabilité complète multi-module et pistes d'audit.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class AccountingTransaction(TimestampMixin, Base):
    """Transaction financière, écriture de grand livre, encaissement ou remboursement."""

    __tablename__ = "accounting_transactions"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_accounting_tx_company_idempotency",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    # revenue, expense, refund, credit_note, payment, order, transfer, non_posting
    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # journal_entry, order, payment_collected, payment_disbursed, refund, credit_note, transfer, payroll_summary, non_posting
    entry_kind: Mapped[str] = mapped_column(String(50), nullable=False, default="journal_entry", index=True)
    # sales, cogs, marketing, payroll, software, utilities, tax, processing_fees, sales_returns, settlement, other
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    subtotal_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="CAD")
    # confirmed, pending, reconciled, proposed, rejected, voided
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="confirmed", index=True)
    # True = écriture comptable confirmée, False = proposition / estimation / brouillon non posté
    is_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tax_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reference_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Provenance & gouvernance unifiée
    source_module: Mapped[str] = mapped_column(String(50), nullable=False, default="manual", index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    document_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenant_documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    dataset_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    invoice_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("accounting_invoices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    verification_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="confirmed", index=True
    )  # confirmed, to_verify, approved, rejected, verified_connector
    accounting_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="posted", index=True
    )  # draft, proposed, posted, reconciled, rejected, voided
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplicate_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    revision_history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    extra_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    def __init__(self, **kwargs: Any) -> None:
        is_conf = kwargs.get("is_confirmed", True)
        status_val = str(kwargs.get("status") or "")
        if "verification_status" not in kwargs:
            if status_val == "rejected":
                kwargs["verification_status"] = "rejected"
            elif is_conf is False:
                kwargs["verification_status"] = "to_verify"
            else:
                kwargs["verification_status"] = "confirmed"
        if "accounting_status" not in kwargs:
            if status_val == "rejected":
                kwargs["accounting_status"] = "rejected"
            elif is_conf is False:
                kwargs["accounting_status"] = "proposed"
            else:
                kwargs["accounting_status"] = "posted"
        super().__init__(**kwargs)


class AccountingInvoice(TimestampMixin, Base):
    """Facture client (créance), facture fournisseur (dette), reçu, avoir ou proposition documentaire."""

    __tablename__ = "accounting_invoices"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_accounting_inv_company_idempotency",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # receivable (client), payable (fournisseur), credit_note (avoir), refund, receipt, payment, transfer, other
    invoice_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # supplier_invoice, customer_invoice, receipt, payment, refund, credit_note, transfer, non_posting, invoice
    document_nature: Mapped[str] = mapped_column(String(50), nullable=False, default="invoice", index=True)
    # expense, revenue, expense_reversal, revenue_reversal, neutral
    direction: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    # customer_buyer, issuer_supplier, internal_transfer, ambiguous, unknown
    company_role: Mapped[str | None] = mapped_column(String(50), nullable=True)

    party_name: Mapped[str] = mapped_column(String(255), nullable=False)
    issuer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    issue_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    subtotal_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    tax_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tax_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    paid_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="CAD")
    # paid, unpaid, overdue, partial, to_verify, rejected, void
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="unpaid", index=True)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Lignes documentaires, provenance, détection de doublons et gouvernance de classification
    line_items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    source_module: Mapped[str] = mapped_column(String(50), nullable=False, default="manual", index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    document_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenant_documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    dataset_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    duplicate_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    duplicate_warning: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duplicate_candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    verification_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="confirmed", index=True
    )  # confirmed, to_verify, approved, rejected, verified_connector
    accounting_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="posted", index=True
    )  # draft, proposed, posted, reconciled, rejected, voided
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision_history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    extra_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    def __init__(self, **kwargs: Any) -> None:
        is_conf = kwargs.get("is_confirmed", True)
        status_val = str(kwargs.get("status") or "")
        if "verification_status" not in kwargs:
            if status_val == "rejected":
                kwargs["verification_status"] = "rejected"
            elif is_conf is False:
                kwargs["verification_status"] = "to_verify"
            else:
                kwargs["verification_status"] = "confirmed"
        if "accounting_status" not in kwargs:
            if status_val == "rejected":
                kwargs["accounting_status"] = "rejected"
            elif is_conf is False:
                kwargs["accounting_status"] = "proposed"
            else:
                kwargs["accounting_status"] = "posted"
        super().__init__(**kwargs)

    @property
    def remaining_amount(self) -> float:
        if self.invoice_type in {"credit_note", "refund", "payment", "transfer", "other"}:
            return 0.0
        if self.status in {"rejected", "void", "paid"}:
            return 0.0
        return max(0.0, round(self.total_amount - self.paid_amount, 2))


class AccountingTenantPolicy(TimestampMixin, Base):
    """Politique comptable du tenant (gouvernance des propositions, seuils IA, règles fiscales explicites)."""

    __tablename__ = "accounting_tenant_policies"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    # Par défaut False : les synchronisations créent des propositions `to_verify` sauf approbation explicite
    auto_confirm_verified_connector_settlements: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    confidence_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.85)
    configured_tax_rules: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    company_aliases: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    extra_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class AccountingClassificationRule(TimestampMixin, Base):
    """Règle déterministe de classification comptable configurée par l'entreprise."""

    __tablename__ = "accounting_classification_rules"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    counterparty_pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    match_field: Mapped[str] = mapped_column(String(50), nullable=False, default="counterparty")
    # supplier_invoice, customer_invoice, receipt, credit_note, refund, transfer, non_posting
    forced_classification: Mapped[str] = mapped_column(String(50), nullable=False)
    default_category: Mapped[str] = mapped_column(String(100), nullable=False, default="other")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
