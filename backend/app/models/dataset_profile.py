"""Profil persistant d'un dataset utilisé par le AI Center."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base


class DatasetProfile(Base):
    """Conserve le schéma détecté sans dépendre du frontend."""

    __tablename__ = "dataset_profiles"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    module_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    numerical_columns: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    categorical_columns: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    schema_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    distribution_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    dataset: Mapped["Dataset"] = relationship(back_populates="profile")