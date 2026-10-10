"""Explicit, expiring, read-only support consent stored in the audit ledger."""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import AuditLogEntry


def active_support_grants(db: Session, company_id: UUID, recipient_id: UUID | None = None) -> list[AuditLogEntry]:
    query = select(AuditLogEntry).where(AuditLogEntry.company_id == company_id,
                                       AuditLogEntry.action == "support_access_granted")
    if recipient_id is not None:
        query = query.where(AuditLogEntry.target_id == str(recipient_id))
    grants = db.scalars(query.order_by(AuditLogEntry.created_at.desc())).all()
    revoked = set(db.scalars(select(AuditLogEntry.target_id).where(
        AuditLogEntry.company_id == company_id, AuditLogEntry.action == "support_access_revoked",
    )).all())
    now = datetime.now(timezone.utc)
    active = []
    for grant in grants:
        try:
            expires_at = datetime.fromisoformat(grant.safe_metadata["expires_at"])
            if expires_at.tzinfo is None:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        if str(grant.id) not in revoked and expires_at > now:
            active.append(grant)
    return active


def support_can_read_retail(db: Session, company_id: UUID, recipient_id: UUID) -> bool:
    return any(grant.safe_metadata.get("scope") == "retail:read"
               for grant in active_support_grants(db, company_id, recipient_id))
