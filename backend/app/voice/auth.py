from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import logging
import re
import secrets
import base64
import json
from typing import Any
from uuid import UUID

logger = logging.getLogger("avenqo.voice.auth")

from pwdlib.exceptions import UnknownHashError
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings
from backend.app.core.permissions import permissions_for
from backend.app.core.rate_limit import _FixedWindowLimiter, get_voice_auth_rate_limiter
from backend.app.core.security import hash_password, verify_password
from backend.app.models import CompanyMembership, CRMClient, User, UserRole, VoiceAuthSession, VoiceCall, VoiceCallerCredential, VoiceBusinessConfig, VoiceToolAction
from shared.ai_engine.contracts import TenantContext
from backend.app.services.audit_log_service import AuditLogService


class _TenantVoiceAuthLimiterProxy:
    """Proxy déléguant dynamiquement au limiteur d'authentification configuré (Redis ou Local)."""

    def hit(self, bucket: str, key: str, limit: int, window_seconds: int = 60) -> bool:
        return get_voice_auth_rate_limiter().hit(bucket, key, limit, window_seconds)

    def is_limited(self, bucket: str, key: str, limit: int, window_seconds: int = 60) -> bool:
        return get_voice_auth_rate_limiter().is_limited(bucket, key, limit, window_seconds)

    def get_count(self, bucket: str, key: str, window_seconds: int = 60) -> int:
        return get_voice_auth_rate_limiter().get_count(bucket, key, window_seconds)

    def record_hit(self, bucket: str, key: str, window_seconds: int = 60) -> int:
        limiter = get_voice_auth_rate_limiter()
        if hasattr(limiter, "record_hit"):
            return limiter.record_hit(bucket, key, window_seconds)
        limiter.hit(bucket, key, 999999, window_seconds)
        return limiter.get_count(bucket, key, window_seconds)

    def reset(self) -> None:
        get_voice_auth_rate_limiter().reset()


_tenant_voice_auth_limiter = _TenantVoiceAuthLimiterProxy()
MAX_UNIDENTIFIED_PIN_SCAN = 20


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def normalized_phone(value):
    if not value or not isinstance(value, str):
        return None
    cleaned = re.sub(r"[^\d+]", "", value.strip())
    if cleaned.startswith("+"):
        return cleaned if re.fullmatch(r"\+[1-9]\d{7,14}", cleaned) else None
    digits = cleaned
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    if 8 <= len(digits) <= 15:
        return "+" + digits
    return None


def mask_phone(value: str | None) -> str:
    """Mask a phone number for safe logging without exposing full customer/staff numbers."""
    if not value or not isinstance(value, str):
        return ""
    cleaned = value.strip()
    if len(cleaned) <= 5:
        return "***"
    return f"{cleaned[:3]}***{cleaned[-4:]}"


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
    def __init__(self, db: Session, settings: Settings, limiter: Any = None) -> None:
        self.db = db
        self.settings = settings
        self.limiter = limiter or get_voice_auth_rate_limiter(settings)

    def _record_tenant_failure(self, company_id: Any, is_already_locked_account: bool = False) -> None:
        """Enregistre un échec d'authentification sur le quota d'échecs de l'organisation.

        Si la tentative visait un compte déjà verrouillé, nous n'incrémentons pas le quota
        global de l'entreprise pour éviter qu'un utilisateur verrouillé ne pénalise ses collègues.
        """
        if is_already_locked_account or not company_id:
            return
        tenant_key = str(company_id)
        failed_limit = getattr(self.settings, "voice_tenant_max_failed_auth_per_window", 30)
        window_sec = getattr(self.settings, "voice_tenant_auth_window_seconds", 60)
        self.limiter.hit("voice_auth_tenant_fail", tenant_key, limit=failed_limit, window_seconds=window_sec)

    def _peppered(self, company_id: UUID | str, principal_id: UUID | str, pin: str) -> str:
        value = f"voice-pin:{company_id}:{principal_id}:{pin}".encode()
        return hmac.new(self.settings.auth_jwt_secret.encode(), value, hashlib.sha256).hexdigest()

    def challenge(self, call: VoiceCall) -> str:
        if call.ended_at is not None or call.status not in {"routed", "in_progress"}:
            raise PermissionError("Active answered call required")
        token = secrets.token_urlsafe(32)
        call.pin_challenge_hash = hashlib.sha256(token.encode()).hexdigest()
        call.pin_challenge_expires_at = datetime.now(timezone.utc) + timedelta(minutes=2)
        self.db.flush()
        return base64.b64encode(json.dumps({"voice_pin_challenge": token}).encode()).decode()

    def valid_challenge(self, call: VoiceCall, client_state: str) -> bool:
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

    def set_pin(
        self,
        tenant: TenantContext,
        principal_type: str,
        principal_id: UUID | str,
        pin: str,
        phone_number: str | None = None,
    ) -> VoiceCallerCredential:
        validate_voice_pin(pin)
        principal_uuid = principal_id if isinstance(principal_id, UUID) else UUID(str(principal_id))
        company_uuid = tenant.company_id if isinstance(tenant.company_id, UUID) else UUID(str(tenant.company_id))
        membership: CompanyMembership | None = None
        if principal_type == "USER":
            principal = self.db.scalar(select(User).where(User.id == principal_uuid, User.company_id == company_uuid, User.is_active.is_(True)))
            membership = self.db.scalar(select(CompanyMembership).where(CompanyMembership.user_id == principal_uuid, CompanyMembership.company_id == company_uuid, CompanyMembership.is_active.is_(True)))
            if membership is None:
                raise PermissionError("Principal is not an active tenant member")
        elif principal_type == "CUSTOMER":
            principal = self.db.scalar(select(CRMClient).where(CRMClient.id == principal_uuid, CRMClient.company_id == company_uuid, CRMClient.is_deleted.is_(False)))
        else:
            raise ValueError("Unsupported principal type")
        existing = self.db.scalar(
            select(VoiceCallerCredential).where(
                VoiceCallerCredential.company_id == company_uuid,
                VoiceCallerCredential.principal_id == principal_uuid,
            )
        )
        if phone_number and "*" in phone_number:
            if existing is not None and existing.phone_number:
                phone_number = None
            else:
                raise ValueError("Veuillez saisir un numéro de téléphone complet sans caractères masqués.")

        raw_phone = phone_number or (existing.phone_number if existing is not None else None) or (principal.phone if principal is not None else None)
        if isinstance(principal, User) and principal.company is not None and principal.company.country:
            if principal.company.country.upper() in {"CA", "US", "CANADA", "UNITED STATES"}:
                digits = re.sub(r"\D", "", raw_phone or "")
                if len(digits) == 10:
                    raw_phone = "+1" + digits
                elif len(digits) == 11 and digits.startswith("1"):
                    raw_phone = "+" + digits
        phone = normalized_phone(raw_phone)
        if principal is None or phone is None:
            raise PermissionError("A registered tenant principal phone is required")
        if principal.phone is None or principal_type == "USER":
            principal.phone = phone
        if self.db.get_bind().dialect.name == "postgresql":
            self.db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": f"voice_pin:{company_uuid}:{phone}"})
        # Strict protection: verify that this phone is not registered to another active user in the tenant
        is_owner = False
        if isinstance(principal, User):
            if getattr(principal, "role", None) == UserRole.OWNER:
                is_owner = True
            elif membership is not None and membership.role == UserRole.OWNER:
                is_owner = True

        other_active_user = self.db.scalar(
            select(User).where(
                User.company_id == company_uuid,
                User.id != principal_uuid,
                User.is_active.is_(True),
                or_(
                    User.phone == phone,
                    User.phone == raw_phone,
                    User.phone == (phone[2:] if phone and phone.startswith("+1") else None),
                ),
            )
        )
        if other_active_user is not None:
            if is_owner:
                other_active_user.phone = None
                self.db.flush()
            else:
                raise PermissionError("Ce numéro de téléphone est déjà associé à un autre collaborateur actif de l'entreprise.")

        shared = self.db.scalar(
            select(VoiceCallerCredential).where(
                VoiceCallerCredential.company_id == company_uuid,
                VoiceCallerCredential.phone_number == phone,
            )
        )
        if shared is not None and str(shared.principal_id) == str(principal_uuid):
            shared.principal_type = principal_type
            existing = shared
        elif shared is not None and str(shared.principal_id) != str(principal_uuid):
            # Check if the number is currently claimed by another user in this tenant
            other_user = self.db.scalar(
                select(User).where(
                    User.id == shared.principal_id,
                    User.company_id == company_uuid,
                )
            )

            # P0 Security Rule: NEVER allow non-owners to reassign the phone number of an ACTIVE user.
            # The tenant OWNER with verified password reauthentication may reclaim a number in their tenant.
            if other_user is not None and str(other_user.id) != str(principal_uuid) and other_user.is_active:
                if not is_owner:
                    raise PermissionError("Ce numéro de téléphone est déjà associé à un autre collaborateur actif de l'entreprise.")

            # If the phone was assigned to an inactive/deactivated account, only OWNER or ADMIN may reassign it
            is_owner_or_admin = is_owner
            if isinstance(principal, User):
                if getattr(principal, "role", None) in {UserRole.OWNER, UserRole.ADMIN}:
                    is_owner_or_admin = True
                else:
                    user_membership = membership or self.db.scalar(
                        select(CompanyMembership).where(
                            CompanyMembership.company_id == company_uuid,
                            CompanyMembership.user_id == principal_uuid,
                            CompanyMembership.is_active.is_(True),
                        )
                    )
                    if user_membership is not None and user_membership.role in {UserRole.OWNER, UserRole.ADMIN}:
                        is_owner_or_admin = True

            if not is_owner_or_admin:
                raise PermissionError("Seul un administrateur peut réattribuer le numéro d'un compte inactif.")

            # Authorized reassignment from inactive account or owner reclaim:
            # 1. Revoke any active voice sessions for the previous holder
            now = datetime.now(timezone.utc)
            for old_session in self.db.scalars(
                select(VoiceAuthSession).where(
                    VoiceAuthSession.company_id == company_uuid,
                    VoiceAuthSession.principal_id == shared.principal_id,
                    VoiceAuthSession.revoked_at.is_(None),
                )
            ):
                old_session.revoked_at = now

            # 2. Record explicit audit log of the reassignment
            action_name = "voice_nip_reassigned_by_owner" if (other_user and other_user.is_active) else "voice_nip_reassigned_from_inactive"
            AuditLogService(self.db).record(
                actor_user_id=principal_uuid,
                action=action_name,
                target_type="voice_credential",
                target_id=str(shared.id),
                company_id=company_uuid,
                metadata={
                    "reassigned_from_user_id": str(shared.principal_id),
                    "reassigned_to_user_id": str(principal_uuid),
                    "phone_number": phone,
                },
                commit=False,
            )

            # 3. Clean up any existing duplicate credential for this principal
            if existing is not None and existing.id != shared.id:
                self.db.delete(existing)
                self.db.flush()

            # 4. Reassign credential
            shared.principal_id = principal_uuid
            shared.principal_type = principal_type
            existing = shared

        if existing is None:
            existing = VoiceCallerCredential(
                company_id=company_uuid,
                principal_type=principal_type,
                principal_id=principal_uuid,
                phone_number=phone,
            )
            self.db.add(existing)
        existing.principal_type = principal_type
        existing.phone_number = phone
        existing.pin_hash = hash_password(self._peppered(company_uuid, principal_uuid, pin))
        existing.enabled = True
        existing.failed_attempts = 0
        existing.locked_until = None
        caller_types = ("OWNER", "EMPLOYEE") if principal_type == "USER" else ("CUSTOMER",)
        for session in self.db.scalars(select(VoiceAuthSession).where(VoiceAuthSession.company_id == tenant.company_id,
            VoiceAuthSession.caller_type.in_(caller_types), VoiceAuthSession.principal_id == principal_id,
            VoiceAuthSession.revoked_at.is_(None))):
            session.revoked_at = datetime.now(timezone.utc)
        self.db.flush()
        return existing

    def has_owner_credential(self, company_id: UUID | str) -> bool:
        return self.db.scalar(select(VoiceCallerCredential.id).where(
            VoiceCallerCredential.company_id == company_id,
            VoiceCallerCredential.principal_type == "USER",
            VoiceCallerCredential.enabled.is_(True),
        )) is not None

    def generate_owner_bootstrap_code(self, company_id: UUID | str, user_id: UUID | str) -> tuple[str, datetime]:
        membership = self.db.scalar(select(CompanyMembership).where(
            CompanyMembership.company_id == company_id,
            CompanyMembership.user_id == user_id,
            CompanyMembership.role == UserRole.OWNER,
            CompanyMembership.is_active.is_(True),
        ))
        if membership is None:
            raise PermissionError("Only tenant owner can generate bootstrap code")
        config = self.db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == company_id))
        if config is None:
            raise ValueError("Voice config not initialized")
        code = f"{secrets.randbelow(900000) + 100000:06d}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        code_hash = hmac.new(self.settings.auth_jwt_secret.encode(), f"bootstrap:{company_id}:{code}".encode(), hashlib.sha256).hexdigest()
        action_id = f"owner-bootstrap-otp:{company_id}"
        existing = self.db.scalar(select(VoiceToolAction).where(
            VoiceToolAction.company_id == company_id,
            VoiceToolAction.config_id == config.id,
            VoiceToolAction.action_id == action_id,
        ))
        if existing is not None:
            existing.result = {"code_hash": code_hash, "expires_at": expires_at.isoformat(), "owner_user_id": str(user_id)}
        else:
            self.db.add(VoiceToolAction(
                company_id=company_id,
                config_id=config.id,
                action_id=action_id,
                tool_name="voice_owner_bootstrap",
                result={"code_hash": code_hash, "expires_at": expires_at.isoformat(), "owner_user_id": str(user_id)},
            ))
        self.db.flush()
        return code, expires_at

    def verify_owner_bootstrap_code(self, company_id: UUID | str, candidate_code: str) -> UUID | None:
        if not candidate_code or not re.fullmatch(r"[0-9]{6}", candidate_code):
            return None
        config = self.db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == company_id))
        if config is None:
            return None
        action_id = f"owner-bootstrap-otp:{company_id}"
        receipt = self.db.scalar(select(VoiceToolAction).where(
            VoiceToolAction.company_id == company_id,
            VoiceToolAction.config_id == config.id,
            VoiceToolAction.action_id == action_id,
        ))
        if receipt is None or not isinstance(receipt.result, dict):
            return None
        expected_hash = receipt.result.get("code_hash")
        expires_iso = receipt.result.get("expires_at")
        owner_id_str = receipt.result.get("owner_user_id")
        if not expected_hash or not expires_iso or not owner_id_str:
            return None
        try:
            expires_at = datetime.fromisoformat(expires_iso)
            if utc(expires_at) <= datetime.now(timezone.utc):
                return None
        except Exception:
            return None
        candidate_hash = hmac.new(self.settings.auth_jwt_secret.encode(), f"bootstrap:{company_id}:{candidate_code}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(candidate_hash, str(expected_hash)):
            return None
        try:
            return UUID(owner_id_str)
        except Exception:
            return None

    def consume_owner_bootstrap_code(self, company_id: UUID | str) -> None:
        config = self.db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == company_id))
        if config is not None:
            receipt = self.db.scalar(select(VoiceToolAction).where(
                VoiceToolAction.company_id == company_id,
                VoiceToolAction.config_id == config.id,
                VoiceToolAction.action_id == f"owner-bootstrap-otp:{company_id}",
            ))
            if receipt is not None:
                receipt.result = {"consumed": True, "consumed_at": datetime.now(timezone.utc).isoformat()}
                self.db.flush()

    def enroll_first_call_owner_pin(self, call: VoiceCall, pin: str, owner_user_id: UUID | str) -> bool:
        validate_voice_pin(pin)
        owner_uid = owner_user_id if isinstance(owner_user_id, UUID) else UUID(str(owner_user_id))
        owner_user = self.db.get(User, owner_uid)
        if owner_user is None or owner_user.company_id != call.company_id or not owner_user.is_active:
            return False
        caller_phone = normalized_phone(call.caller_phone)
        if not caller_phone:
            return False
        tenant = TenantContext(company_id=call.company_id, user_id=owner_user.id)
        self.set_pin(tenant, "USER", owner_user.id, pin, phone_number=caller_phone)
        self.consume_owner_bootstrap_code(call.company_id)
        call.caller_type = "OWNER"
        call.authenticated_user_id = owner_user.id
        call.caller_verified_at = datetime.now(timezone.utc)
        self.establish(call)
        self.db.flush()
        return True

    def establish(self, call: VoiceCall) -> VoiceAuthSession:
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
        if getattr(self.settings, "voice_long_calls_enabled", False):
            from backend.app.voice.call_policy import policy_for, remaining
            from backend.app.models import VoiceBusinessConfig
            config = self.db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.id == call.config_id,
                                                                      VoiceBusinessConfig.company_id == call.company_id))
            if config is None:
                raise PermissionError("Voice configuration unavailable")
            policy = policy_for(self.db, config, self.settings)
            seconds = remaining(call)
            if seconds is None or seconds <= 0:
                raise PermissionError("Call allowance exhausted")
            session.expires_at = now + timedelta(seconds=min(policy.auth_seconds, seconds))
        session.revoked_at = None
        self.db.flush()
        return session

    def valid_session(self, call: VoiceCall) -> VoiceAuthSession | None:
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
        if principal is None or membership is None or call.authenticated_user_id != principal.id:
            return None
        credential = self.db.scalar(select(VoiceCallerCredential).where(
            VoiceCallerCredential.company_id == call.company_id,
            VoiceCallerCredential.principal_id == session.principal_id,
        ))
        if credential is not None and (not credential.enabled or (credential.locked_until is not None and utc(credential.locked_until) > now)):
            return None
        return session

    def verify_gather(self, call: VoiceCall, pin: str, identifier: str | None = None) -> dict[str, Any]:
        failed = {"success": False, "authenticated": False, "error": "caller_authentication_failed"}
        maximum = getattr(self.settings, "voice_pin_max_attempts", 5)
        now = datetime.now(timezone.utc)
        if call.ended_at is not None or call.verification_attempts >= maximum:
            logger.warning(
                "VoiceCallerAuth.verify_gather rejected: call_ended=%s, attempts=%s/%s, call_id=%s, company_id=%s",
                bool(call.ended_at), call.verification_attempts, maximum, call.id, call.company_id,
            )
            return {**failed, "reason": "max_attempts_exceeded"}

        # Guardrail Tier 3: Tenant-level failure and volumetric throttling
        tenant_key = str(call.company_id)
        failed_limit = getattr(self.settings, "voice_tenant_max_failed_auth_per_window", 30)
        total_limit = getattr(self.settings, "voice_tenant_max_total_auth_per_window", 120)
        window_sec = getattr(self.settings, "voice_tenant_auth_window_seconds", 60)

        # 1. Total volume throttle (Anti-flood / DoS protection per tenant)
        if not self.limiter.hit("voice_auth_tenant_total", tenant_key, limit=total_limit, window_seconds=window_sec):
            logger.warning(
                "VoiceCallerAuth.verify_gather: tenant-level total auth rate limit exceeded (limit=%s/%ss) for company_id=%s call_id=%s",
                total_limit, window_sec, call.company_id, call.id,
            )
            return {
                **failed,
                "error": "rate_limited",
                "reason": "tenant_total_auth_rate_limited",
                "message": "Trop de requêtes d'authentification simultanées pour cette organisation. Veuillez patienter.",
            }

        # 2. Failure threshold pre-check (inspects failure count WITHOUT incrementing)
        if self.limiter.is_limited("voice_auth_tenant_fail", tenant_key, limit=failed_limit, window_seconds=window_sec):
            logger.warning(
                "VoiceCallerAuth.verify_gather: tenant-level failed auth rate limit exceeded (limit=%s/%ss) for company_id=%s call_id=%s",
                failed_limit, window_sec, call.company_id, call.id,
            )
            return {
                **failed,
                "error": "rate_limited",
                "reason": "tenant_auth_rate_limited",
                "message": "Trop d'échecs d'authentification pour cette organisation. Veuillez réessayer plus tard.",
            }

        # Check for explicit DTMF cancellation via '*' key
        if isinstance(pin, str) and pin.strip().rstrip("#") == "*":
            logger.info("VoiceCallerAuth.verify_gather: caller cancelled via DTMF '*' for call=%s", call.id)
            call.pin_challenge_hash = None
            call.pin_challenge_expires_at = None
            existing_ctx = dict(call.source_context or {})
            existing_ctx.pop("handover_revoked", None)
            existing_ctx["handover_cancelled"] = True
            existing_ctx["public_fallback"] = True
            existing_ctx["pin_gather_status"] = "cancelled"
            call.source_context = existing_ctx
            self.db.flush()
            return {
                "success": False,
                "authenticated": False,
                "reason": "user_cancelled",
                "cancelled": True,
            }

        # Check compound DTMF input format (e.g. "<identifier>*<pin>" or "<identifier>#<pin>")
        if isinstance(pin, str) and not identifier:
            raw_stripped = pin.strip().rstrip("#")
            if "*" in raw_stripped:
                parts = raw_stripped.split("*", 1)
                if len(parts) == 2 and parts[0] and parts[1]:
                    identifier = parts[0].strip()
                    pin = parts[1].strip()
            elif "#" in raw_stripped:
                parts = raw_stripped.split("#", 1)
                if len(parts) == 2 and parts[0] and parts[1]:
                    identifier = parts[0].strip()
                    pin = parts[1].strip()

        if identifier is None and isinstance(call.source_context, dict):
            identifier = call.source_context.get("pending_auth_identifier") or call.source_context.get("target_user_id")

        pin_clean = pin.strip().rstrip("#") if isinstance(pin, str) else ""
        valid_format = isinstance(pin, str) and bool(re.fullmatch(r"[0-9]{4,12}", pin_clean))
        if not valid_format:
            if pin_clean:
                call.verification_attempts += 1
                self.db.flush()
                self._record_tenant_failure(call.company_id)
            logger.warning(
                "VoiceCallerAuth.verify_gather: invalid pin format (length=%s, attempts=%s/%s, call_id=%s, company_id=%s)",
                len(pin_clean), call.verification_attempts, maximum, call.id, call.company_id,
            )
            return {
                **failed,
                "reason": "empty_pin" if not pin_clean else "invalid_pin_format",
                "is_empty": not bool(pin_clean),
            }

        caller_norm = normalized_phone(call.caller_phone)
        credential = None
        caller_user: User | None = None
        candidate_sync_phone: str | None = None
        is_handover = bool((call.source_context or {}).get("handover_revoked"))

        # Step 1: Targeted O(1) Lookup by explicit Identifier (phone, email, UUID)
        if identifier:
            id_str = str(identifier).strip()
            id_phone_norm = normalized_phone(id_str)
            user_filters = [User.email == id_str, User.phone == id_str]
            if id_phone_norm:
                user_filters.append(User.phone == id_phone_norm)
            try:
                user_filters.append(User.id == UUID(id_str))
            except Exception:
                pass
            user_cand = self.db.scalar(
                select(User).where(
                    User.company_id == call.company_id,
                    User.is_active.is_(True),
                    or_(*user_filters),
                )
            )
            if user_cand is not None:
                caller_user = user_cand
                credential = self.db.scalar(
                    select(VoiceCallerCredential).where(
                        VoiceCallerCredential.company_id == call.company_id,
                        VoiceCallerCredential.principal_type == "USER",
                        VoiceCallerCredential.principal_id == user_cand.id,
                    ).with_for_update()
                )
            else:
                cred_filters = [VoiceCallerCredential.phone_number == id_str]
                if id_phone_norm:
                    cred_filters.append(VoiceCallerCredential.phone_number == id_phone_norm)
                cred_cand = self.db.scalar(
                    select(VoiceCallerCredential).where(
                        VoiceCallerCredential.company_id == call.company_id,
                        VoiceCallerCredential.principal_type == "USER",
                        or_(*cred_filters),
                    ).with_for_update()
                )
                if cred_cand is not None:
                    credential = cred_cand
                    caller_user = self.db.scalar(
                        select(User).join(CompanyMembership, CompanyMembership.user_id == User.id)
                        .where(
                            User.id == cred_cand.principal_id,
                            User.company_id == call.company_id,
                            User.is_active.is_(True),
                            CompanyMembership.company_id == call.company_id,
                            CompanyMembership.is_active.is_(True),
                        )
                    )

        # Step 2: Targeted O(1) Lookup by Caller Phone (when not in handover)
        if credential is None and not identifier and caller_norm and not is_handover:
            credential = self.db.scalar(select(VoiceCallerCredential).where(
                VoiceCallerCredential.company_id == call.company_id,
                VoiceCallerCredential.phone_number == caller_norm,
            ).with_for_update())

            if credential is None:
                user_candidates = self.db.scalars(
                    select(User).join(CompanyMembership, CompanyMembership.user_id == User.id)
                    .where(
                        User.company_id == call.company_id,
                        User.is_active.is_(True),
                        CompanyMembership.company_id == call.company_id,
                        CompanyMembership.is_active.is_(True),
                        User.phone.is_not(None),
                    )
                ).all()
                for uc in user_candidates:
                    if normalized_phone(uc.phone) == caller_norm or uc.phone == call.caller_phone:
                        caller_user = uc
                        break

                if caller_user is not None:
                    credential = self.db.scalar(
                        select(VoiceCallerCredential).where(
                            VoiceCallerCredential.company_id == call.company_id,
                            VoiceCallerCredential.principal_type == "USER",
                            VoiceCallerCredential.principal_id == caller_user.id,
                        ).with_for_update()
                    )
                    if credential is not None and credential.phone_number != caller_norm:
                        candidate_sync_phone = caller_norm

        if caller_user is None and credential is not None and credential.principal_type == "USER":
            caller_user = self.db.scalar(
                select(User).join(CompanyMembership, CompanyMembership.user_id == User.id)
                .where(
                    User.id == credential.principal_id,
                    User.company_id == call.company_id,
                    User.is_active.is_(True),
                    CompanyMembership.company_id == call.company_id,
                    CompanyMembership.is_active.is_(True),
                )
            )

        # Step 3: Unidentified PIN resolution with Performance Guardrail & Ambiguity Detection
        matched_in_fallback = False
        max_scan = getattr(self.settings, "voice_pin_max_scan_candidates", MAX_UNIDENTIFIED_PIN_SCAN)

        if credential is None and not identifier:
            raw_count = self.db.scalar(
                select(func.count()).select_from(VoiceCallerCredential).where(
                    VoiceCallerCredential.company_id == call.company_id,
                    VoiceCallerCredential.principal_type == "USER",
                    VoiceCallerCredential.enabled.is_(True),
                )
            )
            try:
                active_count = int(raw_count) if raw_count is not None else 0
            except (TypeError, ValueError):
                active_count = 0

            # Performance Guardrail: For enterprises with many employees (e.g. 100, 1000, 10000),
            # never run an unbounded linear bcrypt search. Mandate employee identifier.
            if active_count > max_scan:
                call.verification_attempts += 1
                self.db.flush()
                logger.warning(
                    "VoiceCallerAuth.verify_gather: tenant size (%s) exceeds scan threshold (%s); identifier required (call_id=%s, company_id=%s)",
                    active_count, max_scan, call.id, call.company_id,
                )
                return {
                    **failed,
                    "error": "identifier_required",
                    "reason": "tenant_requires_identifier",
                    "message": "Dans cette entreprise, veuillez entrer votre identifiant employé ou numéro de téléphone suivi de votre NIP (ex: ID*NIP).",
                }

            # Small organization team fallback scan
            company_creds = self.db.scalars(
                select(VoiceCallerCredential).where(
                    VoiceCallerCredential.company_id == call.company_id,
                    VoiceCallerCredential.principal_type == "USER",
                    VoiceCallerCredential.enabled.is_(True),
                )
            ).all()

            matching_candidates: list[VoiceCallerCredential] = []
            for cand_cred in company_creds:
                if cand_cred.locked_until and utc(cand_cred.locked_until) > now:
                    continue
                cand_peppered = self._peppered(call.company_id, cand_cred.principal_id, pin_clean)
                try:
                    if verify_password(cand_peppered, cand_cred.pin_hash):
                        matching_candidates.append(cand_cred)
                except (ValueError, UnknownHashError):
                    continue

            # Ambiguity Check: Ensure identity is mathematically unique
            if len(matching_candidates) > 1:
                call.verification_attempts += 1
                self.db.flush()
                logger.warning(
                    "VoiceCallerAuth.verify_gather: ambiguous PIN collision detected (%s employees match PIN) for company_id=%s call_id=%s",
                    len(matching_candidates), call.company_id, call.id,
                )
                return {
                    **failed,
                    "error": "ambiguous_pin_identity",
                    "reason": "ambiguous_identifier_required",
                    "message": "Plusieurs employés possèdent ce même NIP. Veuillez entrer votre numéro de téléphone ou identifiant employé suivi de votre NIP.",
                }
            elif len(matching_candidates) == 1:
                credential = matching_candidates[0]
                matched_in_fallback = True
                caller_user = self.db.scalar(
                    select(User).join(CompanyMembership, CompanyMembership.user_id == User.id)
                    .where(
                        User.id == credential.principal_id,
                        User.company_id == call.company_id,
                        User.is_active.is_(True),
                        CompanyMembership.company_id == call.company_id,
                        CompanyMembership.is_active.is_(True),
                    )
                )

        matched_principal_id = str(credential.principal_id) if credential else (str(caller_user.id) if caller_user else None)
        principal_role_str: str | None = None
        if credential and credential.principal_type == "USER":
            mem = self.db.scalar(select(CompanyMembership).where(
                CompanyMembership.user_id == credential.principal_id,
                CompanyMembership.company_id == call.company_id,
                CompanyMembership.is_active.is_(True),
            ))
            if mem and hasattr(mem, "role"):
                principal_role_str = mem.role.value if hasattr(mem.role, "value") else str(mem.role)
            elif caller_user and hasattr(caller_user, "role"):
                principal_role_str = caller_user.role.value if hasattr(caller_user.role, "value") else str(caller_user.role)
        elif caller_user and hasattr(caller_user, "role"):
            principal_role_str = caller_user.role.value if hasattr(caller_user.role, "value") else str(caller_user.role)

        caller_matched = caller_user is not None
        credential_found = credential is not None
        credential_enabled = bool(credential and credential.enabled)
        is_locked = bool(credential and credential.locked_until and utc(credential.locked_until) > now)

        call.verification_attempts += 1
        logger.info(
            "VoiceCallerAuth.verify_gather: company_id=%s call_id=%s caller_matched=%s credential_found=%s enabled=%s locked=%s principal_id=%s principal_role=%s masked_caller=%s masked_cred_phone=%s attempt=%s/%s",
            call.company_id, call.id, caller_matched, credential_found, credential_enabled, is_locked,
            matched_principal_id, principal_role_str,
            mask_phone(call.caller_phone),
            mask_phone(credential.phone_number if credential else None),
            call.verification_attempts, maximum,
        )

        if credential is None or not credential.enabled:
            verify_password(self._peppered(call.company_id, call.id, pin_clean), hash_password(secrets.token_urlsafe(32)))
            self.db.flush()
            fail_reason = "caller_not_recognized" if not caller_matched else ("pin_not_configured" if not credential_found else "credential_disabled")
            self._record_tenant_failure(call.company_id, is_already_locked_account=False)
            logger.warning(
                "VoiceCallerAuth.verify_gather: rejected (reason=%s, company_id=%s, call_id=%s, principal_id=%s, principal_role=%s)",
                fail_reason, call.company_id, call.id, matched_principal_id, principal_role_str,
            )
            return {**failed, "reason": fail_reason}

        if is_locked:
            logger.warning(
                "VoiceCallerAuth.verify_gather: credential locked (company_id=%s, call_id=%s, principal_id=%s, principal_role=%s, locked_until=%s)",
                call.company_id, call.id, credential.principal_id, principal_role_str, credential.locked_until,
            )
            self.db.flush()
            self._record_tenant_failure(call.company_id, is_already_locked_account=True)
            return {**failed, "reason": "account_locked", "locked_until": credential.locked_until.isoformat() if credential.locked_until else None}
        if credential.locked_until is not None:
            credential.failed_attempts = 0
            credential.locked_until = None

        if not matched_in_fallback:
            candidate = self._peppered(call.company_id, credential.principal_id, pin_clean)
            try:
                matches = verify_password(candidate, credential.pin_hash)
            except (ValueError, UnknownHashError):
                matches = False
        else:
            matches = True

        if not matches:
            if identifier or not is_handover:
                credential.failed_attempts += 1
                if credential.failed_attempts >= maximum:
                    credential.locked_until = now + timedelta(seconds=getattr(self.settings, "voice_pin_lockout_seconds", 900))
                    logger.warning(
                        "VoiceCallerAuth.verify_gather: lockout triggered (company_id=%s, call_id=%s, principal_id=%s, principal_role=%s, failed_attempts=%s)",
                        call.company_id, call.id, credential.principal_id, principal_role_str, credential.failed_attempts,
                    )
            logger.warning(
                "VoiceCallerAuth.verify_gather: pin mismatch (company_id=%s, call_id=%s, principal_id=%s, principal_role=%s, attempt=%s/%s)",
                call.company_id, call.id, credential.principal_id, principal_role_str, call.verification_attempts, maximum,
            )
            self.db.flush()
            self._record_tenant_failure(call.company_id, is_already_locked_account=False)
            return {**failed, "reason": "invalid_pin"}

        principal_model = User if credential.principal_type == "USER" else CRMClient
        principal = self.db.get(principal_model, credential.principal_id)
        if principal is None or principal.company_id != call.company_id:
            self.db.flush()
            self._record_tenant_failure(call.company_id, is_already_locked_account=False)
            return {**failed, "reason": "unauthorized_principal"}
        if credential.principal_type == "USER" and isinstance(principal, User):
            membership = self.db.scalar(select(CompanyMembership).where(CompanyMembership.user_id == principal.id, CompanyMembership.company_id == call.company_id, CompanyMembership.is_active.is_(True)))
            if not principal.is_active or membership is None:
                self.db.flush()
                self._record_tenant_failure(call.company_id, is_already_locked_account=False)
                return {**failed, "reason": "inactive_membership"}
            call.caller_type = "OWNER" if membership.role == UserRole.OWNER else "EMPLOYEE"
            call.authenticated_user_id = principal.id
            call.verified_client_id = None
            call.verification_attempts = 0
            call.pin_challenge_hash = None
            call.pin_challenge_expires_at = None
            call.source_context = {
                **(call.source_context or {}),
                "authenticated": True,
                "user_id": str(principal.id),
                "user_name": f"{principal.first_name} {principal.last_name or ''}".strip(),
                "pin_gather_status": "authenticated",
                "handover_revoked": False,
            }
        elif isinstance(principal, CRMClient):
            if principal.is_deleted:
                self.db.flush()
                return failed
            call.caller_type = "CLIENT"
            call.verified_client_id = principal.id
            call.authenticated_user_id = None
        else:
            self.db.flush()
            return failed
        call.caller_verified_at = now
        credential.failed_attempts = 0
        credential.locked_until = None
        self.establish(call)

        # Post-authentication verified phone synchronization:
        # Preconditions:
        # 1. PIN verification was 100% successful.
        # 2. Principal is a valid active User of this company.
        # 3. Caller ID matches the phone officially registered on the principal's User account.
        # 4. Strict conflict check: No other user or credential in this company already uses this phone number.
        if (
            candidate_sync_phone
            and credential.principal_type == "USER"
            and isinstance(principal, User)
            and principal.id == credential.principal_id
            and (normalized_phone(principal.phone) == candidate_sync_phone or principal.phone == call.caller_phone)
        ):
            conflict_cred = self.db.scalar(
                select(VoiceCallerCredential).where(
                    VoiceCallerCredential.company_id == call.company_id,
                    VoiceCallerCredential.phone_number == candidate_sync_phone,
                    VoiceCallerCredential.id != credential.id,
                )
            )
            conflict_user = self.db.scalar(
                select(User).where(
                    User.company_id == call.company_id,
                    User.phone == candidate_sync_phone,
                    User.id != principal.id,
                )
            )
            if conflict_cred is None and conflict_user is None:
                old_phone = credential.phone_number
                credential.phone_number = candidate_sync_phone
                AuditLogService(self.db).record(
                    actor_user_id=principal.id,
                    action="voice_credential_phone_synchronized",
                    target_type="voice_credential",
                    target_id=str(credential.id),
                    company_id=call.company_id,
                    metadata={"previous_phone": old_phone, "synchronized_phone": candidate_sync_phone},
                    commit=False,
                )
            else:
                logger.warning(
                    "VoiceCallerAuth.verify_gather: phone sync skipped due to conflict (company_id=%s, phone=%s)",
                    call.company_id, candidate_sync_phone,
                )

        self.db.flush()
        logger.info(
            "VoiceCallerAuth.verify_gather: authentication succeeded (company_id=%s, call_id=%s, principal_id=%s, caller_type=%s)",
            call.company_id, call.id, principal.id, call.caller_type,
        )
        return {"success": True, "authenticated": True}

    def logout_session(self, call: VoiceCall) -> dict[str, Any]:
        """Revoke active private voice session and return call to public mode."""
        now = datetime.now(timezone.utc)
        session = self.db.scalar(
            select(VoiceAuthSession).where(
                VoiceAuthSession.call_id == call.id,
                VoiceAuthSession.company_id == call.company_id,
                VoiceAuthSession.revoked_at.is_(None),
            )
        )
        if session is not None:
            session.revoked_at = now
        call.caller_type = "PUBLIC"
        call.authenticated_user_id = None
        call.verified_client_id = None
        self.db.flush()
        return {"success": True, "mode": "public"}
