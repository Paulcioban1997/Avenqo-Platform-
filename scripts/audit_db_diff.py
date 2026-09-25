import os
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

print("Importing models...")
from backend.app.models.base import Base
import backend.app.models
print("Models imported.")

from sqlalchemy import create_engine, inspect

raw_url = os.environ.get(
    "DATABASE_PUBLIC_URL",
    "postgresql://postgres:aVxFamcMziEnMoleBZCYdkLpOELxLatB@tramway.proxy.rlwy.net:25367/railway"
)
if raw_url.startswith("postgresql://"):
    raw_url = raw_url.replace("postgresql://", "postgresql+psycopg2://", 1)

print("Connecting to DB...")
engine = create_engine(raw_url, connect_args={"connect_timeout": 10})
inspector = inspect(engine)

print("Fetching DB schema...")
db_tables = set(inspector.get_table_names(schema="public"))
model_tables = set(Base.metadata.tables.keys())

print("\n=== Tables in Models but NOT in DB ===")
for t in sorted(model_tables - db_tables):
    print("  Missing table:", t)

print("\n=== Column Differences for Existing Tables ===")
missing_columns = []
for table_name in sorted(model_tables.intersection(db_tables)):
    db_cols = {c["name"]: c for c in inspector.get_columns(table_name, schema="public")}
    model_table = Base.metadata.tables[table_name]
    for col in model_table.columns:
        if col.name not in db_cols:
            print(f"  Table '{table_name}' MISSING column: {col.name} ({col.type})")
            missing_columns.append((table_name, col))

print(f"\nTotal missing columns: {len(missing_columns)}")
