import os
import psycopg2

db_url = os.environ.get(
    "DATABASE_PUBLIC_URL",
    "postgresql://postgres:aVxFamcMziEnMoleBZCYdkLpOELxLatB@tramway.proxy.rlwy.net:25367/railway"
)

conn = psycopg2.connect(db_url)
cur = conn.cursor()

cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='commerce_connections' ORDER BY ordinal_position")
cols = cur.fetchall()
print("=== commerce_connections columns ===")
for col, dtype in cols:
    print(f"  {col}: {dtype}")

cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
tables = [r[0] for r in cur.fetchall()]
print("\n=== Public tables ===", sorted(tables))

try:
    cur.execute("SELECT version_num FROM alembic_version")
    print("\n=== Alembic versions ===", cur.fetchall())
except Exception as e:
    print("\nAlembic error:", e)

conn.close()
