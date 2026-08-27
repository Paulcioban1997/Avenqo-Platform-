"""Détection du type de base pour le backup — variantes PostgreSQL Railway.

Prouve que `postgresql://`, `postgres://` et `postgresql+psycopg://` sont
reconnus, et qu'aucune URL (avec credentials) ne fuite dans les erreurs.
"""

from __future__ import annotations

import pytest

from backend.app.services.backup_service import (
    UnsupportedDatabaseError,
    _database_kind,
    database_scheme,
)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:p@host:5432/db",
        "postgres://u:p@host:5432/db",
        "postgresql+psycopg://u:p@host:5432/db",
        "postgresql+psycopg2://u:p@host:5432/db",
        "POSTGRESQL://u:p@host:5432/db",
        "  postgresql://u:p@host:5432/db  ",
    ],
)
def test_postgresql_scheme_variants_detected(url: str) -> None:
    assert _database_kind(url) == "postgresql"


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///./var/avenqo.db",
        "sqlite:////abs/path.db",
    ],
)
def test_sqlite_scheme_detected(url: str) -> None:
    assert _database_kind(url) == "sqlite"


def test_unknown_scheme_rejected_without_leaking_url() -> None:
    secret_url = "mysql://root:s3cr3t@db.internal:3306/prod"
    with pytest.raises(UnsupportedDatabaseError) as exc_info:
        _database_kind(secret_url)

    message = str(exc_info.value)
    assert "mysql" not in message
    assert "s3cr3t" not in message
    assert secret_url not in message


# --- Log SAFE de démarrage : scheme uniquement, jamais credentials ----------


def test_database_scheme_returns_postgresql_for_railway_url() -> None:
    assert database_scheme("postgresql://postgres:secret@tramway.proxy.rlwy.net:25367/railway") == "postgresql"


def test_database_scheme_handles_postgres_alias_and_dialect() -> None:
    assert database_scheme("postgres://u:p@h/db") == "postgres"
    assert database_scheme("postgresql+psycopg://u:p@h/db") == "postgresql+psycopg"


def test_database_scheme_never_returns_credentials() -> None:
    scheme = database_scheme("postgresql://root:sup3rsecret@host:5432/db")
    assert scheme is not None
    assert "sup3rsecret" not in scheme
    assert "root" not in scheme
    assert "@" not in scheme


def test_database_scheme_none_for_missing_url() -> None:
    assert database_scheme("") is None
    assert database_scheme("   ") is None
