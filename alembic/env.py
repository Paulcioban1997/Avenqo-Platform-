"""Environnement Alembic Avenqo.

Utilise TOUJOURS la même source de configuration que le backend
(`backend.app.config.settings.Settings.database_url`) — jamais une URL codée
en dur. Surchargeable via la variable d'environnement `ALEMBIC_DATABASE_URL`
(utile pour cibler une base de test/temporaire isolée sans toucher à
`DATABASE_URL`, ex. lors des exercices de restauration — voir
docs/backup-and-disaster-recovery.md).
"""

from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

PROJECT_ROOT = Path(__file__).resolve().parents[1]

import sys  # noqa: E402

sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config.settings import get_settings  # noqa: E402
from backend.app.models import Base  # noqa: E402

# Importer explicitement tous les modules de modèles pour peupler Base.metadata
# (l'import de backend.app.models suffit déjà car il importe chaque modèle).

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    override = os.environ.get("ALEMBIC_DATABASE_URL")
    if override:
        return override
    return get_settings().database_url


def _resolve_sqlite_path(url: str) -> str:
    """Résout les chemins SQLite relatifs par rapport à la racine du projet,
    exactement comme `backend/app/database/session.py`, pour que Alembic et
    le backend ciblent toujours le même fichier."""

    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        raw_path = url.removeprefix("sqlite:///")
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
            candidate.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{candidate.as_posix()}"
    return url


def run_migrations_offline() -> None:
    url = _resolve_sqlite_path(_database_url())
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite reflète les colonnes UUID/JSON de façon imprécise (ex. UUID -> NUMERIC),
        # ce qui génère des diffs de type non pertinents en autogenerate. À revoir
        # manuellement si migration vers PostgreSQL (reflection plus fidèle).
        compare_type=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _resolve_sqlite_path(_database_url())
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=False)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
