"""Named PostgreSQL roles for tenant RLS. Passwords and live DATABASE_URL stay out of this module."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

APP_ROLE = "avenqo_app"
MIGRATE_ROLE = "avenqo_migrate"
OWNER_ROLE = "avenqo_owner"

_CREATE_ROLES_SQL = """
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'avenqo_owner') THEN
    CREATE ROLE avenqo_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
  END IF;
  ALTER ROLE avenqo_owner WITH NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'avenqo_app') THEN
    CREATE ROLE avenqo_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
  END IF;
  ALTER ROLE avenqo_app WITH NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'avenqo_migrate') THEN
    CREATE ROLE avenqo_migrate NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
  END IF;
  ALTER ROLE avenqo_migrate WITH NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
END
$$;
"""


def ensure_application_roles(connection: Connection) -> None:
    """Create non-superuser roles and DML grants. Does not enable LOGIN or rotate DATABASE_URL."""

    if connection.dialect.name != "postgresql":
        return
    connection.execute(text(_CREATE_ROLES_SQL))
    connection.execute(text("GRANT avenqo_owner TO avenqo_migrate"))
    connection.execute(text("GRANT USAGE ON SCHEMA public TO avenqo_app, avenqo_migrate"))
    database = connection.execute(text("SELECT current_database()")).scalar_one()
    connection.execute(text(f'GRANT CONNECT ON DATABASE "{database}" TO avenqo_app, avenqo_migrate'))
    inspector = inspect(connection)
    tables = [name for name in inspector.get_table_names(schema="public") if name != "alembic_version"]
    if tables:
        quoted = ", ".join(f'"{name}"' for name in tables)
        connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {quoted} TO avenqo_app, avenqo_migrate"))
    connection.execute(text("GRANT SELECT ON alembic_version TO avenqo_app"))
    connection.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON alembic_version TO avenqo_migrate"))
    sequences = inspector.get_sequence_names(schema="public") if hasattr(inspector, "get_sequence_names") else []
    if sequences:
        quoted_seq = ", ".join(f'"{name}"' for name in sequences)
        connection.execute(text(f"GRANT USAGE, SELECT ON SEQUENCE {quoted_seq} TO avenqo_app, avenqo_migrate"))
    connection.execute(text("GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO avenqo_app, avenqo_migrate"))
    connection.execute(
        text(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO avenqo_app, avenqo_migrate"
        )
    )
    connection.execute(
        text(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            "GRANT USAGE, SELECT ON SEQUENCES TO avenqo_app, avenqo_migrate"
        )
    )


def role_is_constrained(connection: Connection, role_name: str) -> bool:
    row = connection.execute(
        text(
            "SELECT NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb "
            "FROM pg_roles WHERE rolname = :name"
        ),
        {"name": role_name},
    ).scalar_one_or_none()
    return bool(row)
