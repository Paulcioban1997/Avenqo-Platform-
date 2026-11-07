"""Gate isolated PostgreSQL RLS rehearsals.

Canonical URLs (never Sandbox/Production):
- CI: ``postgresql+psycopg2://postgres:test-only-password@localhost:5432/rotation_test_ci``
- Local replica load tests: ``127.0.0.1:55432`` (see loadtest/isolated/run_replica.py)

Port ``54329`` is an obsolete leftover mapping. Skip it instead of failing.

These tests must never fail a local suite because a leftover
``AVENQO_ROTATION_TEST_ADMIN_URL`` points at a stopped container.
Skip when the service is absent. Fail only on a reachable, mis-scoped URL.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError


def require_isolated_admin_url():
    value = (os.environ.get("AVENQO_ROTATION_TEST_ADMIN_URL") or "").strip()
    if not value:
        pytest.skip("Isolated PostgreSQL required")
    if os.environ.get("ENVIRONMENT", "").strip().lower() != "test":
        pytest.skip("Isolated PostgreSQL tests run only with ENVIRONMENT=test")

    url = make_url(value)
    if url.host not in {"localhost", "127.0.0.1"}:
        pytest.fail("Isolated PostgreSQL URL must be localhost")
    if int(url.port or 5432) == 54329:
        pytest.skip("Obsolete local Postgres port 54329; CI uses localhost:5432/rotation_test_ci")
    database = str(url.database or "")
    if not database.startswith("rotation_test"):
        pytest.fail("Isolated PostgreSQL database name must start with rotation_test")

    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip("Isolated PostgreSQL is not reachable")
    finally:
        engine.dispose()
    return url
