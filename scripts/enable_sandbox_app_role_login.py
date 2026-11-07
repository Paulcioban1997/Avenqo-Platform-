"""Prepare LOGIN for the constrained Sandbox application role. Dry-run default.

Never prints the password. Never rewrites Railway DATABASE_URL.
Requires a separate owner GO before pointing the API at avenqo_app.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-environment", default="")
    args = parser.parse_args()
    from sqlalchemy import create_engine, text

    from backend.app.config.settings import get_settings
    from backend.app.services.postgres_app_role import APP_ROLE, MIGRATE_ROLE, OWNER_ROLE, role_is_constrained

    settings = get_settings()
    if settings.environment != "sandbox":
        print("Refused: this helper is sandbox-only.", file=sys.stderr)
        return 2
    if args.apply and args.confirm_environment != "sandbox":
        print("Explicit --confirm-environment sandbox required; no changes applied.", file=sys.stderr)
        return 2
    password = os.environ.get("AVENQO_APP_ROLE_PASSWORD", "").strip()
    if args.apply and len(password) < 24:
        print("AVENQO_APP_ROLE_PASSWORD must be set privately (24+ chars); no changes applied.", file=sys.stderr)
        return 2
    engine = create_engine(settings.database_url)
    with engine.begin() as connection:
        if connection.dialect.name != "postgresql":
            print("PostgreSQL required.", file=sys.stderr)
            return 2
        missing = [
            name
            for name in (APP_ROLE, MIGRATE_ROLE, OWNER_ROLE)
            if connection.execute(text("SELECT 1 FROM pg_roles WHERE rolname=:n"), {"n": name}).scalar() is None
        ]
        if missing:
            print("Required roles missing; apply Alembic 0058 first. Names withheld from this message.", file=sys.stderr)
            return 1
        constrained = all(role_is_constrained(connection, name) for name in (APP_ROLE, MIGRATE_ROLE, OWNER_ROLE))
        can_login = connection.execute(
            text("SELECT rolcanlogin FROM pg_roles WHERE rolname=:n"), {"n": APP_ROLE}
        ).scalar_one()
        print(
            "environment=sandbox "
            f"roles_constrained={str(constrained).lower()} "
            f"app_can_login={str(bool(can_login)).lower()} "
            f"apply={str(args.apply).lower()} "
            "database_url_unchanged=true"
        )
        if not args.apply:
            print("Dry-run only. LOGIN not enabled. Pointing the API at this role still requires a separate GO.")
            return 0
        try:
            from psycopg2 import sql as pg_sql
        except ImportError:
            from psycopg import sql as pg_sql
        cursor = connection.connection.driver_connection.cursor()
        cursor.execute(
            pg_sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                pg_sql.Identifier(APP_ROLE),
                pg_sql.Literal(password),
            )
        )
        cursor.close()
        print("LOGIN enabled for avenqo_app. DATABASE_URL was not modified. Rotate the Railway variable only after a separate GO.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
