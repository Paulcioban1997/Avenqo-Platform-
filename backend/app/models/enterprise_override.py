"""Dérogations Enterprise (Phase 33) : quotas/capacités personnalisés par tenant.

Enterprise ne signifie pas automatiquement illimité : ce modèle permet de
personnaliser, tenant par tenant, des limites ou capacités spécifiques
négociées contractuellement, sans jamais modifier la politique globale
(`AIQuotaPolicy`) ni les capacités par défaut (`resolve_tenant_capabilities`).
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import JSON, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin


class EnterpriseOverride(TimestampMixin, Base):
    """Dérogations de quotas/capacités IA pour un tenant Enterprise donné."""

    __tablename__ = "enterprise_overrides"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    # {"monthly_ai_requests": 5000, ...} — remplace la limite du plan pour ce tenant.
    quota_overrides: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # {"segmentation": true, "churn": false, ...} — force l'activation/désactivation
    # d'une capacité au-delà de la détection automatique par modèle entraîné.
    capability_overrides: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped["Company"] = relationship()
