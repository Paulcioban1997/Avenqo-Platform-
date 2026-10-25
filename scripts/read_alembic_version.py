"""Read-only print of alembic_version. Never prints connection strings."""

from __future__ import annotations

import os
import sys


def main() -> int:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("ALEMBIC_QUERY=fail REASON=missing_database_url")
        return 1
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    try:
        import psycopg2
    except ImportError:
        print("ALEMBIC_QUERY=fail REASON=missing_psycopg2")
        return 1
    try:
        connection = psycopg2.connect(url)
        connection.set_session(readonly=True, autocommit=True)
        with connection.cursor() as cursor:
            cursor.execute("SELECT version_num FROM alembic_version ORDER BY 1")
            versions = [row[0] for row in cursor.fetchall()]
        print("ALEMBIC_QUERY=ok COUNT=%d VERSIONS=%s" % (len(versions), ",".join(versions)))
        return 0
    except Exception as exc:
        print("ALEMBIC_QUERY=fail REASON=%s" % type(exc).__name__)
        return 1
    finally:
        try:
            connection.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
