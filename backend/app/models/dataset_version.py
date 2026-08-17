from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, DatasetVersionStatus


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[DatasetVersionStatus] = mapped_column(nullable=False, default=DatasetVersionStatus.UPLOADED)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    row_count: Mapped[int | None] = mapped_column(nullable=True)
    column_count: Mapped[int | None] = mapped_column(nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)

    dataset: Mapped["Dataset"] = relationship(back_populates="versions")

    __table_args__ = ({"sqlite_autoincrement": True},)
