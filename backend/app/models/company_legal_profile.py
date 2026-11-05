from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.app.models.company import Company


class CompanyLegalProfile(TimestampMixin, Base):
    """Profil juridique et d'affaires vérifié d'une entreprise locataire."""

    __tablename__ = "company_legal_profiles"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Identité légale
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trade_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    province_state: Mapped[str] = mapped_column(String(100), nullable=False)
    registration_number: Mapped[str | None] = mapped_column(String(100), nullable=True)  # NEQ si Québec, sinon ID local
    business_number: Mapped[str | None] = mapped_column(String(100), nullable=True)  # BN fédéral / EIN / etc.
    tax_id_gst: Mapped[str | None] = mapped_column(String(100), nullable=True)  # TPS
    tax_id_qst: Mapped[str | None] = mapped_column(String(100), nullable=True)  # TVQ
    tax_id_other: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Autre taxe internationale

    # Adresse enregistrée (siège légal)
    registered_address_street: Mapped[str] = mapped_column(String(255), nullable=False)
    registered_address_city: Mapped[str] = mapped_column(String(100), nullable=False)
    registered_address_state_province: Mapped[str] = mapped_column(String(100), nullable=False)
    registered_address_postal_code: Mapped[str] = mapped_column(String(32), nullable=False)
    registered_address_country: Mapped[str] = mapped_column(String(100), nullable=False)

    # Adresse postale (mailing) si différente
    mailing_address_same: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    mailing_address_street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mailing_address_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mailing_address_state_province: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mailing_address_postal_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mailing_address_country: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Coordonnées corporatives
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    general_email: Mapped[str] = mapped_column(String(255), nullable=False)
    billing_email: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str] = mapped_column(String(120), nullable=False)
    legal_entity_type: Mapped[str] = mapped_column(String(100), nullable=False, default="Corporation")
    preferred_language: Mapped[str] = mapped_column(String(10), nullable=False, default="fr")

    # Représentant légal autorisé
    authorized_representative_first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    authorized_representative_last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    authorized_representative_email: Mapped[str] = mapped_column(String(255), nullable=False)
    authorized_representative_title: Mapped[str] = mapped_column(String(120), nullable=False)
    authorized_representative_capacity: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="Owner",
    )  # Owner, President, CEO, Authorized Director, Authorized Officer, Authorized Representative
    authorized_representative_authority_confirmed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    company: Mapped["Company"] = relationship(back_populates="legal_profile")

