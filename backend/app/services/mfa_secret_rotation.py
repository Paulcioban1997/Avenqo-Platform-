"""Atomic MFA re-encryption without changing enrollment or recovery codes."""
from collections.abc import Sequence
from cryptography.fernet import Fernet, MultiFernet, InvalidToken
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from backend.app.models import User


def rotate_mfa_secrets(session: Session, keys: Sequence[str], *, apply: bool = False) -> dict:
    if not keys:
        raise ValueError("Explicit MFA encryption key ring required")
    primary = Fernet(keys[0].encode("ascii"))
    cipher = MultiFernet([Fernet(key.encode("ascii")) for key in keys])
    query = select(User.id, User.mfa_secret_encrypted, User.mfa_enabled).where(
        (User.mfa_secret_encrypted.is_not(None)) | (User.mfa_enabled.is_(True))).order_by(User.id)
    if apply:
        query = query.with_for_update()
    report = {"encrypted": 0, "already_primary": 0, "needs_rotation": 0, "rotated": 0, "verified": 0}
    for user_id, token, enabled in session.execute(query):
        if not token:
            raise ValueError("Enrolled MFA is missing its encrypted secret")
        encoded = token.encode("ascii")
        original = cipher.decrypt(encoded)
        report["encrypted"] += 1
        try:
            primary.decrypt(encoded)
            report["already_primary"] += 1
        except InvalidToken:
            report["needs_rotation"] += 1
            rotated = cipher.rotate(encoded)
            if primary.decrypt(rotated) != original:
                raise ValueError("MFA rotation verification failed")
            if apply:
                changed = session.execute(update(User).where(User.id == user_id,
                    User.mfa_secret_encrypted == token).values(mfa_secret_encrypted=rotated.decode("ascii")))
                if changed.rowcount != 1:
                    raise ValueError("Concurrent MFA change; rotation must roll back")
                report["rotated"] += 1
        report["verified"] += 1
    return report
