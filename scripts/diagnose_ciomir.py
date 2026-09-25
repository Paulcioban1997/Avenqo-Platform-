"""Check ciomir registration date vs billing_accounts creation, and company status."""
import os
import psycopg2

url = os.environ["DATABASE_PUBLIC_URL"]
conn = psycopg2.connect(url)
cur = conn.cursor()

cur.execute("""
    SELECT u.email, u.created_at, u.email_verified_at,
           c.id AS company_id, c.name AS company_name, c.subscription_plan, c.status AS company_status,
           c.created_at AS company_created_at
    FROM users u
    JOIN companies c ON c.id = u.company_id
    WHERE u.email = 'ciomir@gmail.com'
""")
row = cur.fetchone()
if row:
    print("=== ciomir user + company ===")
    print(f"  email={row[0]}  user_created={row[1]}  verified_at={row[2]}")
    print(f"  company_id={row[3]}  company_name={row[4]}")
    print(f"  subscription_plan={row[5]}  company_status={row[6]}  company_created={row[7]}")
else:
    print("NOT FOUND")

# Check if billing_accounts has a unique constraint on company_id
cur.execute("""
    SELECT constraint_name, constraint_type
    FROM information_schema.table_constraints
    WHERE table_name = 'billing_accounts'
""")
print("\n=== billing_accounts constraints ===")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

conn.close()
