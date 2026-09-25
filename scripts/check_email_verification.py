"""Check ciomir@gmail.com verification status and token environment in production DB."""
import os
from sqlalchemy import create_engine, text

url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not url:
    print("ERROR: no DATABASE_PUBLIC_URL or DATABASE_URL env var found")
    exit(1)

engine = create_engine(url)
with engine.connect() as conn:
    # 1. Check user verification status
    rows = conn.execute(
        text("SELECT email, email_verified_at FROM users WHERE email='ciomir@gmail.com'")
    ).fetchall()
    print("=== User verification status ===")
    for r in rows:
        print(f"  email={r[0]}  verified_at={r[1]}")

    # 2. Check active EMAIL_VERIFICATION tokens for this user
    rows2 = conn.execute(
        text("""
            SELECT at.purpose, at.created_at, at.expires_at, at.used_at
            FROM account_tokens at
            JOIN users u ON u.id = at.user_id
            WHERE u.email = 'ciomir@gmail.com'
              AND at.purpose = 'EMAIL_VERIFICATION'
            ORDER BY at.created_at DESC
            LIMIT 3
        """)
    ).fetchall()
    print("\n=== Recent EMAIL_VERIFICATION tokens ===")
    for r in rows2:
        print(f"  purpose={r[0]}  created={r[1]}  expires={r[2]}  used={r[3]}")

    # 3. Health check environment
    try:
        env_row = conn.execute(text("SELECT current_database(), version()")).fetchone()
        print(f"\n=== DB Info ===")
        if env_row is not None:
            print(f"  database={env_row[0]}  pg_version={env_row[1][:40]}")
    except Exception as e:
        print(f"  (env check failed: {e})")
