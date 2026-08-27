"""Diagnostic SAFE : DATABASE_URL env OS vs lecture Settings (jamais de valeur)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_settings_reads_database_url_from_env_when_set(monkeypatch, tmp_path) -> None:
    """Settings doit lire DATABASE_URL depuis l'env OS même si .env existe."""

    # Créer un .env avec une valeur SQLite pour simuler le conflit potentiel
    env_file = tmp_path / "backend" / ".env"
    env_file.parent.mkdir(parents=True)
    env_file.write_text("DATABASE_URL=sqlite:///./var/avenqo.db\n", encoding="utf-8")

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@railway:5432/db")
    monkeypatch.chdir(tmp_path)

    from backend.app.config.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    get_settings.cache_clear()

    # Settings doit prioriser l'env OS sur le .env
    assert settings.database_url.startswith("postgresql")


def test_backup_script_logs_safe_presence_and_scheme(tmp_path) -> None:
    """Le script de backup log présence + scheme, jamais la valeur."""

    script = Path(__file__).resolve().parents[2] / "scripts" / "backup_db.py"
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql://user:secret@host:5432/db"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    # Forcer un cwd sans .env pour isoler le test
    env["BACKUP_ROOT"] = str(tmp_path / "backups")

    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
        timeout=30,
    )

    output = result.stdout + result.stderr
    assert "env_database_url_present=true" in output
    assert "settings_database_url_present=true" in output
    assert "database_scheme=postgresql" in output
    # Jamais de secret dans la sortie
    assert "secret" not in output
    assert "user:secret" not in output


def test_backup_script_detects_env_settings_mismatch(tmp_path) -> None:
    """Si env existe mais Settings ne lit pas (ex: cwd sans .env), le script
    affiche l'alerte SAFE sans exposer la valeur."""

    script = Path(__file__).resolve().parents[2] / "scripts" / "backup_db.py"
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql://user:secret@host:5432/db"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    env["BACKUP_ROOT"] = str(tmp_path / "backups")

    # cwd dans un dossier vide → Settings cherche backend/.env là-bas → absent
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
        timeout=30,
    )

    output = result.stdout + result.stderr
    # Doit quand même fonctionner car env OS est prioritaire
    assert "settings_database_url_present=true" in output
    assert "secret" not in output
