"""Service d'audit Avenqo (Phase 33) : enregistre les actions administratives sûres.

Ne prend en paramètre que des métadonnées déjà sûres (jamais de secrets, jamais
de contenu métier brut) — l'appelant est responsable de ne fournir que des
valeurs prêtes à être consultées par un `platform_admin`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.audit_log import AuditLogEntry


class AuditLogService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def record(
        self,
        *,
        actor_user_id: UUID,
        action: str,
        target_type: str,
        target_id: str | None = None,
        company_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditLogEntry:
        entry = AuditLogEntry(
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            company_id=company_id,
            safe_metadata=metadata or {},
        )
        self._db.add(entry)
        self._db.commit()
        return entry

    def recent(self, limit: int = 100) -> list[AuditLogEntry]:
        return list(
            self._db.scalars(
                select(AuditLogEntry).order_by(AuditLogEntry.created_at.desc()).limit(limit)
            )
        )
