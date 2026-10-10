"""Verified, transaction-owned rotation of every connector credential store."""
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.models.commerce_connection import CommerceConnection
from backend.app.models.crm import CRMCalendarConnection
from backend.app.services.connector_secret_cipher import ConnectorSecretCipher, ConnectorSecretError


def rotate_connector_secrets(session: Session, cipher: ConnectorSecretCipher, *, apply: bool = False) -> dict:
    """Caller commits only after all rows pass; an exception requires rollback."""
    result = {"encrypted": 0, "already_primary": 0, "needs_rotation": 0, "rotated": 0, "verified": 0}
    for model in (CommerceConnection, CRMCalendarConnection):
        query = select(model.id, model.encrypted_credentials).where(model.encrypted_credentials.is_not(None))
        if apply:
            query = query.with_for_update()
        for row_id, encrypted in session.execute(query.execution_options(yield_per=100)):
            cipher.decrypt(encrypted)
            result["encrypted"] += 1
            if cipher.uses_primary_key(encrypted):
                result["already_primary"] += 1
            else:
                result["needs_rotation"] += 1
                rotated = cipher.rotate(encrypted)
                if not cipher.uses_primary_key(rotated):
                    raise ConnectorSecretError("Primary-key verification failed; rotation must be rolled back")
                if apply:
                    changed = session.execute(update(model).where(model.id == row_id, model.encrypted_credentials == encrypted)
                                              .values(encrypted_credentials=rotated))
                    if changed.rowcount != 1:
                        raise ConnectorSecretError("Concurrent credential change; rotation must be rolled back")
                    result["rotated"] += 1
            result["verified"] += 1
    return result
