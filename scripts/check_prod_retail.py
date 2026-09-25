"""Check datasets table schema and content for Data Hub 500 error."""
import os
import psycopg2

db_url = os.environ["DATABASE_PUBLIC_URL"]
conn = psycopg2.connect(db_url)
cur = conn.cursor()

COMPANY_ID = "9c97cb94-e9f9-46fb-afd4-8a1d21019cff"

# Get datasets schema
cur.execute("""
    SELECT column_name, data_type FROM information_schema.columns
    WHERE table_name = 'datasets'
    ORDER BY ordinal_position
""")
cols = cur.fetchall()
print("=== datasets columns ===")
for c in cols:
    print(f"  {c[0]}: {c[1]}")

# Get dataset rows
col_names = [c[0] for c in cols]
cur.execute("SELECT * FROM datasets WHERE company_id = %s ORDER BY id DESC LIMIT 5", (COMPANY_ID,))
rows = cur.fetchall()
print(f"\n=== datasets rows ({len(rows)}) ===")
for r in rows:
    row_dict = dict(zip(col_names, r))
    print(f"  {row_dict}")

conn.close()
