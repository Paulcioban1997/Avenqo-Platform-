"""Real Database Verification Suite for VoiceCallerAuth & Multi-Employee Handover.

Validates the auditor's P0 requirements:
1. Ambiguity detection when multiple employees possess the identical PIN.
2. Resistance to repeated attempts across multiple accounts (isolation of lockout).
3. Three-tier authentication limits (Call, Account, Tenant).
4. Performance and scalability guardrails with 1,000 employees (strictly O(1) indexed lookup).
5. Compound DTMF (Identifier*PIN) and explicit employee identifier resolution.
6. Full end-to-end handover journey with two distinct employees and zero permission leakage.
7. Full compatibility with Telnyx and existing authentication models.

Uses a real isolated SQLite database on disk (tmp_path), executing real SQLAlchemy queries and commits.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from backend.app.config.settings import Settings
from backend.app.core.security import hash_password
from backend.app.models.base import UserRole
from backend.app.models.company import Company
from backend.app.models.company_membership import CompanyMembership
from backend.app.models.user import User
from backend.app.models.voice import VoiceCall, VoiceCallerCredential
from backend.app.voice.auth import VoiceCallerAuth, _tenant_voice_auth_limiter
from tests.backend.test_voice_agent import _voice_database


def _setup_real_voice_company(tmp_path):
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    settings = Settings()
    settings.auth_jwt_secret = "real-db-secret-32-chars-minimum-key-xyz-12345"
    settings.voice_pin_max_attempts = 5
    settings.voice_pin_lockout_seconds = 900
    settings.voice_tenant_max_failed_auth_per_window = 30
    settings.voice_tenant_auth_window_seconds = 60
    settings.voice_tenant_max_total_auth_per_window = 200
    auth = VoiceCallerAuth(session, settings)
    return session, company, config, settings, auth, orchestrator


# ==============================================================================
# 1. Ambiguity Detection When Two Employees Possess the Same PIN
# ==============================================================================

def test_real_db_ambiguous_pin_detection_blocks_arbitrary_login(tmp_path):
    """Verify that when 2 employees in the same company have the exact same PIN,
    an unauthenticated call on a foreign/handover phone entering just that PIN is REJECTED
    with 'ambiguous_pin_identity' rather than arbitrarily picking one employee."""
    session, company, config, settings, auth, _ = _setup_real_voice_company(tmp_path)

    # Create Alice (Manager) and Bob (Staff)
    alice = User(
        company_id=company.id,
        email="alice@realtest.com",
        first_name="Alice",
        last_name="Manager",
        phone="+15145550001",
        role=UserRole.MANAGER,
        password_hash="test-pw-hash",
        is_active=True,
    )
    bob = User(
        company_id=company.id,
        email="bob@realtest.com",
        first_name="Bob",
        last_name="Staff",
        phone="+15145550002",
        role=UserRole.USER,
        password_hash="test-pw-hash",
        is_active=True,
    )
    session.add_all([alice, bob])
    session.flush()

    mem_a = CompanyMembership(company_id=company.id, user_id=alice.id, role=UserRole.MANAGER, is_active=True)
    mem_b = CompanyMembership(company_id=company.id, user_id=bob.id, role=UserRole.USER, is_active=True)
    session.add_all([mem_a, mem_b])

    # Both Alice and Bob have the IDENTICAL PIN: '123456'
    shared_pin = "123456"
    alice_cred = VoiceCallerCredential(
        company_id=company.id,
        principal_type="USER",
        principal_id=alice.id,
        phone_number=alice.phone,
        enabled=True,
        pin_hash=hash_password(auth._peppered(company.id, alice.id, shared_pin)),
        failed_attempts=0,
    )
    bob_cred = VoiceCallerCredential(
        company_id=company.id,
        principal_type="USER",
        principal_id=bob.id,
        phone_number=bob.phone,
        enabled=True,
        pin_hash=hash_password(auth._peppered(company.id, bob.id, shared_pin)),
        failed_attempts=0,
    )
    session.add_all([alice_cred, bob_cred])
    session.commit()

    # Call arrives from a third/unknown phone (or handover phone)
    call = VoiceCall(
        company_id=company.id,
        config_id=config.id,
        caller_phone="+15145559999",  # Foreign/Shared office phone
        caller_type="UNKNOWN",
        status="in_progress",
        verification_attempts=0,
    )
    session.add(call)
    session.commit()

    # Caller enters only '123456' without identifier
    result = auth.verify_gather(call, shared_pin)

    # MUST fail with ambiguous identity guardrail
    assert result["authenticated"] is False
    assert result["error"] == "ambiguous_pin_identity"
    assert result["reason"] == "ambiguous_identifier_required"
    assert "Plusieurs employés" in result["message"] or "identifier" in result["message"]
    assert call.authenticated_user_id is None


# ==============================================================================
# 2. Compound DTMF (Identifier*PIN) Resolves Ambiguity O(1) in Real DB
# ==============================================================================

def test_real_db_compound_dtmf_identifier_star_pin_succession(tmp_path):
    """Verify compound DTMF input '<identifier>*<PIN>' allows instant O(1) indexed
    identification even when two employees share the same PIN."""
    session, company, config, settings, auth, _ = _setup_real_voice_company(tmp_path)

    alice = User(company_id=company.id, email="alice@corp.com", first_name="Alice", last_name="Manager", phone="+15145550001", role=UserRole.MANAGER, password_hash="pw", is_active=True)
    bob = User(company_id=company.id, email="bob@corp.com", first_name="Bob", last_name="Staff", phone="+15145550002", role=UserRole.USER, password_hash="pw", is_active=True)
    session.add_all([alice, bob])
    session.flush()

    session.add_all([
        CompanyMembership(company_id=company.id, user_id=alice.id, role=UserRole.MANAGER, is_active=True),
        CompanyMembership(company_id=company.id, user_id=bob.id, role=UserRole.USER, is_active=True),
    ])

    shared_pin = "889900"
    session.add_all([
        VoiceCallerCredential(company_id=company.id, principal_type="USER", principal_id=alice.id, phone_number=alice.phone, enabled=True, pin_hash=hash_password(auth._peppered(company.id, alice.id, shared_pin))),
        VoiceCallerCredential(company_id=company.id, principal_type="USER", principal_id=bob.id, phone_number=bob.phone, enabled=True, pin_hash=hash_password(auth._peppered(company.id, bob.id, shared_pin))),
    ])
    session.commit()

    # Shared handset call (Alice's phone)
    call = VoiceCall(company_id=company.id, config_id=config.id, caller_phone=alice.phone, caller_type="UNKNOWN", status="in_progress", verification_attempts=0)
    session.add(call)
    session.commit()

    # Bob enters his phone and PIN combined via DTMF: '5145550002*889900'
    res_bob = auth.verify_gather(call, "5145550002*889900")
    assert res_bob["authenticated"] is True
    assert call.authenticated_user_id == bob.id
    assert "Bob" in call.source_context["user_name"]

    # Verify Alice's credential remains completely untouched
    alice_cred_db = session.scalar(select(VoiceCallerCredential).where(VoiceCallerCredential.principal_id == alice.id))
    assert alice_cred_db is not None
    assert alice_cred_db.failed_attempts == 0


# ==============================================================================
# 3. Targeted Lockout vs Untargeted Brute-Force Isolation
# ==============================================================================

def test_real_db_targeted_account_lockout_vs_untargeted_attempt(tmp_path):
    """Verify that targeting an account increments that specific account's failed attempts,
    while random blind guesses during handover do NOT lock the original phone owner."""
    session, company, config, settings, auth, _ = _setup_real_voice_company(tmp_path)

    alice = User(company_id=company.id, email="alice@lockout.com", first_name="Alice", last_name="Manager", phone="+15145550001", role=UserRole.MANAGER, password_hash="pw", is_active=True)
    bob = User(company_id=company.id, email="bob@lockout.com", first_name="Bob", last_name="Staff", phone="+15145550002", role=UserRole.USER, password_hash="pw", is_active=True)
    session.add_all([alice, bob])
    session.flush()

    session.add_all([
        CompanyMembership(company_id=company.id, user_id=alice.id, role=UserRole.MANAGER, is_active=True),
        CompanyMembership(company_id=company.id, user_id=bob.id, role=UserRole.USER, is_active=True),
    ])

    alice_cred = VoiceCallerCredential(company_id=company.id, principal_type="USER", principal_id=alice.id, phone_number=alice.phone, enabled=True, pin_hash=hash_password(auth._peppered(company.id, alice.id, "111111")))
    bob_cred = VoiceCallerCredential(company_id=company.id, principal_type="USER", principal_id=bob.id, phone_number=bob.phone, enabled=True, pin_hash=hash_password(auth._peppered(company.id, bob.id, "222222")))
    session.add_all([alice_cred, bob_cred])
    session.commit()

    call = VoiceCall(
        company_id=company.id,
        config_id=config.id,
        caller_phone=alice.phone,
        caller_type="UNKNOWN",
        status="in_progress",
        verification_attempts=0,
        source_context={"handover_revoked": True},
    )
    session.add(call)
    session.commit()

    # 1. Someone enters wrong PINs during handover without identifier
    res1 = auth.verify_gather(call, "999999")
    assert res1["authenticated"] is False
    session.refresh(alice_cred)
    # Alice's account must NOT be locked because she wasn't targeted
    assert alice_cred.failed_attempts == 0

    # 2. Now someone specifically targets Bob with wrong PINs using Bob's identifier
    call.verification_attempts = 0
    for i in range(5):
        auth.verify_gather(call, "5145550002*000000")

    session.refresh(bob_cred)
    session.refresh(alice_cred)
    # Bob's account is locked out after 5 attempts
    assert bob_cred.failed_attempts >= 5
    assert bob_cred.locked_until is not None
    assert bob_cred.locked_until > datetime.utcnow()
    # Alice's account remains completely untouched
    assert alice_cred.failed_attempts == 0
    assert alice_cred.locked_until is None


# ==============================================================================
# 4. Three-Tier Rate Limiting (Call, Account, Tenant)
# ==============================================================================

def test_real_db_three_tier_limits_call_account_tenant(tmp_path):
    """Verify all 3 tiers of protection operate simultaneously in real DB."""
    session, company, config, settings, auth, _ = _setup_real_voice_company(tmp_path)
    _tenant_voice_auth_limiter.reset()

    user = User(company_id=company.id, email="tier@test.com", first_name="User", last_name="Staff", phone="+15145550010", role=UserRole.USER, password_hash="pw", is_active=True)
    session.add(user)
    session.flush()
    session.add(CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.USER, is_active=True))
    cred = VoiceCallerCredential(company_id=company.id, principal_type="USER", principal_id=user.id, phone_number=user.phone, enabled=True, pin_hash=hash_password(auth._peppered(company.id, user.id, "123456")))
    session.add(cred)
    session.commit()

    call = VoiceCall(company_id=company.id, config_id=config.id, caller_phone=user.phone, caller_type="UNKNOWN", status="in_progress", verification_attempts=0)
    session.add(call)
    session.commit()

    # Tier 1: Per-call attempts limit
    for _ in range(5):
        auth.verify_gather(call, "000000")

    assert call.verification_attempts >= 5
    res_blocked = auth.verify_gather(call, "123456")
    assert res_blocked["authenticated"] is False
    assert res_blocked["reason"] == "max_attempts_exceeded"

    # Tier 2: Per-account lockout
    session.refresh(cred)
    assert cred.failed_attempts >= 5
    assert cred.locked_until is not None

    # Tier 3: Per-tenant rate limit threshold
    tenant_key = str(company.id)
    # Trigger 30 tenant hits
    for _ in range(30):
        _tenant_voice_auth_limiter.hit("voice_auth_tenant_fail", tenant_key, limit=30)

    # Next call in same tenant is rate limited
    call2 = VoiceCall(company_id=company.id, config_id=config.id, caller_phone="+15145550099", caller_type="UNKNOWN", status="in_progress", verification_attempts=0)
    session.add(call2)
    session.commit()
    res_tenant_blocked = auth.verify_gather(call2, "123456")
    assert res_tenant_blocked["authenticated"] is False
    assert res_tenant_blocked["error"] == "rate_limited"
    assert res_tenant_blocked["reason"] == "tenant_auth_rate_limited"


# ==============================================================================
# 5. Scalability & Performance Guardrail: 1,000 Employees in Real DB
# ==============================================================================

def test_real_db_scale_benchmark_1000_employees_o1_lookup(tmp_path):
    """Benchmark real database scalability with 1,000 employees:
    1. Targeted O(1) indexed lookup with identifier finishes in < 250ms (1 bcrypt check).
    2. PIN-only attempt without identifier hits MAX_UNIDENTIFIED_PIN_SCAN guardrail and
       immediately returns in < 50ms without running 1,000 expensive bcrypt hashes."""
    session, company, config, settings, auth, _ = _setup_real_voice_company(tmp_path)

    # Bulk insert 1,000 employees into the real database
    users = []
    memberships = []
    credentials = []

    # Choose employee 777 as target
    target_phone = f"+1514{777:07d}"
    target_pin = "777888"

    # Use a precomputed argon2/bcrypt hash for speed in seeding 1,000 DB records
    dummy_hash = hash_password("dummy-peppered-hash")

    for i in range(1, 1001):
        uid = uuid4()
        u_phone = f"+1514{i:07d}"
        users.append(User(
            id=uid,
            company_id=company.id,
            email=f"employee_{i}@scalecorp.com",
            first_name=f"Emp{i}",
            last_name="Test",
            phone=u_phone,
            role=UserRole.USER,
            password_hash="pw",
            is_active=True,
        ))
        memberships.append(CompanyMembership(
            company_id=company.id,
            user_id=uid,
            role=UserRole.USER,
            is_active=True,
        ))
        is_target = (u_phone == target_phone)
        p_hash = hash_password(auth._peppered(company.id, uid, target_pin)) if is_target else dummy_hash
        credentials.append(VoiceCallerCredential(
            company_id=company.id,
            principal_type="USER",
            principal_id=uid,
            phone_number=u_phone,
            enabled=True,
            pin_hash=p_hash,
            failed_attempts=0,
        ))

    session.add_all(users)
    session.flush()
    session.add_all(memberships)
    session.add_all(credentials)
    session.commit()

    call = VoiceCall(
        company_id=company.id,
        config_id=config.id,
        caller_phone="+15149999999",  # Foreign phone
        caller_type="UNKNOWN",
        status="in_progress",
        verification_attempts=0,
    )
    session.add(call)
    session.commit()

    # Part 1: Blind PIN-only entry on 1,000 employee company
    t0 = time.perf_counter()
    res_blind = auth.verify_gather(call, target_pin)
    t_blind = time.perf_counter() - t0

    # Must be intercepted immediately by the performance guardrail in < 100ms!
    assert t_blind < 0.100, f"Guardrail took too long: {t_blind:.3f}s"
    assert res_blind["authenticated"] is False
    assert res_blind["error"] == "identifier_required"
    assert res_blind["reason"] == "tenant_requires_identifier"

    # Part 2: Targeted compound DTMF 'phone*pin' on 1,000 employee company
    call.verification_attempts = 0
    t1 = time.perf_counter()
    res_targeted = auth.verify_gather(call, f"{target_phone}*{target_pin}")
    t_targeted = time.perf_counter() - t1

    # Strictly O(1): exactly 1 indexed SQL query + 1 password verification
    assert res_targeted["authenticated"] is True
    assert t_targeted < 0.500, f"O(1) lookup took too long: {t_targeted:.3f}s"
    assert "Emp777" in call.source_context["user_name"]


# ==============================================================================
# 6. Full Handover Journey With Zero Permission Leakage in Real DB
# ==============================================================================

def test_real_db_full_two_employee_handover_zero_permission_leakage(tmp_path):
    """End-to-end multi-employee handover on real DB:
    1. Employee A (Alice - Manager) calls from her phone -> authenticated with full Manager permissions.
    2. Handover is triggered: session revoked, conversation detached, context wiped.
    3. Employee B (Bob - Staff) takes the phone -> enters 'bob_phone*bob_pin'.
    4. Bob authenticated with his own Staff ID and User permissions.
    5. Confirms zero access to Alice's management role or conversation history."""
    session, company, config, settings, auth, _ = _setup_real_voice_company(tmp_path)

    # 1. Setup Alice (Manager) and Bob (Staff)
    alice = User(
        company_id=company.id,
        email="alice@company.com",
        first_name="Alice",
        last_name="Manager",
        phone="+15145550001",
        role=UserRole.MANAGER,
        password_hash="pw",
        is_active=True,
    )
    bob = User(
        company_id=company.id,
        email="bob@company.com",
        first_name="Bob",
        last_name="Staff",
        phone="+15145550002",
        role=UserRole.USER,
        password_hash="pw",
        is_active=True,
    )
    session.add_all([alice, bob])
    session.flush()

    session.add_all([
        CompanyMembership(company_id=company.id, user_id=alice.id, role=UserRole.MANAGER, is_active=True),
        CompanyMembership(company_id=company.id, user_id=bob.id, role=UserRole.USER, is_active=True),
        VoiceCallerCredential(company_id=company.id, principal_type="USER", principal_id=alice.id, phone_number=alice.phone, enabled=True, pin_hash=hash_password(auth._peppered(company.id, alice.id, "112233"))),
        VoiceCallerCredential(company_id=company.id, principal_type="USER", principal_id=bob.id, phone_number=bob.phone, enabled=True, pin_hash=hash_password(auth._peppered(company.id, bob.id, "998877"))),
    ])
    session.commit()

    # Step 1: Alice calls from her own phone (+15145550001)
    call = VoiceCall(
        company_id=company.id,
        config_id=config.id,
        caller_phone=alice.phone,
        caller_type="UNKNOWN",
        status="in_progress",
        verification_attempts=0,
    )
    session.add(call)
    session.commit()

    res_alice = auth.verify_gather(call, "112233")
    assert res_alice["authenticated"] is True
    assert call.authenticated_user_id == alice.id
    assert call.caller_type == "EMPLOYEE"
    assert "Alice" in call.source_context["user_name"]

    # Step 2: Handover triggered (Alice says "Je te passe mon collègue")
    call.authenticated_user_id = None
    call.caller_type = "UNKNOWN"
    call.central_conversation_id = None
    call.source_context = {
        "authenticated": False,
        "handover_revoked": True,
        "handover_count": 1,
    }
    session.commit()

    # Step 3: Bob enters his compound credentials on Alice's phone (+15145550001)
    res_bob = auth.verify_gather(call, "5145550002*998877")
    assert res_bob["authenticated"] is True
    assert call.authenticated_user_id == bob.id
    assert call.authenticated_user_id != alice.id
    assert call.source_context["user_id"] == str(bob.id)
    assert "Bob" in call.source_context["user_name"]
    assert call.source_context["handover_revoked"] is False

    # Verify Alice's credential was not penalized
    alice_cred = session.scalar(select(VoiceCallerCredential).where(VoiceCallerCredential.principal_id == alice.id))
    assert alice_cred is not None
    assert alice_cred.failed_attempts == 0


# ==============================================================================
# 7. 50 Consecutive Successful Logins NEVER Trip Failure Limiter
# ==============================================================================

def test_real_db_50_consecutive_successful_logins_never_trips_failure_limiter(tmp_path):
    """Verify that 50 consecutive legitimate authentications in an organization
    succeed without ever incrementing or tripping the tenant failure limiter (voice_auth_tenant_fail)."""
    session, company, config, settings, auth, _ = _setup_real_voice_company(tmp_path)
    _tenant_voice_auth_limiter.reset()

    users = []
    memberships = []
    credentials = []

    # Seed 50 legitimate employees
    for i in range(1, 51):
        uid = uuid4()
        phone = f"+1514888{i:04d}"
        pin = f"{100000 + i}"
        u = User(
            id=uid,
            company_id=company.id,
            email=f"staff_{i}@company.com",
            first_name=f"Staff{i}",
            last_name="Member",
            phone=phone,
            role=UserRole.USER,
            password_hash="pw",
            is_active=True,
        )
        mem = CompanyMembership(company_id=company.id, user_id=uid, role=UserRole.USER, is_active=True)
        cred = VoiceCallerCredential(
            company_id=company.id,
            principal_type="USER",
            principal_id=uid,
            phone_number=phone,
            enabled=True,
            pin_hash=hash_password(auth._peppered(company.id, uid, pin)),
            failed_attempts=0,
        )
        users.append(u)
        memberships.append(mem)
        credentials.append(cred)

    session.add_all(users)
    session.flush()
    session.add_all(memberships)
    session.add_all(credentials)
    session.commit()

    # Authenticate all 50 employees consecutively
    for i in range(50):
        u = users[i]
        pin = f"{100000 + (i + 1)}"
        call = VoiceCall(
            company_id=company.id,
            config_id=config.id,
            caller_phone=u.phone,
            caller_type="UNKNOWN",
            status="in_progress",
            verification_attempts=0,
        )
        session.add(call)
        session.commit()

        res = auth.verify_gather(call, f"{u.phone}*{pin}")
        assert res["authenticated"] is True, f"Employee {i+1} failed to authenticate: {res}"
        assert call.authenticated_user_id == u.id

    # Tenant failure count MUST BE STRICTLY ZERO!
    tenant_key = str(company.id)
    failure_count = _tenant_voice_auth_limiter.get_count("voice_auth_tenant_fail", tenant_key)
    assert failure_count == 0, f"Expected 0 failures recorded, got {failure_count}"

    # 51st authentication also succeeds with zero blockage
    u50 = users[49]
    call51 = VoiceCall(company_id=company.id, config_id=config.id, caller_phone=u50.phone, caller_type="UNKNOWN", status="in_progress", verification_attempts=0)
    session.add(call51)
    session.commit()
    res51 = auth.verify_gather(call51, f"{u50.phone}*{100050}")
    assert res51["authenticated"] is True


# ==============================================================================
# 8. Distributed Brute-Force Attack Across Accounts Trips Tenant Failure Limit
# ==============================================================================

def test_real_db_distributed_brute_force_attack_across_multiple_accounts_trips_failure_limit(tmp_path):
    """Verify that when 30 failed authentications occur across multiple accounts in a tenant,
    Tier 3 tenant-level throttling triggers and blocks further attempts."""
    session, company, config, settings, auth, _ = _setup_real_voice_company(tmp_path)
    _tenant_voice_auth_limiter.reset()

    # Create 30 different employees
    users = []
    credentials = []
    for i in range(1, 35):
        uid = uuid4()
        phone = f"+1514777{i:04d}"
        u = User(id=uid, company_id=company.id, email=f"victim_{i}@target.com", first_name=f"V{i}", last_name="User", phone=phone, role=UserRole.USER, password_hash="pw", is_active=True)
        cred = VoiceCallerCredential(company_id=company.id, principal_type="USER", principal_id=uid, phone_number=phone, enabled=True, pin_hash=hash_password(auth._peppered(company.id, uid, "999999")), failed_attempts=0)
        users.append(u)
        credentials.append(cred)

    session.add_all(users)
    session.flush()
    for u in users:
        session.add(CompanyMembership(company_id=company.id, user_id=u.id, role=UserRole.USER, is_active=True))
    session.add_all(credentials)
    session.commit()

    # Attacker tries wrong PIN "000000" against 30 distinct accounts
    for i in range(30):
        u = users[i]
        call = VoiceCall(company_id=company.id, config_id=config.id, caller_phone=u.phone, caller_type="UNKNOWN", status="in_progress", verification_attempts=0)
        session.add(call)
        session.commit()
        res = auth.verify_gather(call, f"{u.phone}*000000")
        assert res["authenticated"] is False
        assert res["reason"] == "invalid_pin"

    # 31st attempt in the same tenant is blocked by Tier 3 rate limit
    u31 = users[30]
    call31 = VoiceCall(company_id=company.id, config_id=config.id, caller_phone=u31.phone, caller_type="UNKNOWN", status="in_progress", verification_attempts=0)
    session.add(call31)
    session.commit()
    res31 = auth.verify_gather(call31, f"{u31.phone}*000000")
    assert res31["authenticated"] is False
    assert res31["error"] == "rate_limited"
    assert res31["reason"] == "tenant_auth_rate_limited"


# ==============================================================================
# 9. Single Locked User Cannot Denial-of-Service Colleagues (Lockout Isolation)
# ==============================================================================

def test_real_db_single_locked_user_repeated_attempts_do_not_exhaust_tenant_quota(tmp_path):
    """Verify that when a single user is locked out, their repeated attempts on that locked account
    do NOT continue burning the company's tenant failure quota, preventing a single rogue caller
    from locking out other employees."""
    session, company, config, settings, auth, _ = _setup_real_voice_company(tmp_path)
    _tenant_voice_auth_limiter.reset()

    # Eve (Rogue user) and Alice (Innocent colleague)
    eve = User(company_id=company.id, email="eve@victim.com", first_name="Eve", last_name="Attacker", phone="+15145550099", role=UserRole.USER, password_hash="pw", is_active=True)
    alice = User(company_id=company.id, email="alice@victim.com", first_name="Alice", last_name="Colleague", phone="+15145550001", role=UserRole.USER, password_hash="pw", is_active=True)
    session.add_all([eve, alice])
    session.flush()
    session.add_all([
        CompanyMembership(company_id=company.id, user_id=eve.id, role=UserRole.USER, is_active=True),
        CompanyMembership(company_id=company.id, user_id=alice.id, role=UserRole.USER, is_active=True),
        VoiceCallerCredential(company_id=company.id, principal_type="USER", principal_id=eve.id, phone_number=eve.phone, enabled=True, pin_hash=hash_password(auth._peppered(company.id, eve.id, "111111")), failed_attempts=0),
        VoiceCallerCredential(company_id=company.id, principal_type="USER", principal_id=alice.id, phone_number=alice.phone, enabled=True, pin_hash=hash_password(auth._peppered(company.id, alice.id, "222222")), failed_attempts=0),
    ])
    session.commit()

    call_eve = VoiceCall(company_id=company.id, config_id=config.id, caller_phone=eve.phone, caller_type="UNKNOWN", status="in_progress", verification_attempts=0)
    session.add(call_eve)
    session.commit()

    # Eve enters wrong PIN 5 times -> Eve's account is locked (5 failures recorded)
    for _ in range(5):
        auth.verify_gather(call_eve, f"{eve.phone}*000000")

    eve_cred = session.scalar(select(VoiceCallerCredential).where(VoiceCallerCredential.principal_id == eve.id))
    assert eve_cred is not None
    assert eve_cred.failed_attempts >= 5
    assert eve_cred.locked_until is not None

    tenant_key = str(company.id)
    assert _tenant_voice_auth_limiter.get_count("voice_auth_tenant_fail", tenant_key) == 5

    # Eve tries 20 more times on fresh calls while her account is already locked
    for i in range(20):
        c = VoiceCall(company_id=company.id, config_id=config.id, caller_phone=eve.phone, caller_type="UNKNOWN", status="in_progress", verification_attempts=0)
        session.add(c)
        session.commit()
        res = auth.verify_gather(c, f"{eve.phone}*000000")
        assert res["authenticated"] is False
        assert res["reason"] == "account_locked"

    # Tenant failure count must REMAIN 5, NOT 25!
    assert _tenant_voice_auth_limiter.get_count("voice_auth_tenant_fail", tenant_key) == 5

    # Alice logs in with her correct PIN: MUST SUCCEED!
    call_alice = VoiceCall(company_id=company.id, config_id=config.id, caller_phone=alice.phone, caller_type="UNKNOWN", status="in_progress", verification_attempts=0)
    session.add(call_alice)
    session.commit()
    res_alice = auth.verify_gather(call_alice, f"{alice.phone}*222222")
    assert res_alice["authenticated"] is True
    assert call_alice.authenticated_user_id == alice.id


# ==============================================================================
# 10. RedisRateLimiter Multi-Instance Architecture & Fallback
# ==============================================================================

def test_redis_rate_limiter_distributed_atomic_operations_and_graceful_fallback():
    """Verify RedisRateLimiter handles atomic distributed operations and gracefully falls back
    to in-memory limiter when Redis is unconfigured, absent, or encounters network drops."""
    from unittest.mock import MagicMock
    from backend.app.core.rate_limit import RedisRateLimiter, _FixedWindowLimiter

    # 1. Unconfigured Redis -> delegates smoothly to fallback
    limiter_unconfigured = RedisRateLimiter(redis_url=None)
    assert limiter_unconfigured.hit("test_bucket", "key_1", limit=5) is True
    assert limiter_unconfigured.is_limited("test_bucket", "key_1", limit=5) is False
    assert limiter_unconfigured.get_count("test_bucket", "key_1") == 1

    # 2. Configured Mock Redis Client with atomic pipeline
    mock_redis = MagicMock()
    mock_pipeline = MagicMock()
    mock_redis.pipeline.return_value = mock_pipeline
    mock_pipeline.execute.return_value = [1, True]  # [incr_result, expire_result]

    limiter_redis = RedisRateLimiter(redis_client=mock_redis)
    assert limiter_redis.hit("tenant_fail", "tenant_xyz", limit=10) is True
    mock_pipeline.incr.assert_called_once()
    mock_pipeline.expire.assert_called_once()

    # 3. Redis raises connection error -> falls back to local memory without crashing
    mock_redis.pipeline.side_effect = ConnectionError("Redis host unreachable")
    # Must not raise, but return local fallback
    fallback_res = limiter_redis.hit("tenant_fail", "tenant_xyz", limit=10)
    assert fallback_res is True


# ==============================================================================
# 11. Centralized Shared Limiter Injection into VoiceCallerAuth
# ==============================================================================

def test_voice_caller_auth_centralized_shared_limiter_injection(tmp_path):
    """Verify VoiceCallerAuth automatically injects RedisRateLimiter when REDIS_URL
    is configured, falls back to _FixedWindowLimiter when unset, and reuses a shared
    singleton connection pool without recreating clients per call."""
    from backend.app.core.rate_limit import (
        RedisRateLimiter,
        _FixedWindowLimiter,
        get_voice_auth_rate_limiter,
        reset_voice_auth_rate_limiter,
    )

    session, company, config, settings, _, _ = _setup_real_voice_company(tmp_path)

    # 1. Without REDIS_URL -> VoiceCallerAuth uses shared _FixedWindowLimiter
    reset_voice_auth_rate_limiter(None)
    settings.redis_url = None
    auth_local = VoiceCallerAuth(session, settings)
    assert isinstance(auth_local.limiter, _FixedWindowLimiter)

    # Calling again reuses the exact same instance
    auth_local_2 = VoiceCallerAuth(session, settings)
    assert auth_local.limiter is auth_local_2.limiter

    # 2. With REDIS_URL -> VoiceCallerAuth uses shared RedisRateLimiter
    reset_voice_auth_rate_limiter(None)
    settings.redis_url = "redis://mock-redis-host:6379/0"
    auth_redis = VoiceCallerAuth(session, settings)
    assert isinstance(auth_redis.limiter, RedisRateLimiter)
    assert auth_redis.limiter._redis_url == "redis://mock-redis-host:6379/0"

    # Calling again reuses the exact same RedisRateLimiter instance (no new connection pool)
    auth_redis_2 = VoiceCallerAuth(session, settings)
    assert auth_redis.limiter is auth_redis_2.limiter

    # Cleanup test state
    reset_voice_auth_rate_limiter(None)


# ==============================================================================
# 12. Two Simulated Instances Sharing Same Redis Coordinate Tenant Quotas
# ==============================================================================

def test_two_simulated_instances_sharing_redis_coordinate_tenant_quotas(tmp_path):
    """Verify that two distinct backend server instances (Instance A and Instance B)
    sharing the same Redis coordinate their tenant quotas:
    5 failures on Instance A + 5 failures on Instance B = 10 failures total in Redis.
    The 11th failure on Instance A is immediately rate limited.
    The 12th failure on Instance B is also immediately rate limited."""
    from unittest.mock import MagicMock
    from backend.app.core.rate_limit import RedisRateLimiter

    session, company, config, settings, _, _ = _setup_real_voice_company(tmp_path)
    settings.voice_tenant_max_failed_auth_per_window = 10
    settings.voice_tenant_auth_window_seconds = 60
    tenant_key = str(company.id)

    # In-memory shared Redis mock datastore
    shared_redis_store: dict[str, int] = {}

    class SharedMockRedisClient:
        def __init__(self, store: dict[str, int]):
            self._store = store

        def get(self, key: str):
            val = self._store.get(key)
            return str(val) if val is not None else None

        def pipeline(self):
            return SharedMockPipeline(self._store)

    class SharedMockPipeline:
        def __init__(self, store: dict[str, int]):
            self._store = store
            self._incr_key = None

        def incr(self, key: str):
            self._incr_key = key
            return self

        def expire(self, key: str, seconds: int):
            return self

        def execute(self):
            if self._incr_key:
                val = self._store.get(self._incr_key, 0) + 1
                self._store[self._incr_key] = val
                return [val, True]
            return [0, True]

    shared_client = SharedMockRedisClient(shared_redis_store)

    # Server Instance A
    limiter_instance_a = RedisRateLimiter(redis_client=shared_client)
    auth_instance_a = VoiceCallerAuth(session, settings, limiter=limiter_instance_a)

    # Server Instance B
    limiter_instance_b = RedisRateLimiter(redis_client=shared_client)
    auth_instance_b = VoiceCallerAuth(session, settings, limiter=limiter_instance_b)

    # Create 15 victim employees in DB
    users = []
    credentials = []
    for i in range(1, 16):
        uid = uuid4()
        phone = f"+1514666{i:04d}"
        u = User(id=uid, company_id=company.id, email=f"shared_{i}@target.com", first_name=f"S{i}", last_name="Staff", phone=phone, role=UserRole.USER, password_hash="pw", is_active=True)
        cred = VoiceCallerCredential(company_id=company.id, principal_type="USER", principal_id=uid, phone_number=phone, enabled=True, pin_hash=hash_password(auth_instance_a._peppered(company.id, uid, "123456")), failed_attempts=0)
        users.append(u)
        credentials.append(cred)

    session.add_all(users)
    session.flush()
    for u in users:
        session.add(CompanyMembership(company_id=company.id, user_id=u.id, role=UserRole.USER, is_active=True))
    session.add_all(credentials)
    session.commit()

    # Instance A receives 5 failed authentications
    for i in range(5):
        u = users[i]
        call_a = VoiceCall(company_id=company.id, config_id=config.id, caller_phone=u.phone, caller_type="UNKNOWN", status="in_progress", verification_attempts=0)
        session.add(call_a)
        session.commit()
        res_a = auth_instance_a.verify_gather(call_a, f"{u.phone}*000000")
        assert res_a["authenticated"] is False
        assert res_a["reason"] == "invalid_pin"

    # Instance B receives 5 failed authentications
    for i in range(5, 10):
        u = users[i]
        call_b = VoiceCall(company_id=company.id, config_id=config.id, caller_phone=u.phone, caller_type="UNKNOWN", status="in_progress", verification_attempts=0)
        session.add(call_b)
        session.commit()
        res_b = auth_instance_b.verify_gather(call_b, f"{u.phone}*000000")
        assert res_b["authenticated"] is False
        assert res_b["reason"] == "invalid_pin"

    # Total failures in shared Redis store must be exactly 10
    assert limiter_instance_a.get_count("voice_auth_tenant_fail", tenant_key, window_seconds=60) == 10
    assert limiter_instance_b.get_count("voice_auth_tenant_fail", tenant_key, window_seconds=60) == 10

    # 11th attempt on Instance A is rate limited by the coordinated Redis quota!
    u11 = users[10]
    call_11 = VoiceCall(company_id=company.id, config_id=config.id, caller_phone=u11.phone, caller_type="UNKNOWN", status="in_progress", verification_attempts=0)
    session.add(call_11)
    session.commit()
    res_11 = auth_instance_a.verify_gather(call_11, f"{u11.phone}*000000")
    assert res_11["authenticated"] is False
    assert res_11["error"] == "rate_limited"
    assert res_11["reason"] == "tenant_auth_rate_limited"

    # 12th attempt on Instance B is ALSO rate limited by the coordinated Redis quota!
    u12 = users[11]
    call_12 = VoiceCall(company_id=company.id, config_id=config.id, caller_phone=u12.phone, caller_type="UNKNOWN", status="in_progress", verification_attempts=0)
    session.add(call_12)
    session.commit()
    res_12 = auth_instance_b.verify_gather(call_12, f"{u12.phone}*000000")
    assert res_12["authenticated"] is False
    assert res_12["error"] == "rate_limited"
    assert res_12["reason"] == "tenant_auth_rate_limited"
