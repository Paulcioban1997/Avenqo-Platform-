import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, ".")
from backend.app.models import Base

db_path = Path("var/avenqo.db")
if db_path.exists():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    for table_name, table in Base.metadata.tables.items():
        existing_cols = [r[1] for r in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()]
        if not existing_cols:
            continue
        for col in table.columns:
            if col.name not in existing_cols:
                col_type = "TEXT"
                default_clause = ""
                type_str = str(col.type).upper()
                if any(t in type_str for t in ("INT", "BOOL")):
                    col_type = "INTEGER"
                    default_clause = "DEFAULT 0" if not col.nullable else ""
                elif "JSON" in type_str:
                    col_type = "JSON"
                    default_clause = "DEFAULT '[]'" if not col.nullable else ""
                elif any(t in type_str for t in ("VARCHAR", "STRING", "TEXT", "DATE")):
                    col_type = "TEXT"
                sql = f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type} {default_clause}"
                print("Running:", sql)
                try:
                    cursor.execute(sql)
                except Exception as e:
                    print("Warning:", e)
    conn.commit()
    conn.close()
    print("Schema synchronization complete!")
