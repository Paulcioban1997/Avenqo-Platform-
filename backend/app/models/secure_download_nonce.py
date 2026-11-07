"""Persistance distribuée et atomique des nonces de téléchargement sécurisé.

Permet de garantir une consommation unique (anti-rejeu) partagée entre
plusieurs instances ou processus d'exécution Railway via PostgreSQL.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class SecureDownloadNonce(Base):
    """Registre distribué anti-rejeu pour les jetons de téléchargement sécurisé."""

    __tablename__ = "secure_download_nonces"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    nonce: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    doc_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    redeemed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
