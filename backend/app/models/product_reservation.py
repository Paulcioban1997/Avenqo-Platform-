"""Modèle de données pour les réservations de produits en magasin (Cueillette / In-Store Pickup).

Permet une gestion transactionnelle multi-tenant des mises de côté en boutique :
- Persistance en base avec référence unique (RES-...).
- États de cycle de vie : PENDING, CONFIRMED, COLLECTED, CANCELLED, EXPIRED.
- Déduction de stock concurrentiel pour empêcher les doubles réservations.
- Traçabilité multi-tenant stricte par company_id.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class ReservationStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    COLLECTED = "COLLECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class ProductReservation(TimestampMixin, Base):
    """Réservation persistante multi-tenant d'un produit pour cueillette en boutique."""

    __tablename__ = "product_reservations"
    __table_args__ = (
        UniqueConstraint("company_id", "reference_code", name="uq_reservation_company_reference"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reference_code: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ReservationStatus.CONFIRMED, index=True
    )
    product_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(120), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CAD")

    client_name: Mapped[str] = mapped_column(String(180), nullable=False)
    client_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    client_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    pickup_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pickup_date_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_connection_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    source_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_freshness: Mapped[str] = mapped_column(String(32), nullable=False, default="LIVE")
    electronic_stock_locked: Mapped[bool] = mapped_column(nullable=False, default=False)

    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
