"""Company-scoped linguistic profile shared by every Avenqo module.

Timezone for dates stays on ``Company.timezone`` (and VoiceBusinessConfig for
telephony). This table never stores an imposed language from country, phone,
or IP — only an explicit company choice.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin

FALLBACK_POLICY_STAY_PRIMARY = "stay_primary"


class CompanyLocaleProfile(TimestampMixin, Base):
    """1:1 tenant linguistic profile. Readable by Voice, CRM, Retail, billing, Central AI, auth."""

    __tablename__ = "company_locale_profiles"
    __table_args__ = (UniqueConstraint("company_id", name="uq_company_locale_profile_company"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    primary_locale: Mapped[str] = mapped_column(String(16), nullable=False)
    secondary_locales: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    voice_by_locale: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    fallback_policy: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=FALLBACK_POLICY_STAY_PRIMARY,
    )

    company: Mapped["Company"] = relationship(back_populates="locale_profile")
