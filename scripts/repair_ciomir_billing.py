"""
Idempotent repair: create BillingAccount for ciomir@gmail.com in sandbox
if and only if:
  - the user exists
  - their email is verified
  - they have a company
  - they do NOT already have a BillingAccount

Plan assigned: 'demo' (the default for a new account at this stage).
No Stripe subscription is created — this is a free-trial demo account.
"""
import os
import uuid
from datetime import datetime, timezone, timedelta
import psycopg2

url = os.environ["DATABASE_PUBLIC_URL"]
conn = psycopg2.connect(url)
cur = conn.cursor()

# 1. Verify preconditions
cur.execute("""
    SELECT u.id, u.company_id, u.email_verified_at,
           ba.id AS ba_id
    FROM users u
    LEFT JOIN billing_accounts ba ON ba.company_id = u.company_id
    WHERE u.email = 'ciomir@gmail.com'
""")
row = cur.fetchone()
if not row:
    print("ERROR: ciomir@gmail.com not found in sandbox")
    conn.close()
    exit(1)

user_id, company_id, verified_at, ba_id = row
print(f"User: id={user_id}  company_id={company_id}  verified_at={verified_at}  billing_account_id={ba_id}")

if ba_id is not None:
    print("OK: BillingAccount already exists — nothing to do.")
    conn.close()
    exit(0)

if verified_at is None:
    print("SKIP: Email not yet verified — BillingAccount will be created upon verification if the app supports it.")
    conn.close()
    exit(0)

# 2. Create BillingAccount (idempotent: only if absent)
new_ba_id = str(uuid.uuid4())
now = datetime.now(timezone.utc)
trial_end = now + timedelta(days=14)

cur.execute("""
    INSERT INTO billing_accounts
        (id, company_id, plan_code, status, current_period_end, cancel_at_period_end, created_at, updated_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (company_id) DO NOTHING
""", (new_ba_id, company_id, "demo", "trialing", trial_end, False, now, now))

conn.commit()
print(f"CREATED BillingAccount id={new_ba_id}  plan=demo  status=trialing  trial_end={trial_end}")

# 3. Verify
cur.execute("SELECT id, plan_code, status FROM billing_accounts WHERE company_id = %s", (company_id,))
result = cur.fetchone()
print(f"VERIFY: {result}")
conn.close()
