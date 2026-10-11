"""Repair the known revoked E2E marker without creating an OAuth credential."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Company
from backend.app.models.crm import CRMCalendarConnection
from backend.app.services.connector_secret_cipher import ConnectorSecretCipher, ConnectorSecretError


def repair_revoked_calendar_fixture(db: Session, connection_id, cipher: ConnectorSecretCipher, *, environment: str) -> bool:
    if environment != "sandbox":
        raise ConnectorSecretError("Calendar fixture repair is sandbox-only")
    row = db.scalar(select(CRMCalendarConnection).where(CRMCalendarConnection.id == connection_id).with_for_update())
    if row is None:
        raise ConnectorSecretError("Calendar fixture not found")
    company = db.get(Company, row.company_id)
    if not company or not company.slug.startswith("tenant-alpha-") or row.user_id is not None or row.sync_status != "disconnected":
        raise ConnectorSecretError("Calendar is not an eligible disconnected E2E fixture")
    if row.encrypted_credentials != "revoked_fake_payload":
        payload = cipher.decrypt(row.encrypted_credentials)
        if payload.get("revoked") is True and payload.get("legacy_fixture") == "revoked_fake_payload":
            return False
        raise ConnectorSecretError("Unrecognized calendar credentials; OAuth reauthorization required")
    replacement = cipher.encrypt({"revoked": True, "reauthorization_required": True,
                                  "legacy_fixture": row.encrypted_credentials})
    restored = cipher.decrypt(replacement)
    if restored.get("legacy_fixture") != row.encrypted_credentials or not restored.get("revoked"):
        raise ConnectorSecretError("Calendar repair verification failed")
    row.encrypted_credentials = replacement
    db.flush()
    return True
