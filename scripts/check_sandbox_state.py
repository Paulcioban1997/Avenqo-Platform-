"""
Check sandbox DB:
1. List test users (non-gauffy, non-ciomir) with verified emails and billing accounts
2. Check ciomir's BillingAccount provisioning issue
3. Check what demo users have active modules
"""
import os
import psycopg2

url = os.environ["DATABASE_PUBLIC_URL"]
conn = psycopg2.connect(url)
cur = conn.cursor()

print("=== DB Name ===")
cur.execute("SELECT current_database()")
print(cur.fetchone())

print("\n=== Users with verified email and BillingAccount (sandbox) ===")
cur.execute("""
    SELECT u.email, u.id, u.company_id, ba.plan_code, ba.status, ba.stripe_customer_id
    FROM users u
    JOIN billing_accounts ba ON ba.company_id = u.company_id
    WHERE u.email_verified_at IS NOT NULL
    ORDER BY u.created_at DESC
    LIMIT 10
""")
for r in cur.fetchall():
    print(f"  email={r[0]}  plan={r[3]}  status={r[4]}  stripe_cust={r[5]}")

print("\n=== ciomir@gmail.com full state ===")
cur.execute("""
    SELECT u.id, u.company_id, u.email_verified_at,
           ba.id AS ba_id, ba.plan_code, ba.status
    FROM users u
    LEFT JOIN billing_accounts ba ON ba.company_id = u.company_id
    WHERE u.email = 'ciomir@gmail.com'
""")
row = cur.fetchone()
if row:
    print(f"  user_id={row[0]}  company_id={row[1]}  verified_at={row[2]}")
    print(f"  billing_account_id={row[3]}  plan={row[4]}  status={row[5]}")
else:
    print("  NOT FOUND")

print("\n=== Users WITHOUT BillingAccount ===")
cur.execute("""
    SELECT u.email, u.company_id, u.created_at
    FROM users u
    LEFT JOIN billing_accounts ba ON ba.company_id = u.company_id
    WHERE ba.id IS NULL
    ORDER BY u.created_at DESC
    LIMIT 10
""")
for r in cur.fetchall():
    print(f"  email={r[0]}  company_id={r[1]}  created={r[2]}")

conn.close()
