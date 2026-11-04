from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin


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
        default="PENDING_SIGNATURE",
        index=True,
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
    metadata_json: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    company: Mapped["Company"] = relationship(back_populates="contracts")
    signatory_user: Mapped["User | None"] = relationship()

