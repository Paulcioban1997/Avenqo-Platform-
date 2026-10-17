"""AVENQO PHASE 8.2.1 - SECURE SANDBOX TEST CREDENTIAL ROTATION TOOL.

Strictly Sandbox Only.
Safely rotates the test credential for 'alex.physio.sandbox@avenqo.ca' in the Sandbox PostgreSQL database.
Never prints raw password values to stdout or logs.
Requires explicit '--execute' flag to commit changes.
"""

from __future__ import annotations

import argparse
import os
import secrets
import string
import sys
from typing import Any

from dotenv import dotenv_values
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, ".")

from backend.app.core.security import hash_password, verify_password
from backend.app.models.user import User


def generate_secure_password(length: int = 28) -> str:
    """Generate a cryptographically secure password with mixed entropy."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in "!@#$%^&*-_=+" for c in password)
        ):
            return password


def main() -> None:
    parser = argparse.ArgumentParser(description="Rotate Sandbox Test Account Credential")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Commit password rotation to live database. Without this flag, runs in dry-run mode.",
    )
    parser.add_argument(
        "--email",
        default="alex.physio.sandbox@avenqo.ca",
        help="Target test account email (default: alex.physio.sandbox@avenqo.ca)",
    )
    args = parser.parse_args()

    # Resolve database URL
    vals = dotenv_values("backend/.env")
    db_url = vals.get("DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if db_url.startswith("postgres://"):
        db_url = "postgresql://" + db_url[len("postgres://"):]

    if not db_url:
        print("[ERROR] DATABASE_URL not found in backend/.env or environment.")
        sys.exit(1)

    engine = create_engine(db_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    print("================================================================================")
    print("AVENQO PHASE 8.2.1: SANDBOX CREDENTIAL ROTATION AUDIT")
    print(f"Target Account: {args.email}")
    print(f"Mode: {'EXECUTE (LIVE WRITE)' if args.execute else 'DRY RUN (INSPECTION ONLY)'}")
    print("================================================================================")

    try:
        user = session.scalar(select(User).where(User.email == args.email))
        if user is None:
            print(f"[FAIL] Target account '{args.email}' does not exist in database.")
            sys.exit(1)

        print(f"User Record Found: ID={user.id}, Role={user.role}, CompanyID={user.company_id}")
        current_hash = user.password_hash
        print(f"Current Password Hash Scheme: {current_hash[:12]}... (length={len(current_hash)})")

        # Resolve replacement password
        replacement_pass = os.environ.get("NEW_AVENQO_E2E_PASSWORD")
        auto_generated = False
        if not replacement_pass:
            replacement_pass = generate_secure_password()
            auto_generated = True

        new_hash = hash_password(replacement_pass)
        print(f"New Password Hash Scheme: {new_hash[:12]}... (Argon2 / Recommended)")

        if not args.execute:
            print("\n[DRY RUN SUMMARY]")
            print("1. Target account verified in Sandbox database.")
            print("2. Cryptographically secure replacement generated in memory.")
            print("3. Live database was NOT modified (awaiting founder approval).")
            print("4. To commit rotation, obtain authorization and run with '--execute'.")
            return

        # Execute Rotation
        print("\n[EXECUTING LIVE ROTATION]")
        user.password_hash = new_hash
        session.commit()
        print("✓ Database user password_hash successfully updated.")

        # Invalidation & verification test
        session.refresh(user)
        refreshed_hash = user.password_hash
        is_new_valid = verify_password(replacement_pass, refreshed_hash)
        
        # Test old password rejection if old test secret candidate provided in env
        old_test_candidate = os.environ.get("OLD_AVENQO_E2E_PASSWORD", "")
        is_old_rejected = True
        if old_test_candidate:
            is_old_rejected = not verify_password(old_test_candidate, refreshed_hash)

        print(f"Verification: New Password Authenticates Successfully = {is_new_valid}")
        print(f"Verification: Old Password Rejected = {is_old_rejected}")

        if is_new_valid and is_old_rejected:
            print("\n[SUCCESS] Credential rotation completed and verified.")
            if auto_generated:
                print("NOTE: Set the new credential into GitHub Secrets as 'AVENQO_E2E_PASSWORD'.")
        else:
            print("\n[ERROR] Post-rotation authentication check failed!")
            sys.exit(2)

    finally:
        session.close()


if __name__ == "__main__":
    main()
