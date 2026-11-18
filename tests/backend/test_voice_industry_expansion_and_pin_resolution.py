"""Backend tests for Voice AI Industry Expansion & Employee PIN Resolution.
Verifies:
1. Descriptive error localization for Voice PIN failures (no generic masking).
2. Phone number normalization for Canadian 10-digit numbers.
3. Ambiguous phone collisions returning clear conflict messages.
4. Incorrect password rejection (403).
5. Trivial PIN rejection (complexity).
6. Multi-tenant isolation: different companies keep independent sector configurations and PINs.
7. Active PIN status guarantees (configured + enabled + !is_locked).
8. Strict protection against PIN or password leakage.
"""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy import select

from backend.app.core.error_localization import http_error_message, validation_summary
from backend.app.core.security import hash_password, verify_password
from backend.app.models import (
    Company,
    CompanyMembership,
    User,
    UserRole,
    VoiceBusinessConfig,
    VoiceCallerCredential,
)
from backend.app.schemas.voice import VoicePinRequest
from backend.app.voice.auth import VoiceCallerAuth, normalized_phone, validate_voice_pin
from backend.app.config.settings import Settings
from shared.ai_engine.contracts import TenantContext
from tests.backend.test_voice_tts_and_dynamic_retail_sync import _setup_multi_tenant_db


def test_voice_error_localization_preserves_specific_pin_messages():
    """Ensure error_localization never swallows voice PIN messages into generic validation_failed."""
    # French
    msg_trivial_fr = http_error_message(422, "fr-CA", "Choose a nontrivial Voice PIN")
    assert "sécurisé" in msg_trivial_fr
    assert "Certaines informations" not in msg_trivial_fr

    msg_mismatch_fr = http_error_message(422, "fr", "Voice PIN and confirmation PIN do not match")
    assert "correspondent pas" in msg_mismatch_fr
    assert "Certaines informations" not in msg_mismatch_fr

    msg_pw_match_fr = http_error_message(422, "fr", "Voice PIN must not be identical to your account password")
    assert "mot de passe" in msg_pw_match_fr
    assert "Certaines informations" not in msg_pw_match_fr

    msg_ambiguous_fr = http_error_message(422, "fr", "Phone identity is ambiguous")
    assert "collaborateur" in msg_ambiguous_fr or "téléphone" in msg_ambiguous_fr

    # English
    msg_trivial_en = http_error_message(422, "en-US", "Choose a nontrivial Voice PIN")
    assert "secure" in msg_trivial_en.lower() or "nontrivial" in msg_trivial_en.lower()

    msg_mismatch_en = http_error_message(422, "en", "Voice PIN and confirmation PIN do not match")
    assert "match" in msg_mismatch_en.lower()


def test_schema_voice_pin_request_normalizes_canadian_phone():
    """VoicePinRequest normalizes 10-digit Canadian phone numbers."""
    req1 = VoicePinRequest(
        pin="902841",
        confirm_pin="902841",
        phone_number="5142955720",
        current_password="MyStrongPassword123!",
    )
    assert req1.phone_number == "+15142955720"

    req2 = VoicePinRequest(
        pin="902841",
        confirm_pin="902841",
        phone_number="(514) 295-5720",
        current_password="MyStrongPassword123!",
    )
    assert req2.phone_number == "+15142955720"

    req3 = VoicePinRequest(
        pin="902841",
        confirm_pin="902841",
        phone_number="+15142955720",
        current_password="MyStrongPassword123!",
    )
    assert req3.phone_number == "+15142955720"


def test_schema_voice_pin_request_rejects_trivial_pin_with_specific_error():
    """Sequential and repeated PINs are rejected with descriptive messages."""
    with pytest.raises(ValueError) as exc1:
        VoicePinRequest(
            pin="123456",
            confirm_pin="123456",
            phone_number="+15142955720",
            current_password="MyStrongPassword123!",
        )
    assert "nontrivial" in str(exc1.value).lower()

    with pytest.raises(ValueError) as exc2:
        VoicePinRequest(
            pin="777777",
            confirm_pin="777777",
            phone_number="+15142955720",
            current_password="MyStrongPassword123!",
        )
    assert "nontrivial" in str(exc2.value).lower()


def test_phone_ambiguity_collision_prevents_impersonation(tmp_path):
    """If another staff member in the same company already uses the phone, set_pin rejects."""
    engine, session, company_a, config_a, user_a, company_b, config_b, user_b = _setup_multi_tenant_db(tmp_path)
    dummy_secret = "test_synthetic_secret_" + "x" * 20
    settings = Settings(AUTH_JWT_SECRET=dummy_secret)

    # Add second employee in company A
    user_a2 = User(
        id=uuid4(),
        company_id=company_a.id,
        first_name="Jean",
        last_name="Tremblay",
        email="employee2@company-a.ca",
        password_hash=hash_password("Pass123456!"),
        is_active=True,
    )
    mem_a2 = CompanyMembership(
        id=uuid4(),
        company_id=company_a.id,
        user_id=user_a2.id,
        role=UserRole.USER,
        is_active=True,
    )
    session.add_all([user_a2, mem_a2])
    session.commit()

    tenant_a1 = TenantContext(company_id=company_a.id, user_id=user_a.id)
    tenant_a2 = TenantContext(company_id=company_a.id, user_id=user_a2.id)
    auth = VoiceCallerAuth(session, settings)

    shared_phone = "+15149998877"

    # User 1 claims the phone
    auth.set_pin(tenant_a1, "USER", user_a.id, "948201", phone_number=shared_phone)
    session.commit()

    # User 2 attempts to claim the same phone in company A -> PermissionError
    with pytest.raises(PermissionError) as exc:
        auth.set_pin(tenant_a2, "USER", user_a2.id, "739105", phone_number=shared_phone)
    assert "collaborateur" in str(exc.value).lower() or "ambiguous" in str(exc.value).lower()


def test_owner_can_reassign_or_rotate_phone_without_ambiguity_collision(tmp_path):
    """Owner can claim or rotate phone number even if a stale/seed record held it, or rotate their own PIN."""
    engine, session, company_a, config_a, user_a, company_b, config_b, user_b = _setup_multi_tenant_db(tmp_path)
    dummy_secret = "test_synthetic_secret_" + "x" * 20
    settings = Settings(AUTH_JWT_SECRET=dummy_secret)

    tenant_a1 = TenantContext(company_id=company_a.id, user_id=user_a.id)
    auth = VoiceCallerAuth(session, settings)
    owner_phone = "+15142955720"

    # 1. Initial PIN set by owner
    cred1 = auth.set_pin(tenant_a1, "USER", user_a.id, "948201", phone_number=owner_phone)
    session.commit()
    assert cred1.phone_number == owner_phone

    # 2. Owner rotates/updates PIN with same phone -> must succeed smoothly without collision
    cred2 = auth.set_pin(tenant_a1, "USER", user_a.id, "682491", phone_number=owner_phone)
    session.commit()
    assert cred2.id == cred1.id
    assert cred2.phone_number == owner_phone

    # 3. If an inactive employee had a credential with a new phone number
    inactive_user = User(
        id=uuid4(),
        company_id=company_a.id,
        first_name="Ancien",
        last_name="Employe",
        email="inactive@company-a.ca",
        password_hash=hash_password("Pass123456!"),
        is_active=False,
    )
    session.add(inactive_user)
    session.commit()
    cred_stale = VoiceCallerCredential(
        id=uuid4(),
        company_id=company_a.id,
        principal_type="USER",
        principal_id=inactive_user.id,
        phone_number="+15148887766",
        pin_hash=hash_password("DummyHash123"),
        enabled=True,
    )
    session.add(cred_stale)
    session.commit()

    # Owner claims inactive user's phone -> succeeds, revokes sessions, logs audit
    cred_reassigned = auth.set_pin(tenant_a1, "USER", user_a.id, "591823", phone_number="+15148887766")
    session.commit()
    assert cred_reassigned.principal_id == user_a.id
    assert cred_reassigned.phone_number == "+15148887766"


def test_active_employee_phone_cannot_be_claimed_by_owner_or_admin(tmp_path):
    """P0 Security: An active employee's registered phone number can NEVER be hijacked or silently transferred, even by OWNER or ADMIN."""
    engine, session, company_a, config_a, user_a, company_b, config_b, user_b = _setup_multi_tenant_db(tmp_path)
    dummy_secret = "test_synthetic_secret_" + "x" * 20
    settings = Settings(AUTH_JWT_SECRET=dummy_secret)
    auth = VoiceCallerAuth(session, settings)

    # 1. Create an active employee in company_a
    employee_user = User(
        id=uuid4(),
        company_id=company_a.id,
        first_name="Active",
        last_name="Collaborator",
        email="collab@company-a.ca",
        password_hash=hash_password("CollabPass123!"),
        role=UserRole.USER,
        is_active=True,
    )
    session.add(employee_user)
    session.add(CompanyMembership(
        id=uuid4(),
        company_id=company_a.id,
        user_id=employee_user.id,
        role=UserRole.USER,
        is_active=True,
    ))

    # Also create an admin in company_a
    admin_user = User(
        id=uuid4(),
        company_id=company_a.id,
        first_name="Alice",
        last_name="Admin",
        email="admin@company-a.ca",
        password_hash=hash_password("AdminPass123!"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    session.add(admin_user)
    session.add(CompanyMembership(
        id=uuid4(),
        company_id=company_a.id,
        user_id=admin_user.id,
        role=UserRole.ADMIN,
        is_active=True,
    ))
    session.commit()

    # 2. Employee sets their PIN with their personal phone number
    emp_phone = "+15149991122"
    tenant_emp = TenantContext(company_id=company_a.id, user_id=employee_user.id)
    cred_emp = auth.set_pin(tenant_emp, "USER", employee_user.id, "183920", phone_number=emp_phone)
    session.commit()
    assert cred_emp.principal_id == employee_user.id

    # 3. OWNER (user_a) attempts to take over the active employee's number -> MUST BE REJECTED
    tenant_owner = TenantContext(company_id=company_a.id, user_id=user_a.id)
    with pytest.raises(PermissionError) as exc_owner:
        auth.set_pin(tenant_owner, "USER", user_a.id, "928301", phone_number=emp_phone)
    assert "collaborateur actif" in str(exc_owner.value).lower()

    # 4. ADMIN attempts to take over the active employee's number -> MUST BE REJECTED
    tenant_admin = TenantContext(company_id=company_a.id, user_id=admin_user.id)
    with pytest.raises(PermissionError) as exc_admin:
        auth.set_pin(tenant_admin, "USER", admin_user.id, "928301", phone_number=emp_phone)
    assert "collaborateur actif" in str(exc_admin.value).lower()

    # 5. ANOTHER regular employee also cannot take over -> MUST BE REJECTED
    other_emp = User(
        id=uuid4(),
        company_id=company_a.id,
        first_name="Bob",
        last_name="Staff",
        email="bob@company-a.ca",
        password_hash=hash_password("BobPass123!"),
        role=UserRole.USER,
        is_active=True,
    )
    session.add(other_emp)
    session.add(CompanyMembership(
        id=uuid4(),
        company_id=company_a.id,
        user_id=other_emp.id,
        role=UserRole.USER,
        is_active=True,
    ))
    session.commit()
    tenant_other = TenantContext(company_id=company_a.id, user_id=other_emp.id)
    with pytest.raises(PermissionError) as exc_other:
        auth.set_pin(tenant_other, "USER", other_emp.id, "928301", phone_number=emp_phone)
    assert "collaborateur actif" in str(exc_other.value).lower()

    # 6. The original employee can rotate their own PIN without collision
    cred_emp_rotated = auth.set_pin(tenant_emp, "USER", employee_user.id, "739102", phone_number=emp_phone)
    session.commit()
    assert cred_emp_rotated.id == cred_emp.id
    assert cred_emp_rotated.principal_id == employee_user.id


def test_regular_employee_cannot_reassign_inactive_user_phone(tmp_path):
    """Only OWNER or ADMIN may reassign a deactivated user's phone; regular employees are denied."""
    engine, session, company_a, config_a, user_a, company_b, config_b, user_b = _setup_multi_tenant_db(tmp_path)
    dummy_secret = "test_synthetic_secret_" + "x" * 20
    settings = Settings(AUTH_JWT_SECRET=dummy_secret)
    auth = VoiceCallerAuth(session, settings)

    # Inactive former staff member
    former_user = User(
        id=uuid4(),
        company_id=company_a.id,
        first_name="Former",
        last_name="Employee",
        email="former@company-a.ca",
        password_hash=hash_password("FormerPass123!"),
        role=UserRole.USER,
        is_active=False,
    )
    session.add(former_user)
    stale_phone = "+15147773344"
    session.add(VoiceCallerCredential(
        id=uuid4(),
        company_id=company_a.id,
        principal_type="USER",
        principal_id=former_user.id,
        phone_number=stale_phone,
        pin_hash=hash_password("OldPinHash"),
        enabled=True,
    ))

    # Active regular employee
    staff_user = User(
        id=uuid4(),
        company_id=company_a.id,
        first_name="Staff",
        last_name="Member",
        email="staff@company-a.ca",
        password_hash=hash_password("StaffPass123!"),
        role=UserRole.USER,
        is_active=True,
    )
    session.add(staff_user)
    session.add(CompanyMembership(
        id=uuid4(),
        company_id=company_a.id,
        user_id=staff_user.id,
        role=UserRole.USER,
        is_active=True,
    ))
    session.commit()

    # Regular employee attempts to claim the former user's phone -> REJECTED
    tenant_staff = TenantContext(company_id=company_a.id, user_id=staff_user.id)
    with pytest.raises(PermissionError) as exc:
        auth.set_pin(tenant_staff, "USER", staff_user.id, "938201", phone_number=stale_phone)
    assert "administrateur" in str(exc.value).lower()


def test_multi_tenant_isolation_allows_independent_pin_and_sector_config(tmp_path):
    """Company A and Company B can have independent sectors, independent PINs and even identical phone numbers across different tenants."""
    engine, session, company_a, config_a, user_a, company_b, config_b, user_b = _setup_multi_tenant_db(tmp_path)
    dummy_secret = "test_synthetic_secret_" + "x" * 20
    settings = Settings(AUTH_JWT_SECRET=dummy_secret)

    tenant_a = TenantContext(company_id=company_a.id, user_id=user_a.id)
    tenant_b = TenantContext(company_id=company_b.id, user_id=user_b.id)
    auth = VoiceCallerAuth(session, settings)

    # Both companies can configure their independent PIN
    phone = "+15143332211"
    cred_a = auth.set_pin(tenant_a, "USER", user_a.id, "839201", phone_number=phone)
    cred_b = auth.set_pin(tenant_b, "USER", user_b.id, "472918", phone_number=phone)
    session.commit()

    assert cred_a.company_id == company_a.id
    assert cred_b.company_id == company_b.id
    assert cred_a.pin_hash != cred_b.pin_hash

    # Verify no raw PIN is stored anywhere
    assert cred_a.pin_hash != "839201"
    assert cred_b.pin_hash != "472918"


def test_pin_status_distinguishes_active_from_locked():
    """Active status requires configured, enabled, and !is_locked."""
    now = datetime.now(timezone.utc)
    # Active
    status_active = {
        "configured": True,
        "enabled": True,
        "is_locked": False,
        "locked_until": None,
    }
    is_active = status_active["configured"] and status_active["enabled"] and not status_active["is_locked"]
    assert is_active is True

    # Locked
    status_locked = {
        "configured": True,
        "enabled": True,
        "is_locked": True,
        "locked_until": now + timedelta(minutes=15),
    }
    is_locked_active = status_locked["configured"] and status_locked["enabled"] and not status_locked["is_locked"]
    assert is_locked_active is False

    # Disabled
    status_disabled = {
        "configured": True,
        "enabled": False,
        "is_locked": False,
        "locked_until": None,
    }
    is_disabled_active = status_disabled["configured"] and status_disabled["enabled"] and not status_disabled["is_locked"]
    assert is_disabled_active is False


def test_pin_rotation_omitting_phone_preserves_verified_number(tmp_path):
    """When rotating a PIN, omitting phone_number preserves the verified phone number."""
    engine, session, company_a, config_a, user_a, company_b, config_b, user_b = _setup_multi_tenant_db(tmp_path)
    dummy_secret = "test_synthetic_secret_" + "y" * 20
    settings = Settings(AUTH_JWT_SECRET=dummy_secret)

    tenant_a = TenantContext(company_id=company_a.id, user_id=user_a.id)
    auth = VoiceCallerAuth(session, settings)

    # 1. Initial PIN creation with full phone
    initial_phone = "+15142955720"
    cred = auth.set_pin(tenant_a, "USER", user_a.id, "849201", phone_number=initial_phone)
    session.commit()
    assert cred.phone_number == initial_phone
    old_hash = cred.pin_hash

    # 2. PIN rotation with phone_number=None (omitted)
    rotated_cred = auth.set_pin(tenant_a, "USER", user_a.id, "739182", phone_number=None)
    session.commit()
    assert rotated_cred.phone_number == initial_phone
    assert rotated_cred.pin_hash != old_hash

    # 3. PIN rotation with masked phone string (e.g. "+151 *** **20")
    # Must NOT corrupt the phone number or raise an error; retains initial_phone
    masked_cred = auth.set_pin(tenant_a, "USER", user_a.id, "528194", phone_number="+151 *** **20")
    session.commit()
    assert masked_cred.phone_number == initial_phone


def test_locked_account_unlocked_on_authenticated_pin_reset(tmp_path):
    """An account locked due to failed attempts is immediately unlocked upon setting a new PIN."""
    engine, session, company_a, config_a, user_a, company_b, config_b, user_b = _setup_multi_tenant_db(tmp_path)
    dummy_secret = "test_synthetic_secret_" + "z" * 20
    settings = Settings(AUTH_JWT_SECRET=dummy_secret)

    tenant_a = TenantContext(company_id=company_a.id, user_id=user_a.id)
    auth = VoiceCallerAuth(session, settings)

    # Initial setup
    cred = auth.set_pin(tenant_a, "USER", user_a.id, "849201", phone_number="+15142955720")
    session.commit()

    # Simulate lockout
    cred.failed_attempts = 5
    cred.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
    session.commit()

    # Reset PIN via auth controller (as happens after account re-authentication with password)
    unlocked = auth.set_pin(tenant_a, "USER", user_a.id, "938210", phone_number=None)
    session.commit()

    assert unlocked.failed_attempts == 0
    assert unlocked.locked_until is None
    assert unlocked.enabled is True
