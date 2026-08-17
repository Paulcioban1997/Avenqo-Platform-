from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin


class Module(TimestampMixin, Base):
    """Représente un module disponible dans la plateforme Enterprise."""

    __tablename__ = "modules"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0.0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    company_modules: Mapped[list["CompanyModule"]] = relationship(
        back_populates="module",
        cascade="all, delete-orphan",
    )
    ai_jobs: Mapped[list["AIJob"]] = relationship(
        back_populates="module",
        cascade="all, delete-orphan",
    )
