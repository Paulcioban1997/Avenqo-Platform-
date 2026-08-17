from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, CompanyModuleStatus


class CompanyModule(Base):
    """Associe une entreprise à un module activé de la plateforme."""

    __tablename__ = "company_modules"
    __table_args__ = (
        UniqueConstraint("company_id", "module_id", name="uq_company_modules_company_module"),
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
    module_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("modules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[CompanyModuleStatus] = mapped_column(
        SAEnum(CompanyModuleStatus, name="company_module_status"),
        nullable=False,
        default=CompanyModuleStatus.ACTIVE,
    )

    company: Mapped["Company"] = relationship(back_populates="company_modules")
    module: Mapped["Module"] = relationship(back_populates="company_modules")
