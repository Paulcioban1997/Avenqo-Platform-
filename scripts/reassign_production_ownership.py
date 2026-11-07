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
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError
from backend.app.services.postgres_app_role import (
    MIGRATE_ROLE,
    OWNER_ROLE,
    ensure_application_roles,
)


def _reassign_schema_objects_once(engine, *, expected_database: str) -> dict[str, int]:
    """Reassign all public tables, sequences, and enums to avenqo_owner."""
    with engine.begin() as conn:
        if conn.dialect.name != "postgresql":
            raise RuntimeError("PostgreSQL is required")
        actual_database = conn.execute(text("SELECT current_database()")).scalar_one()
        if actual_database != expected_database:
            raise RuntimeError("Target database confirmation does not match")
        # 1. Ensure roles and base permissions
        ensure_application_roles(conn)
        conn.execute(text(f"ALTER ROLE {MIGRATE_ROLE} INHERIT"))
        # PostgreSQL 16+ records inheritance on each membership. Merely
        # ALTER ROLE ... INHERIT leaves an existing NOINHERIT grant unchanged.
        conn.execute(text(f"GRANT {OWNER_ROLE} TO {MIGRATE_ROLE} WITH INHERIT TRUE"))

        # 2. Reassign all tables in public schema
        inspector = inspect(conn)
        quote = conn.dialect.identifier_preparer.quote
        tables = inspector.get_table_names(schema="public")
        for table in tables:
            conn.execute(text(f"ALTER TABLE public.{quote(table)} OWNER TO {OWNER_ROLE}"))

        # 3. Reassign sequences
        sequences = inspector.get_sequence_names(schema="public") if hasattr(inspector, "get_sequence_names") else []
        for seq in sequences:
            conn.execute(text(f"ALTER SEQUENCE public.{quote(seq)} OWNER TO {OWNER_ROLE}"))

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
            conn.execute(text(f"ALTER TYPE public.{quote(typ)} OWNER TO {OWNER_ROLE}"))

        inherited = conn.execute(text(
            "SELECT pg_has_role('avenqo_migrate', 'avenqo_owner', 'USAGE')"
        )).scalar_one()
        if not inherited:
            raise RuntimeError("Migrator does not inherit owner privileges")
        app_has_owner = conn.execute(text(
            "SELECT pg_has_role('avenqo_app', 'avenqo_owner', 'MEMBER')"
        )).scalar_one()
        if app_has_owner:
            raise RuntimeError("Runtime role must not inherit owner privileges")

    return {
        "tables_transferred": len(tables),
        "sequences_transferred": len(sequences),
        "enums_transferred": len(rows),
    }


def reassign_schema_objects(engine, *, expected_database: str) -> dict[str, int]:
    """Retry only transaction-safe lock contention; never retry privilege errors."""
    for attempt in range(3):
        try:
            return _reassign_schema_objects_once(engine, expected_database=expected_database)
        except DBAPIError as exc:
            code = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
            if code not in {"40P01", "55P03"} or attempt == 2:
                raise
            time.sleep(attempt + 1)
    raise AssertionError("Unreachable ownership retry state")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--admin-database-url",
        default=os.environ.get("ADMIN_DATABASE_URL") or os.environ.get("DATABASE_URL"),
        help="Superuser or admin connection URL with ALTER privilege on public schema.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Inspect only, do not alter.")
    parser.add_argument("--apply", action="store_true", help="Execute ownership changes after an explicit target confirmation.")
    parser.add_argument("--expect-database", help="Exact database name to verify before any change.")
    args = parser.parse_args()

    if args.dry_run == args.apply:
        print("Choose exactly one of --dry-run or --apply.", file=sys.stderr)
        return 2

    if not args.admin_database_url:
        print("ADMIN_DATABASE_URL or DATABASE_URL required.", file=sys.stderr)
        return 1

    engine = create_engine(args.admin_database_url)
    
    if args.dry_run:
        with engine.connect() as conn:
            if conn.dialect.name != "postgresql":
                print("PostgreSQL is required.", file=sys.stderr)
                return 2
            inspector = inspect(conn)
            tables = inspector.get_table_names(schema="public")
            sequences = inspector.get_sequence_names(schema="public")
            enums = conn.execute(text(
                "SELECT count(DISTINCT enumtypid) FROM pg_enum e "
                "JOIN pg_type t ON t.oid=e.enumtypid "
                "JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='public'"
            )).scalar_one()
            database = conn.execute(text("SELECT current_database()")).scalar_one()
            revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            cur_owners = conn.execute(text(
                "SELECT tableowner, count(*) FROM pg_tables WHERE schemaname = 'public' GROUP BY tableowner"
            )).fetchall()
            print(json.dumps({
                "mode": "dry-run",
                "database": database,
                "alembic_revision": revision,
                "tables_count": len(tables),
                "sequences_count": len(sequences),
                "enums_count": enums,
                "current_owners": [dict(r._mapping) for r in cur_owners],
                "planned_owner": OWNER_ROLE,
                "planned_migrator": MIGRATE_ROLE,
            }, indent=2))
            return 0

    if not args.expect_database:
        print("--expect-database is required with --apply.", file=sys.stderr)
        return 2
    results = reassign_schema_objects(engine, expected_database=args.expect_database)
    print("Ownership transfer complete:")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
