from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re
import secrets
import base64
import json

from pwdlib.exceptions import UnknownHashError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings
from backend.app.core.permissions import permissions_for
from backend.app.core.security import hash_password, verify_password
from backend.app.models import CompanyMembership, CRMClient, User, UserRole, VoiceAuthSession, VoiceCall, VoiceCallerCredential


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def normalized_phone(value):
    phone = re.sub(r"[^0-9+]", "", value or "")
    return phone if re.fullmatch(r"\+[1-9]\d{7,14}", phone) else None


def redact_voice_secrets(value):
    return re.sub(r"(?<!\d)(?:\d[ -]?){6,12}(?!\d)", "[REDACTED]", str(value or ""))


def validate_voice_pin(pin: str) -> str:
    if not isinstance(pin, str) or not re.fullmatch(r"[0-9]{6,12}", pin):
        raise ValueError("PIN must contain 6 to 12 digits")
    ascending = "01234567890123456789"
    descending = "98765432109876543210"
    repeated = any(len(pin) % size == 0 and pin == pin[:size] * (len(pin) // size)
        for size in range(1, len(pin) // 2 + 1))
    if pin in ascending or pin in descending or repeated:
        raise ValueError("Choose a nontrivial Voice PIN")
    return pin


class VoiceCallerAuth:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def _peppered(self, company_id, principal_id, pin):
        value = f"voice-pin:{company_id}:{principal_id}:{pin}".encode()
        return hmac.new(self.settings.auth_jwt_secret.encode(), value, hashlib.sha256).hexdigest()

    def challenge(self, call):
        if call.ended_at is not None or call.status not in {"routed", "in_progress"}:
            raise PermissionError("Active answered call required")
        token = secrets.token_urlsafe(32)
        call.pin_challenge_hash = hashlib.sha256(token.encode()).hexdigest()
        call.pin_challenge_expires_at = datetime.now(timezone.utc) + timedelta(minutes=2)
        self.db.flush()
        return base64.b64encode(json.dumps({"voice_pin_challenge": token}).encode()).decode()

    def valid_challenge(self, call, client_state):
        if not call.pin_challenge_hash or call.pin_challenge_expires_at is None or utc(call.pin_challenge_expires_at) <= datetime.now(timezone.utc):
            return False
        if not isinstance(client_state, str) or len(client_state) > 1024:
            return False
        try:
            decoded = json.loads(base64.b64decode(client_state, validate=True))
            if not isinstance(decoded, dict):
                return False
            candidate = decoded.get("voice_pin_challenge")
            if not isinstance(candidate, str) or len(candidate) > 128:
                return False
        except (ValueError, TypeError, UnicodeDecodeError):
            return False
        return hmac.compare_digest(hashlib.sha256(candidate.encode()).hexdigest(), call.pin_challenge_hash)

    def set_pin(self, tenant, principal_type, principal_id, pin):
        validate_voice_pin(pin)
        if principal_type == "USER":
            principal = self.db.scalar(select(User).where(User.id == principal_id, User.company_id == tenant.company_id, User.is_active.is_(True)))
            membership = self.db.scalar(select(CompanyMembership).where(CompanyMembership.user_id == principal_id, CompanyMembership.company_id == tenant.company_id, CompanyMembership.is_active.is_(True)))
            if membership is None:
                raise PermissionError("Principal is not an active tenant member")
        elif principal_type == "CUSTOMER":
            principal = self.db.scalar(select(CRMClient).where(CRMClient.id == principal_id, CRMClient.company_id == tenant.company_id, CRMClient.is_deleted.is_(False)))
        else:
            raise ValueError("Unsupported principal type")
        phone = normalized_phone(principal.phone if principal is not None else None)
        if principal is None or phone is None:
            raise PermissionError("A registered tenant principal phone is required")
        if self.db.get_bind().dialect.name == "postgresql":
            self.db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": f"voice_pin:{tenant.company_id}:{phone}"})
        existing = self.db.scalar(select(VoiceCallerCredential).where(VoiceCallerCredential.company_id == tenant.company_id,
            VoiceCallerCredential.principal_type == principal_type, VoiceCallerCredential.principal_id == principal_id))
        shared = self.db.scalar(select(VoiceCallerCredential).where(VoiceCallerCredential.company_id == tenant.company_id, VoiceCallerCredential.phone_number == phone))
        if shared is not None and (existing is None or shared.id != existing.id):
            raise PermissionError("Phone identity is ambiguous")
        if existing is None:
            existing = VoiceCallerCredential(company_id=tenant.company_id, principal_type=principal_type, principal_id=principal_id, phone_number=phone)
            self.db.add(existing)
        existing.phone_number = phone
        existing.pin_hash = hash_password(self._peppered(tenant.company_id, principal_id, pin))
        existing.enabled = True; existing.failed_attempts = 0; existing.locked_until = None
        caller_types = ("OWNER", "EMPLOYEE") if principal_type == "USER" else ("CUSTOMER",)
        for session in self.db.scalars(select(VoiceAuthSession).where(VoiceAuthSession.company_id == tenant.company_id,
            VoiceAuthSession.caller_type.in_(caller_types), VoiceAuthSession.principal_id == principal_id,
            VoiceAuthSession.revoked_at.is_(None))):
            session.revoked_at = datetime.now(timezone.utc)
        self.db.flush()
        return existing

    def establish(self, call):
        now = datetime.now(timezone.utc)
        if call.ended_at is not None:
            raise PermissionError("Call has ended")
        if call.caller_type in {"OWNER", "EMPLOYEE"} and call.authenticated_user_id:
            principal = self.db.scalar(select(User).where(User.id == call.authenticated_user_id, User.company_id == call.company_id, User.is_active.is_(True)))
            membership = self.db.scalar(select(CompanyMembership).where(CompanyMembership.user_id == call.authenticated_user_id, CompanyMembership.company_id == call.company_id, CompanyMembership.is_active.is_(True)))
            if principal is None or membership is None:
                raise PermissionError("Principal unavailable")
            caller_type = "OWNER" if membership.role == UserRole.OWNER else "EMPLOYEE"
            permissions = list(permissions_for(membership.role)); principal_id = principal.id
        elif call.caller_type in {"CLIENT", "CUSTOMER"} and call.verified_client_id:
            principal = self.db.scalar(select(CRMClient).where(CRMClient.id == call.verified_client_id, CRMClient.company_id == call.company_id, CRMClient.is_deleted.is_(False)))
            if principal is None:
                raise PermissionError("Principal unavailable")
            caller_type = "CUSTOMER"; permissions = ["customer:self"]; principal_id = principal.id
        else:
            raise PermissionError("Verified principal required")
        session = self.db.scalar(select(VoiceAuthSession).where(VoiceAuthSession.call_id == call.id, VoiceAuthSession.company_id == call.company_id))
        if session is None:
            session = VoiceAuthSession(company_id=call.company_id, call_id=call.id)
            self.db.add(session)
        session.caller_type = caller_type; session.principal_id = principal_id; session.permissions = permissions
        session.authenticated_at = now
        session.expires_at = now + timedelta(seconds=getattr(self.settings, "voice_auth_session_ttl_seconds", 600))
        session.revoked_at = None
        self.db.flush()
        return session

    def valid_session(self, call):
        now = datetime.now(timezone.utc)
        session = self.db.scalar(select(VoiceAuthSession).where(VoiceAuthSession.call_id == call.id, VoiceAuthSession.company_id == call.company_id))
        if session is None or session.revoked_at is not None or utc(session.expires_at) <= now or call.ended_at is not None:
            return None
        if normalized_phone(call.caller_phone) is None:
            return None
        if session.caller_type == "CUSTOMER":
            principal = self.db.scalar(select(CRMClient).where(CRMClient.id == session.principal_id, CRMClient.company_id == call.company_id, CRMClient.is_deleted.is_(False)))
            return session if principal is not None and call.verified_client_id == principal.id and normalized_phone(principal.phone) == normalized_phone(call.caller_phone) else None
        principal = self.db.scalar(select(User).where(User.id == session.principal_id, User.company_id == call.company_id, User.is_active.is_(True)))
        membership = self.db.scalar(select(CompanyMembership).where(CompanyMembership.user_id == session.principal_id, CompanyMembership.company_id == call.company_id, CompanyMembership.is_active.is_(True)))
        if principal is None or membership is None or call.authenticated_user_id != principal.id or normalized_phone(principal.phone) != normalized_phone(call.caller_phone):
            return None
        return session

    def verify_gather(self, call, pin):
        failed = {"success": False, "authenticated": False, "error": "caller_authentication_failed"}
        maximum = getattr(self.settings, "voice_pin_max_attempts", 5)
        now = datetime.now(timezone.utc)
        if call.ended_at is not None or call.verification_attempts >= maximum:
            return failed
        credential = self.db.scalar(select(VoiceCallerCredential).where(VoiceCallerCredential.company_id == call.company_id,
            VoiceCallerCredential.phone_number == normalized_phone(call.caller_phone), VoiceCallerCredential.enabled.is_(True)).with_for_update())
        call.verification_attempts += 1
        if credential is None:
            verify_password(self._peppered(call.company_id, call.id, pin), hash_password(secrets.token_urlsafe(32)))
            self.db.flush(); return failed
        if credential.locked_until is not None and utc(credential.locked_until) > now:
            self.db.flush(); return failed
        if credential.locked_until is not None:
            credential.failed_attempts = 0; credential.locked_until = None
        valid_format = isinstance(pin, str) and re.fullmatch(r"[0-9]{6,12}", pin)
        candidate = self._peppered(call.company_id, credential.principal_id, pin if isinstance(pin, str) else "")
        try:
            matches = bool(valid_format) and verify_password(candidate, credential.pin_hash)
        except (ValueError, UnknownHashError):
            matches = False
        if not matches:
            credential.failed_attempts += 1
            if credential.failed_attempts >= maximum:
                credential.locked_until = now + timedelta(seconds=getattr(self.settings, "voice_pin_lockout_seconds", 900))
            self.db.flush(); return failed
        principal_model = User if credential.principal_type == "USER" else CRMClient
        principal = self.db.get(principal_model, credential.principal_id)
        if principal is None or principal.company_id != call.company_id or normalized_phone(principal.phone) != credential.phone_number:
            self.db.flush(); return failed
        if credential.principal_type == "USER":
            membership = self.db.scalar(select(CompanyMembership).where(CompanyMembership.user_id == principal.id, CompanyMembership.company_id == call.company_id, CompanyMembership.is_active.is_(True)))
            if not principal.is_active or membership is None:
                self.db.flush(); return failed
            call.caller_type = "OWNER" if membership.role == UserRole.OWNER else "EMPLOYEE"
            call.authenticated_user_id = principal.id; call.verified_client_id = None
        else:
            if principal.is_deleted:
                self.db.flush(); return failed
            call.caller_type = "CLIENT"; call.verified_client_id = principal.id; call.authenticated_user_id = None
        call.caller_verified_at = now
        credential.failed_attempts = 0; credential.locked_until = None
        self.establish(call)
        self.db.flush()
        return {"success": True, "authenticated": True}