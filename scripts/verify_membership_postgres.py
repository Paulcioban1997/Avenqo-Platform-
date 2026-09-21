"""Validate the repair in an isolated PostgreSQL schema, then roll it back."""
import importlib.util
import os
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


def verify():
    engine = create_engine(os.environ["MIGRATION_TEST_DATABASE_URL"])
    schema = "repair_test_" + uuid4().hex
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            connection.execute(text("CREATE TYPE user_role AS ENUM ('OWNER', 'ADMIN', 'MANAGER', 'ANALYST', 'USER', 'VIEWER')"))
            connection.execute(text("CREATE TABLE companies (id uuid PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE users (id uuid PRIMARY KEY, role user_role NOT NULL)"))
            root = Path(__file__).resolve().parents[1]
            for filename in ("0019_enterprise_quotes.py", "0019_company_memberships.py"):
                spec = importlib.util.spec_from_file_location("migration", root / "alembic/versions" / filename)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                module.op = Operations(MigrationContext.configure(connection))
                module.upgrade()
                module.upgrade()
            assert connection.scalar(text("SELECT count(*) FROM company_memberships")) == 0
            assert connection.scalar(text("SELECT count(*) FROM enterprise_quotes")) == 0
            assert connection.scalar(text("SELECT cardinality(enum_range(NULL::user_role))")) == 6
            constraints = connection.execute(text("SELECT contype FROM pg_constraint WHERE conrelid = 'company_memberships'::regclass")).scalars().all()
            assert constraints.count("f") == 2 and "u" in constraints and "p" in constraints
            module.downgrade()
            assert connection.scalar(text("SELECT cardinality(enum_range(NULL::user_role))")) == 6
            print("PASS: PostgreSQL upgrade, repeatability, empty memberships, constraints and enum preservation")
        finally:
            transaction.rollback()
    engine.dispose()


if __name__ == "__main__":
    verify()
