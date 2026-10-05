from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class UserSourceSelection(Base):
    __tablename__ = "user_source_selections"

    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    dataset_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    connection_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)