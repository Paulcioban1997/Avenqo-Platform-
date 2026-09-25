import os
import psycopg2

url = os.environ["DATABASE_PUBLIC_URL"]
conn = psycopg2.connect(url)
cur = conn.cursor()

# 1. User verification status
cur.execute("SELECT email, email_verified_at FROM users WHERE email='ciomir@gmail.com'")
rows = cur.fetchall()
print("=== User ===")
for r in rows:
    print(f"  email={r[0]}  verified_at={r[1]}")

# 2. Tokens
cur.execute("""
    SELECT purpose, created_at, expires_at, used_at
    FROM account_tokens
    WHERE user_id = (SELECT id FROM users WHERE email = 'ciomir@gmail.com')
    ORDER BY created_at DESC
    LIMIT 3
""")
rows2 = cur.fetchall()
print("=== Tokens ===")
for r in rows2:
    print(f"  purpose={r[0]}  created={r[1]}  expires={r[2]}  used={r[3]}")

# 3. DB name
cur.execute("SELECT current_database()")
print("=== DB ===", cur.fetchone())

conn.close()
