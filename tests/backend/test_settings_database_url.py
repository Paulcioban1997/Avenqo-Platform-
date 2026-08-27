"""Test ciblé : Settings.database_url lit DATABASE_URL depuis os.environ uniquement.

Prouve que la lecture ne dépend PAS du fichier .env local et fonctionne en
production (Railway) où seule la variable OS est définie.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_database_url_from_os_env_only_without_dotenv(tmp_path, monkeypatch) -> None:
    """DATABASE_URL défini uniquement dans os.environ (pas de .env) doit être lu."""

    # Isoler dans un répertoire sans backend/.env
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@railway:5432/prod")

    from backend.app.config.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    get_settings.cache_clear()

    assert settings.database_url == "postgresql://u:p@railway:5432/prod"


def test_database_url_from_os_env_overrides_dotenv(tmp_path, monkeypatch) -> None:
    """DATABASE_URL dans os.environ doit prioriser sur backend/.env local."""

    # Créer un .env avec SQLite (valeur par défaut de dev)
    env_dir = tmp_path / "backend"
    env_dir.mkdir()
    (env_dir / ".env").write_text("DATABASE_URL=sqlite:///./var/local.db\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@railway:5432/prod")

    from backend.app.config.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    get_settings.cache_clear()

    assert settings.database_url == "postgresql://u:p@railway:5432/prod"
    assert "sqlite" not in settings.database_url


def test_settings_script_confirms_database_url_reading(tmp_path) -> None:
    """Un script Python minimal confirme la lecture depuis l'env OS."""

    code = """
import os
os.environ['DATABASE_URL'] = 'postgresql://env:secret@host:5432/db'
from backend.app.config.settings import get_settings
s = get_settings()
print('database_url_present=', bool(s.database_url))
print('scheme=', s.database_url.split(':')[0] if s.database_url else 'none')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=tmp_path,  # sans .env
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2])},
        timeout=30,
    )
    assert result.returncode == 0
    assert "database_url_present=" in result.stdout and "True" in result.stdout
    assert "scheme=" in result.stdout and "postgresql" in result.stdout
    assert "secret" not in result.stdout
