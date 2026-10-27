"""CLI script to safely establish role separation and transfer table ownership to avenqo_owner.

Ensures that avenqo_migrate has owner-level privileges via avenqo_owner membership,
allowing smooth Alembic migrations without granting superuser rights or runtime DDL rights.
Never logs passwords or connection strings.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, inspect, text
from backend.app.services.postgres_app_role import (
    APP_ROLE,
    MIGRATE_ROLE,
    OWNER_ROLE,
    ensure_application_roles,
)


def reassign_schema_objects(engine) -> dict[str, int]:
    """Reassign all public tables, sequences, and enums to avenqo_owner."""
    with engine.begin() as conn:
        # 1. Ensure roles and base permissions
        ensure_application_roles(conn)
        conn.execute(text(f"ALTER ROLE {MIGRATE_ROLE} INHERIT"))
        conn.execute(text(f"GRANT {OWNER_ROLE} TO {MIGRATE_ROLE}"))

        # 2. Reassign all tables in public schema
        inspector = inspect(conn)
        tables = inspector.get_table_names(schema="public")
        for table in tables:
            conn.execute(text(f'ALTER TABLE public."{table}" OWNER TO {OWNER_ROLE}'))

        # 3. Reassign sequences
        sequences = inspector.get_sequence_names(schema="public") if hasattr(inspector, "get_sequence_names") else []
        for seq in sequences:
            conn.execute(text(f'ALTER SEQUENCE public."{seq}" OWNER TO {OWNER_ROLE}'))

        # 4. Reassign custom types and enums
        rows = conn.execute(text("""
            SELECT distinct t.typname 
            FROM pg_type t 
            JOIN pg_enum e ON t.oid = e.enumtypid 
            JOIN pg_namespace n ON t.typnamespace = n.oid 
            WHERE n.nspname = 'public'
        """)).fetchall()
        for row in rows:
            typ = row[0]
            conn.execute(text(f'ALTER TYPE public."{typ}" OWNER TO {OWNER_ROLE}'))

    return {
        "tables_transferred": len(tables),
        "sequences_transferred": len(sequences),
        "enums_transferred": len(rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--admin-database-url",
        default=os.environ.get("ADMIN_DATABASE_URL") or os.environ.get("DATABASE_URL"),
        help="Superuser or admin connection URL with ALTER privilege on public schema.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Inspect only, do not alter.")
    args = parser.parse_args()

    if not args.admin_database_url:
        print("ADMIN_DATABASE_URL or DATABASE_URL required.", file=sys.stderr)
        return 1

    engine = create_engine(args.admin_database_url)
    
    if args.dry_run:
        with engine.connect() as conn:
            inspector = inspect(conn)
            tables = inspector.get_table_names(schema="public")
            cur_owners = conn.execute(text(
                "SELECT tableowner, count(*) FROM pg_tables WHERE schemaname = 'public' GROUP BY tableowner"
            )).fetchall()
            print(json.dumps({
                "mode": "dry-run",
                "tables_count": len(tables),
                "current_owners": [dict(r._mapping) for r in cur_owners],
            }, indent=2))
            return 0

    results = reassign_schema_objects(engine)
    print("Ownership transfer complete:")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
