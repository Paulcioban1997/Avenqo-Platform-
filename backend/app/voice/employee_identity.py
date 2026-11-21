"""AVENQO VOICE AI — UNIVERSAL EMPLOYEE IDENTITY & MULTI-TENANT ACCESS CONTROL

Architecture Specification & Cryptographic Contracts:
1. Primary Authentication:
   - Unique Identifier (Employee ID, Registered Work Phone, or Work Email) + Personal PIN per tenant.
   - O(1) indexed lookup: Never linear bcrypt scan over large employee cohorts.
   - Peppered HMAC-SHA256 + Argon2/bcrypt hash storage with advisory transactional locks.
2. Step-up Multi-Factor Authentication (MFA):
   - FIDO2 / WebAuthn / Passkey or push confirmation to registered companion app.
   - Required for high-privilege operations: financial ledger access, employee record modifications,
     cross-tenant operations, subscription tier updates, or bulk data exports.
3. Session Cryptographic Binding:
   - VoiceAuthSession strictly binds (company_id, user_id, call_id, auth_epoch, expires_at).
   - Invalidation of session or revision of employee credentials instantly revokes voice authority.
4. Regulatory & Biometric Compliance:
   - NIST SP 800-63B Section 4: Standalone voice biometrics are explicitly NOT compliant as a
     primary authenticator due to replay, spoofing, and generative voice cloning vulnerabilities.
   - Quebec Law 25 (Loi 25 / LCCJTI Art. 45): Express opt-in consent, strict necessity assessment,
     and a mandatory declaration to the Commission d'accès à l'information (CAI) at least 60 days
     prior to deploying any biometric bank.
   - Voice biometrics in Avenqo are designated ONLY as an optional, non-decisive passive fraud signal
     with explicit employee consent, NEVER as a standalone gate.
5. Colleague Handover Protocol:
   - Immediate revocation of Employee A authority.
   - Audio input paused, DTMF buffer cleared.
   - Collect Employee B Identifier + PIN.
   - Direct O(1) verification and establishment of Employee B session with B's exact entitlements.
   - Fail-closed fallback: Any failure reverts to unauthenticated public mode with ZERO privilege bleeding.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, constr


class AuthenticationFactor(str, Enum):
    KNOWLEDGE_PIN = "knowledge_pin"
    POSSESSION_PHONE = "possession_phone"
    POSSESSION_FIDO2_PASSKEY = "possession_fido2_passkey"
    POSSESSION_DEVICE_CONFIRMATION = "possession_device_confirmation"
    BIOMETRIC_VOICE_CONTINUITY = "biometric_voice_continuity"  # Non-decisive secondary signal only


class HandoverState(str, Enum):
    IDLE = "idle"
    REQUESTED = "requested"
    AWAITING_IDENTIFIER = "awaiting_identifier"
    AWAITING_PIN = "awaiting_pin"
    AUTHENTICATING = "authenticating"
    COMPLETED = "completed"
    FAILED_REVERTED_PUBLIC = "failed_reverted_public"


class BiometricComplianceStatus(str, Enum):
    DISABLED = "disabled"
    CONSENT_PENDING = "consent_pending"
    CAI_DECLARATION_PENDING = "cai_declaration_pending"
    COMPLIANT_ACTIVE_SIGNAL = "compliant_active_signal"


# ---------------------------------------------------------------------------
# Employee Identity Schemas (Admin UI & Voice Engine)
# ---------------------------------------------------------------------------

class EmployeeVoiceIdentityCreate(BaseModel):
    user_id: UUID = Field(..., description="Target employee user ID within the tenant")
    employee_identifier: constr(min_length=2, max_length=64) = Field(  # type: ignore[valid-type]
        ..., description="Unique employee badge ID, employee code, or work email"
    )
    work_phone: str | None = Field(None, description="Registered work phone in E.164 format")
    pin: constr(min_length=4, max_length=12) = Field(  # type: ignore[valid-type]
        ..., description="Employee personal Voice PIN (numeric, 4-12 digits)"
    )
    mfa_required_for_privileged: bool = Field(
        True, description="Enforce step-up WebAuthn/Passkey MFA for sensitive operations"
    )


class EmployeeVoiceIdentityUpdate(BaseModel):
    employee_identifier: str | None = None
    work_phone: str | None = None
    new_pin: str | None = None
    enabled: bool | None = None
    mfa_required_for_privileged: bool | None = None


class EmployeeVoiceIdentityResponse(BaseModel):
    id: UUID
    company_id: UUID
    user_id: UUID
    employee_identifier: str
    masked_phone: str | None
    enabled: bool
    failed_attempts: int
    is_locked: bool
    locked_until: datetime | None
    mfa_required_for_privileged: bool
    biometric_status: BiometricComplianceStatus
    created_at: datetime
    updated_at: datetime


class StepUpMFARequest(BaseModel):
    call_id: UUID
    user_id: UUID
    operation: str
    challenge_token: str
    expires_at: datetime
    verification_url: str


class ColleagueHandoverSession(BaseModel):
    call_id: UUID
    company_id: UUID
    previous_user_id: UUID | None
    new_user_id: UUID | None
    state: HandoverState
    handover_count: int = 0
    initiated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


# ---------------------------------------------------------------------------
# Legal & Technical Compliance Specifications
# ---------------------------------------------------------------------------

BIOMETRIC_REGULATORY_DISCLOSURE = {
    "jurisdiction": "Canada / Quebec & International",
    "applicable_frameworks": [
        "NIST SP 800-63B Section 4 (Digital Identity Guidelines - Authentication and Lifecycle Management)",
        "Quebec Law 25 (Loi sur la protection des renseignements personnels dans le secteur privé)",
        "Quebec Act to Establish a Legal Framework for Information Technology (LCCJTI Art. 45)",
    ],
    "nist_sp_800_63b_determination": (
        "Standalone voice biometrics are NOT compliant as a primary authenticator due to presentation attack "
        "vulnerability (synthesis, generative AI, replay). Avenqo uses Identifier + Knowledge-PIN as primary factor."
    ),
    "quebec_law_25_mandates": {
        "express_consent_required": True,
        "cai_60_day_prior_declaration_required": True,
        "biometric_bank_opt_in_only": True,
        "destruction_upon_employment_end": True,
    },
    "implementation_rule": (
        "Voice biometrics may only function as an optional non-decisive risk indicator when express consent "
        "is recorded and the 60-day notice to the Commission d'accès à l'information du Québec is documented."
    ),
}
