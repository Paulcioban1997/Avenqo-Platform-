"""Account security controls, available independently of AI credits or billing."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field

from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, require_permission
from backend.app.models import AuditLogEntry, AuthSession, LoginEvent, User
from backend.app.services.support_access import active_support_grants
from backend.app.services.totp import (
    encrypt_mfa_secret,
    decrypt_mfa_secret,
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_code,
    provisioning_uri,
    verify_totp,
)

router = APIRouter(prefix="/security", tags=["security"])


class SupportConsent(BaseModel):
    recipient_email: EmailStr
    reason: str = Field(min_length=10, max_length=250)
    duration_minutes: int = Field(default=15, ge=5, le=60)


@router.post("/support-access", status_code=201)
def grant_support_access(payload: SupportConsent,
                         identity: CurrentIdentity = Depends(require_permission("company:manage")),
                         db: Session = Depends(get_db)) -> dict:
    recipient = db.scalar(select(User).where(User.email == str(payload.recipient_email).lower(),
                                              User.is_active.is_(True), User.is_platform_admin.is_(True)))
    if recipient is None:
        raise HTTPException(400, "Compte de support autorisé introuvable")
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=payload.duration_minutes)
    row = AuditLogEntry(actor_user_id=identity.user_id, company_id=identity.company_id,
                        action="support_access_granted", target_type="user", target_id=str(recipient.id),
                        safe_metadata={"expires_at": expires.isoformat(), "reason": payload.reason,
                                       "scope": "retail:read"})
    db.add(row)
    db.commit()
    return {"id": row.id, "expires_at": expires, "scope": "retail:read"}


@router.get("/support-access")
def list_support_access(identity: CurrentIdentity = Depends(require_permission("company:manage")),
                        db: Session = Depends(get_db)) -> list[dict]:
    return [{"id": row.id, "expires_at": row.safe_metadata["expires_at"],
             "reason": row.safe_metadata.get("reason"), "scope": row.safe_metadata.get("scope")}
            for row in active_support_grants(db, identity.company_id)]


@router.delete("/support-access/{grant_id}", status_code=204)
def revoke_support_access(grant_id: UUID,
                          identity: CurrentIdentity = Depends(require_permission("company:manage")),
                          db: Session = Depends(get_db)) -> Response:
    row = db.scalar(select(AuditLogEntry).where(AuditLogEntry.id == grant_id,
                                              AuditLogEntry.company_id == identity.company_id,
                                              AuditLogEntry.action == "support_access_granted"))
    if row is None:
        raise HTTPException(404, "Autorisation introuvable")
    db.add(AuditLogEntry(actor_user_id=identity.user_id, company_id=identity.company_id,
                        action="support_access_revoked", target_type="support_grant", target_id=str(grant_id)))
    db.commit()
    return Response(status_code=204)


@router.get("/overview")
def overview(identity: CurrentIdentity = Depends(get_current_identity), db: Session = Depends(get_db)) -> dict:
    recommendations = []
    if identity.user.email_verified_at is None:
        recommendations.append({"code": "verify_email", "severity": "high"})
    if not identity.user.mfa_enabled:
        recommendations.append({"code": "enable_mfa", "severity": "medium"})
    active_sessions = db.scalars(select(AuthSession).where(
        AuthSession.user_id == identity.user.id,
        AuthSession.revoked_at.is_(None),
        AuthSession.expires_at > datetime.now(timezone.utc),
    )).all()
    if len(list(active_sessions)) > 3:
        recommendations.append({"code": "review_sessions", "severity": "medium"})
    return {
        "email_verified": identity.user.email_verified_at is not None,
        "role": identity.user.role.value,
        "mfa_supported": True,
        "mfa_enabled": bool(identity.user.mfa_enabled),
        "session_revocation_supported": True,
        "support_access": "explicit_consent_required",
        "recommendations": recommendations,
        "plan_tier": identity.user.company.subscription_plan if identity.user.company else "base",
    }


@router.get("/sessions")
def sessions(identity: CurrentIdentity = Depends(get_current_identity), db: Session = Depends(get_db)) -> list[dict]:
    now = datetime.now(timezone.utc)
    rows = db.scalars(select(AuthSession).where(
        AuthSession.user_id == identity.user.id,
        AuthSession.revoked_at.is_(None),
        AuthSession.expires_at > now,
    ).order_by(AuthSession.created_at.desc())).all()
    return [{"id": row.id, "created_at": row.created_at, "expires_at": row.expires_at,
             "ip_address": row.ip_address, "user_agent": row.user_agent,
             "last_seen_at": row.last_seen_at,
             "current": row.id == identity.auth_session.id} for row in rows]


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(session_id: UUID, identity: CurrentIdentity = Depends(get_current_identity),
                   db: Session = Depends(get_db)) -> Response:
    row = db.scalar(select(AuthSession).where(AuthSession.id == session_id,
                                              AuthSession.user_id == identity.user.id))
    if row is None:
        raise HTTPException(404, "Session introuvable")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        db.add(AuditLogEntry(actor_user_id=identity.user.id, company_id=identity.company_id,
                            action="session_revoked", target_type="auth_session", target_id=str(row.id),
                            safe_metadata={"current_session": row.id == identity.auth_session.id}))
        db.commit()
    return Response(status_code=204)


@router.get("/audit")
def audit(limit: int = 50, identity: CurrentIdentity = Depends(require_permission("users:manage")),
          db: Session = Depends(get_db)) -> list[dict]:
    if not 1 <= limit <= 100:
        raise HTTPException(422, "La limite doit être comprise entre 1 et 100")
    rows = db.scalars(select(AuditLogEntry).where(AuditLogEntry.company_id == identity.company_id)
                      .order_by(AuditLogEntry.created_at.desc(), AuditLogEntry.id.desc()).limit(limit)).all()
    # Metadata may originate in older administrative paths; never expose it blindly.
    return [{"id": row.id, "action": row.action, "target_type": row.target_type,
             "created_at": row.created_at} for row in rows]


@router.get("/login-history")
def login_history(identity: CurrentIdentity = Depends(get_current_identity), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(LoginEvent)
        .where(LoginEvent.company_id == identity.company_id, LoginEvent.user_id == identity.user.id)
        .order_by(LoginEvent.created_at.desc())
        .limit(50)
    ).all()
    return [
        {
            "id": str(row.id),
            "outcome": row.outcome,
            "ip_address": row.ip_address,
            "user_agent": row.user_agent,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


class MfaConfirm(BaseModel):
    code: str = Field(min_length=6, max_length=12)


@router.post("/mfa/enroll")
def enroll_mfa(identity: CurrentIdentity = Depends(get_current_identity), db: Session = Depends(get_db)) -> dict:
    user = db.get(User, identity.user.id)
    if user is None:
        raise HTTPException(404, "Compte introuvable")
    if user.mfa_enabled:
        raise HTTPException(409, "Désactivez la MFA avec votre code actuel avant une nouvelle configuration")
    secret = generate_totp_secret()
    user.mfa_secret_encrypted = encrypt_mfa_secret(secret)
    user.mfa_enabled = False
    db.commit()
    return {"otpauth_url": provisioning_uri(secret, user.email), "secret": secret}


@router.post("/mfa/confirm")
def confirm_mfa(payload: MfaConfirm, identity: CurrentIdentity = Depends(get_current_identity), db: Session = Depends(get_db)) -> dict:
    user = db.get(User, identity.user.id)
    if user is None or not user.mfa_secret_encrypted:
        raise HTTPException(400, "Enrollment MFA requis")
    if not verify_totp(decrypt_mfa_secret(user.mfa_secret_encrypted), payload.code):
        raise HTTPException(400, "Code d'authentification invalide")
    import json

    codes = generate_recovery_codes()
    user.mfa_recovery_hashes = json.dumps([hash_recovery_code(code) for code in codes])
    user.mfa_enabled = True
    db.add(AuditLogEntry(actor_user_id=user.id, company_id=user.company_id, action="mfa_enabled", target_type="user", target_id=str(user.id)))
    db.commit()
    return {"mfa_enabled": True, "recovery_codes": codes}


@router.delete("/mfa")
def disable_mfa(payload: MfaConfirm, identity: CurrentIdentity = Depends(get_current_identity), db: Session = Depends(get_db)) -> dict:
    user = db.get(User, identity.user.id)
    if user is None or not user.mfa_enabled or not user.mfa_secret_encrypted:
        return {"mfa_enabled": False}
    if not verify_totp(decrypt_mfa_secret(user.mfa_secret_encrypted), payload.code):
        raise HTTPException(400, "Code d'authentification invalide")
    user.mfa_enabled = False
    user.mfa_secret_encrypted = None
    user.mfa_recovery_hashes = None
    db.add(AuditLogEntry(actor_user_id=user.id, company_id=user.company_id, action="mfa_disabled", target_type="user", target_id=str(user.id)))
    db.commit()
    return {"mfa_enabled": False}
