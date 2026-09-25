"""Check active modules and enum values in production for gauffy95."""
import os
import psycopg2

url = os.environ["DATABASE_PUBLIC_URL"]
conn = psycopg2.connect(url)
cur = conn.cursor()

company_id = "9c97cb94-e9f9-46fb-afd4-8a1d21019cff"  # gauffy95's company (Produits_Ero)

# Check the enum values for company_module_status
cur.execute("""
    SELECT enumlabel FROM pg_enum
    JOIN pg_type ON pg_type.oid = pg_enum.enumtypid
    WHERE pg_type.typname = 'company_module_status'
    ORDER BY enumsortorder
""")
enum_vals = [r[0] for r in cur.fetchall()]
print(f"=== company_module_status enum values === {enum_vals}")

# Get all company_modules for gauffy's company
cur.execute("""
    SELECT m.code, m.name, cm.status, cm.activated_at
    FROM company_modules cm
    JOIN modules m ON m.id = cm.module_id
    WHERE cm.company_id = %s
    ORDER BY cm.status, m.code
""", (company_id,))
mods = cur.fetchall()
print(f"=== All company_modules (gauffy) ({len(mods)} total) ===")
for m in mods:
    print(f"  code={m[0]}  name={m[1]}  status={m[2]}  activated={m[3]}")

conn.close()
