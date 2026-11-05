from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.app.models.company import Company
    from backend.app.models.user import User


class ContractLifecycleStatus(StrEnum):
    """Machine d'état explicite du cycle de vie contractuel Avenqo."""

    DRAFT = "DRAFT"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    IN_REVIEW = "IN_REVIEW"
    READY_FOR_SIGNATURE = "READY_FOR_SIGNATURE"
    CUSTOMER_SIGNED = "CUSTOMER_SIGNED"
    PROVIDER_SIGNING_REQUIRED = "PROVIDER_SIGNING_REQUIRED"
    FULLY_EXECUTED = "FULLY_EXECUTED"
    UPLOADED_FOR_REVIEW = "UPLOADED_FOR_REVIEW"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"  # Compatibilité manuscript
    PENDING_SIGNATURE = "PENDING_SIGNATURE"        # Rétrocompatibilité
    SIGNED = "SIGNED"                              # Rétrocompatibilité
    BLOCKED = "BLOCKED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    VOIDED = "VOIDED"
    SUPERSEDED = "SUPERSEDED"


class ContractExecutionPartyState(StrEnum):
    """État d'exécution par partie contractuelle."""

    PENDING_CUSTOMER = "PENDING_CUSTOMER"
    PENDING_PROVIDER = "PENDING_PROVIDER"
    COMPLETED = "COMPLETED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    VOIDED = "VOIDED"


class CompanyContract(TimestampMixin, Base):
    """Contrat légal et commercial rattaché à une entreprise cliente (locataire)."""

    __tablename__ = "company_contracts"
    __table_args__ = (
        UniqueConstraint("company_id", "contract_type", "version", name="uq_company_contracts_type_version"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contract_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ContractLifecycleStatus.PENDING_SIGNATURE.value,
        index=True,
    )
    execution_state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ContractExecutionPartyState.PENDING_CUSTOMER.value,
    )
    version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="2026-V1",
    )
    language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="fr",
    )
    signature_mode: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    # Signataire Client
    signatory_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    signatory_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    signatory_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    signatory_title: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    signatory_authority_declared: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    signed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Contresignataire Fournisseur (Avenqo / PMC Solutions AI)
    provider_signatory_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    provider_signatory_title: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    provider_signed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    provider_signature_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    # Intégrité & Preuve
    sha256_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
    )
    content_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    storage_path: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    audit_receipt_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    commercial_schedule_json: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    completion_record_json: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    metadata_json: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    company: Mapped["Company"] = relationship(back_populates="contracts")
    signatory_user: Mapped["User | None"] = relationship()
