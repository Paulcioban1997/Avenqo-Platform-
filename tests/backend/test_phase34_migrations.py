"""Remédiation post-Phase 34 — Alembic : migrations versionnées.

Couvre : migration sur base fraîche (upgrade head), stratégie de baseline pour
une base existante (stamp), et le cycle upgrade/downgrade entre deux
révisions (0001 -> 0002 -> 0001). N'utilise jamais la base de développement
réelle — toujours un fichier SQLite temporaire dédié.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

REPO_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config(database_url: str) -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    os.environ["ALEMBIC_DATABASE_URL"] = database_url
    return config


@pytest.fixture
def temp_db_url(tmp_path: Path) -> str:
    db_path = tmp_path / "phase34_migrations.db"
    url = f"sqlite:///{db_path.as_posix()}"
    yield url
    os.environ.pop("ALEMBIC_DATABASE_URL", None)


def test_fresh_database_upgrade_head_creates_full_schema(temp_db_url: str) -> None:
    config = _alembic_config(temp_db_url)
    command.upgrade(config, "head")

    engine = create_engine(temp_db_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    for expected in ("companies", "users", "billing_invoices", "audit_log_entries", "ai_conversations", "company_onboarding"):
        assert expected in tables

    with engine.connect() as connection:
        current = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert current == "0003_company_onboarding"


def test_fresh_database_has_audit_log_indexes_after_upgrade(temp_db_url: str) -> None:
    config = _alembic_config(temp_db_url)
    command.upgrade(config, "head")

    engine = create_engine(temp_db_url)
    inspector = inspect(engine)
    index_names = {idx["name"] for idx in inspector.get_indexes("audit_log_entries")}
    assert "ix_audit_log_entries_created_at" in index_names
    assert "ix_audit_log_entries_company_id" in index_names


def test_upgrade_downgrade_cycle_between_revisions(temp_db_url: str) -> None:
    config = _alembic_config(temp_db_url)
    command.upgrade(config, "0001_baseline_schema")

    engine = create_engine(temp_db_url)
    inspector = inspect(engine)
    assert "audit_log_entries" in inspector.get_table_names()
    index_names_before = {idx["name"] for idx in inspector.get_indexes("audit_log_entries")}
    assert "ix_audit_log_entries_created_at" not in index_names_before

    command.upgrade(config, "0002_audit_log_indexes")
    inspector = inspect(engine)
    index_names_after = {idx["name"] for idx in inspector.get_indexes("audit_log_entries")}
    assert "ix_audit_log_entries_created_at" in index_names_after

    command.downgrade(config, "0001_baseline_schema")
    inspector = inspect(engine)
    index_names_reverted = {idx["name"] for idx in inspector.get_indexes("audit_log_entries")}
    assert "ix_audit_log_entries_created_at" not in index_names_reverted


def test_existing_database_baseline_stamp_strategy(temp_db_url: str) -> None:
    """Simule une base Avenqo EXISTANTE (créée via `Base.metadata.create_all()`
    avant l'introduction d'Alembic) : `stamp` doit permettre de continuer les
    migrations SANS jamais rejouer le DDL de création des tables déjà présentes."""

    from backend.app.models import Base

    engine = create_engine(temp_db_url)
    # `company_onboarding` a été introduite APRÈS la baseline (migration 0003) :
    # une vraie base pré-Alembic ne l'aurait jamais eue. On l'exclut du
    # `create_all()` pour simuler fidèlement ce scénario et laisser la
    # migration 0003 la créer normalement via `upgrade(config, "head")`.
    tables_before_onboarding = [
        table for table in Base.metadata.sorted_tables if table.name != "company_onboarding"
    ]
    Base.metadata.create_all(engine, tables=tables_before_onboarding)  # simule l'ancien comportement Phase 1-34
    inspector = inspect(engine)
    assert "audit_log_entries" in inspector.get_table_names()

    # Le modèle actuel inclut déjà les index ajoutés par la migration 0002 (ils
    # ont été ajoutés au modèle EN MÊME TEMPS que la migration, pour rester
    # cohérents). Pour simuler fidèlement une base Phase 34 RÉELLEMENT
    # existante (créée AVANT cette remédiation, donc sans ces index), on les
    # supprime explicitement avant de tester la stratégie de stamp.
    with engine.begin() as connection:
        connection.execute(text("DROP INDEX IF EXISTS ix_audit_log_entries_created_at"))
        connection.execute(text("DROP INDEX IF EXISTS ix_audit_log_entries_company_id"))
    inspector = inspect(engine)
    index_names_before = {idx["name"] for idx in inspector.get_indexes("audit_log_entries")}
    assert "ix_audit_log_entries_created_at" not in index_names_before

    config = _alembic_config(temp_db_url)
    # Marque la base comme étant déjà au niveau du schéma baseline, SANS exécuter
    # le moindre CREATE TABLE (les tables existent déjà).
    command.stamp(config, "0001_baseline_schema")

    # Les futures migrations (ex. 0002) restent applicables normalement.
    command.upgrade(config, "head")
    inspector = inspect(engine)
    index_names_after = {idx["name"] for idx in inspector.get_indexes("audit_log_entries")}
    assert "ix_audit_log_entries_created_at" in index_names_after


def test_application_starts_after_migration(temp_db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    config = _alembic_config(temp_db_url)
    command.upgrade(config, "head")

    # `backend.app.database.session.engine` est un singleton lié au module,
    # construit une seule fois à l'import — on ne peut pas le repointer via une
    # variable d'environnement après coup. On surcharge donc `get_db`
    # explicitement vers la base fraîchement migrée, comme les autres tests.
    monkeypatch.setenv("AUTH_JWT_SECRET", "d" * 32)
    from sqlalchemy.orm import sessionmaker

    from backend.app.config.settings import get_settings
    from backend.app.database import get_db
    from backend.main import create_application
    from fastapi.testclient import TestClient

    get_settings.cache_clear()
    migrated_engine = create_engine(temp_db_url)
    factory = sessionmaker(bind=migrated_engine, autoflush=False, expire_on_commit=False)

    app = create_application()

    def override_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        response = client.get("/api/v1/ready")
        assert response.status_code == 200
        assert response.json()["database"] == "ok"
    get_settings.cache_clear()
