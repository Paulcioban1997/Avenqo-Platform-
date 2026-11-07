"""Read-only audit script for Produits_Ero company in Production database.
Strictly read-only: does not execute any UPDATE, INSERT, DELETE, or ALTER.
"""
import json
import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor

db_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL")
if not db_url:
    print("ERROR: DATABASE_URL or DATABASE_PUBLIC_URL not found in environment.", file=sys.stderr)
    sys.exit(1)

# Ensure connection is strictly read-only
conn = psycopg2.connect(db_url)
conn.set_session(readonly=True)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=== AUDIT READ-ONLY PRODUITS_ERO ===")

# 1. Search company
cur.execute("""
    SELECT id, name, subscription_plan, status, created_at, updated_at
    FROM companies
    WHERE name ILIKE '%ero%' OR id = '9c97cb94-e9f9-46fb-afd4-8a1d21019cff'
""")
companies = cur.fetchall()
print(f"\n[COMPANIES MATCHED] ({len(companies)}):")
target_company_id = None
for c in companies:
    c_dict = dict(c)
    # Convert dates to isoformat
    for k, v in c_dict.items():
        if hasattr(v, "isoformat"):
            c_dict[k] = v.isoformat()
    print(json.dumps(c_dict, default=str, indent=2))
    target_company_id = c["id"]

if not target_company_id:
    print("No matching company found! Listing all companies:")
    cur.execute("SELECT id, name, subscription_plan, status FROM companies LIMIT 10")
    for c in cur.fetchall():
        print(dict(c))
    conn.close()
    sys.exit(0)

# 2. Billing accounts columns and query
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'billing_accounts'
    ORDER BY ordinal_position
""")
b_cols = [r["column_name"] for r in cur.fetchall()]
print(f"\n[BILLING_ACCOUNTS COLUMNS]: {b_cols}")

cur.execute("""
    SELECT *
    FROM billing_accounts
    WHERE company_id = %s
""", (target_company_id,))
billing = cur.fetchall()
print(f"\n[BILLING ACCOUNTS] ({len(billing)}):")
for b in billing:
    b_dict = dict(b)
    for k, v in b_dict.items():
        if hasattr(v, "isoformat"):
            b_dict[k] = v.isoformat()
    print(json.dumps(b_dict, default=str, indent=2))

# 3. Company modules
# Let's inspect column names in company_modules
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'company_modules'
    ORDER BY ordinal_position
""")
cols = [r["column_name"] for r in cur.fetchall()]
print(f"\n[COMPANY_MODULES COLUMNS]: {cols}")

cur.execute(f"""
    SELECT *
    FROM company_modules
    WHERE company_id = %s
""", (target_company_id,))
modules = cur.fetchall()
print(f"\n[COMPANY_MODULES] ({len(modules)}):")
for m in modules:
    m_dict = dict(m)
    for k, v in m_dict.items():
        if hasattr(v, "isoformat"):
            m_dict[k] = v.isoformat()
    print(json.dumps(m_dict, default=str, indent=2))

# 4. Users in company
cur.execute("""
    SELECT id, email, role, is_platform_admin, is_active, created_at
    FROM users
    WHERE company_id = %s
""", (target_company_id,))
users = cur.fetchall()
print(f"\n[USERS IN COMPANY] ({len(users)}):")
for u in users:
    u_dict = dict(u)
    for k, v in u_dict.items():
        if hasattr(v, "isoformat"):
            u_dict[k] = v.isoformat()
    print(json.dumps(u_dict, default=str, indent=2))

# 5. Check audit logs or history if available
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' AND table_name ILIKE '%audit%'
""")
audit_tables = [r["table_name"] for r in cur.fetchall()]
print(f"\n[AUDIT TABLES]: {audit_tables}")

conn.close()
print("\n=== AUDIT COMPLETE (0 WRITES) ===")
