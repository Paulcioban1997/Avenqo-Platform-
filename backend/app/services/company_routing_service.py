"""Company Routing NIP Service for multi-tenant inbound telephony routing.

Allows company administrators to generate, rotate, or set custom DTMF routing NIPs
for routing calls dialed into the shared Avenqo platform number (+1 438-607-5438).
Enforces tenant isolation, anti-enumeration, anti-brute-force rate limiting,
and never logs raw secret credentials.
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings
from backend.app.models.audit_log import AuditLogEntry
from backend.app.models.voice import CompanyRoutingNip
from backend.app.services.tenant_rls import supports_rls

logger = logging.getLogger("avenqo.voice.routing_nip")

_TRIVIAL_SEQUENCES = frozenset({
    "0123", "1234", "2345", "3456", "4567", "5678", "6789",
    "3210", "4321", "5432", "6543", "7654", "8765", "9876",
    "01234", "12345", "23456", "34567", "45678", "56789",
    "54321", "65432", "76543", "87654", "98765",
    "123456", "654321",
})


class CompanyRoutingNipService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.max_failed_attempts = getattr(settings, "voice_routing_nip_max_attempts", 3)
        self.lockout_seconds = getattr(settings, "voice_pin_lockout_seconds", 900)

    @staticmethod
    def hash_code(code: str) -> str:
        """Normalized SHA-256 hash of routing digits."""
        clean = code.strip().replace("#", "").replace("*", "")
        return hashlib.sha256(clean.encode("utf-8")).hexdigest()

    @classmethod
    def validate_code(cls, code: str) -> str:
        """Validate format and non-triviality of routing code digits."""
        clean = code.strip().replace("#", "").replace("*", "")
        if not re.match(r"^\d{4,8}$", clean):
            raise ValueError("Le code NIP doit comporter entre 4 et 8 chiffres.")
        if len(set(clean)) == 1:
            raise ValueError("Le code NIP ne peut pas être composé d'un seul chiffre répété.")
        if clean in _TRIVIAL_SEQUENCES:
            raise ValueError("Le code NIP ne peut pas être une séquence triviale évidente.")
        return clean

    def generate_secure_code(self) -> str:
        """Generate a random non-trivial 5-digit code not currently active in any company."""
        for _ in range(50):
            candidate = str(secrets.randbelow(90000) + 10000)
            if len(set(candidate)) > 1 and candidate not in _TRIVIAL_SEQUENCES:
                cand_hash = self.hash_code(candidate)
                existing = self.db.scalar(
                    select(CompanyRoutingNip.id).where(
                        CompanyRoutingNip.routing_code_hash == cand_hash,
                        CompanyRoutingNip.status == "ACTIVE",
                    )
                )
                if existing is None:
                    return candidate
        raise RuntimeError("Impossible de générer un code NIP unique; réessayez.")

    def get_active_nip(self, company_id: UUID) -> CompanyRoutingNip | None:
        """Get the active routing NIP for a tenant."""
        return self.db.scalar(
            select(CompanyRoutingNip).where(
                CompanyRoutingNip.company_id == company_id,
                CompanyRoutingNip.status == "ACTIVE",
            )
        )

    def configure_or_rotate_nip(
        self,
        company_id: UUID,
        user_id: UUID | None,
        custom_code: str | None = None,
    ) -> CompanyRoutingNip:
        """Configure or rotate the company's routing NIP."""
        if custom_code is not None and custom_code.strip():
            code = self.validate_code(custom_code)
        else:
            code = self.generate_secure_code()

        code_hash = self.hash_code(code)

        # Check for conflict across other companies
        conflict = self.db.scalar(
            select(CompanyRoutingNip.id).where(
                CompanyRoutingNip.routing_code_hash == code_hash,
                CompanyRoutingNip.status == "ACTIVE",
                CompanyRoutingNip.company_id != company_id,
            )
        )
        if conflict is not None:
            raise ValueError("Ce code NIP est déjà utilisé par une autre entreprise.")

        now = datetime.now(timezone.utc)

        # Mark existing active NIP as rotated
        active_existing = self.get_active_nip(company_id)
        if active_existing is not None:
            active_existing.status = "ROTATED"
            active_existing.rotated_at = now
            action = "VOICE_ROUTING_NIP_ROTATED"
        else:
            action = "VOICE_ROUTING_NIP_CREATED"

        new_nip = CompanyRoutingNip(
            id=uuid4(),
            company_id=company_id,
            routing_code=code,
            routing_code_hash=code_hash,
            status="ACTIVE",
            created_by_user_id=user_id,
            failed_attempts=0,
            locked_until=None,
        )
        self.db.add(new_nip)

        # Immutable audit log entry (masked code)
        self.db.add(
            AuditLogEntry(
                id=uuid4(),
                actor_user_id=user_id,
                action=action,
                target_type="company_routing_nip",
                target_id=str(new_nip.id),
                company_id=company_id,
                safe_metadata={"status": "ACTIVE", "code_last2": code[-2:], "digits_len": len(code)},
                created_at=now,
            )
        )

        self.db.commit()
        self.db.refresh(new_nip)
        logger.info(
            "Company routing NIP %s for company %s",
            "rotated" if active_existing else "created",
            company_id,
            extra={"company_id": str(company_id)},
        )
        return new_nip

    def revoke_nip(self, company_id: UUID, user_id: UUID | None) -> bool:
        """Revoke the company's active routing NIP."""
        active = self.get_active_nip(company_id)
        if active is None:
            return False

        now = datetime.now(timezone.utc)
        active.status = "REVOKED"
        active.revoked_at = now

        self.db.add(
            AuditLogEntry(
                id=uuid4(),
                actor_user_id=user_id,
                action="VOICE_ROUTING_NIP_REVOKED",
                target_type="company_routing_nip",
                target_id=str(active.id),
                company_id=company_id,
                safe_metadata={"status": "REVOKED"},
                created_at=now,
            )
        )
        self.db.commit()
        logger.info("Company routing NIP revoked for company %s", company_id, extra={"company_id": str(company_id)})
        return True

    def resolve_tenant_by_nip(self, raw_digits: str) -> tuple[UUID | None, str | None]:
        """Resolve tenant company_id from DTMF digits safely without leaking info.

        Returns (company_id, None) on success, or (None, reason) on failure.
        """
        clean = raw_digits.strip().replace("#", "").replace("*", "")
        if not re.match(r"^\d{4,8}$", clean):
            return None, "INVALID_FORMAT"

        code_hash = self.hash_code(clean)

        if supports_rls(self.db):
            try:
                result = self.db.execute(
                    text("SELECT public.resolve_company_routing_nip(:h)"),
                    {"h": code_hash},
                ).scalar()
                if result is not None:
                    return UUID(str(result)), None
            except Exception as exc:
                logger.warning("PostgreSQL resolver function call failed: %s", exc)

        # Fallback / SQLite environment
        nip = self.db.scalar(
            select(CompanyRoutingNip).where(
                CompanyRoutingNip.routing_code_hash == code_hash,
                CompanyRoutingNip.status == "ACTIVE",
            )
        )
        if nip is None:
            return None, "NOT_FOUND"

        if nip.locked_until and nip.locked_until > datetime.now(timezone.utc):
            return None, "LOCKED"

        return nip.company_id, None

    def record_failed_lookup(self, raw_digits: str) -> None:
        """Record a failed routing attempt with anti-brute-force rate limiting."""
        clean = raw_digits.strip().replace("#", "").replace("*", "")
        if not re.match(r"^\d{4,8}$", clean):
            return

        code_hash = self.hash_code(clean)
        nip = self.db.scalar(
            select(CompanyRoutingNip).where(
                CompanyRoutingNip.routing_code_hash == code_hash,
                CompanyRoutingNip.status == "ACTIVE",
            )
        )
        if nip is not None:
            nip.failed_attempts += 1
            if nip.failed_attempts >= self.max_failed_attempts:
                nip.locked_until = datetime.now(timezone.utc) + timedelta(seconds=self.lockout_seconds)
                logger.warning(
                    "Company routing NIP locked due to consecutive failed attempts",
                    extra={"company_id": str(nip.company_id)},
                )
            self.db.commit()
