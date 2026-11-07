"""Vérifie qu'une sauvegarde S3 récente existe pour l'environnement courant.

Usage :
    python scripts/check_backup_freshness.py

Quitte 0 si la dernière sauvegarde de cet environnement a moins de
BACKUP_MAX_AGE_HOURS heures (26 par défaut). Quitte 2 si elle est absente
ou trop ancienne. N'affiche jamais d'URL, de clé ou de dump.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.backup_service import BackupService
from scripts.backup_db import _load_backup_settings


def main() -> int:
    settings = _load_backup_settings()
    max_age_raw = os.getenv("BACKUP_MAX_AGE_HOURS", "26").strip() or "26"
    try:
        max_age_hours = float(max_age_raw)
    except ValueError:
        print("BACKUP_MAX_AGE_HOURS invalide", file=sys.stderr)
        return 1
    if not settings.backup_s3_enabled:
        print("s3_enabled=false freshness=unconfigured", file=sys.stderr)
        return 1

    service = BackupService(settings)  # type: ignore[arg-type]
    backups = [
        item
        for item in service.list_backups()
        if item.environment == settings.environment
    ]
    if not backups:
        print(
            f"backup_environment={settings.environment} "
            "freshness=missing latest_age_hours=none",
            file=sys.stderr,
        )
        return 2

    latest = max(backups, key=lambda item: item.created_at)
    created = datetime.fromisoformat(latest.created_at)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
    artifacts_present = bool(latest.artifacts_checksum_sha256)
    print(
        f"backup_environment={settings.environment} "
        f"latest_backup_id={latest.backup_id} "
        f"latest_age_hours={age_hours:.2f} "
        f"artifacts_archived={artifacts_present} "
        f"s3_prefix={settings.environment}/"
    )
    if age_hours > max_age_hours:
        print("freshness=stale", file=sys.stderr)
        return 2
    print("freshness=ok")
    if os.getenv("BACKUP_REQUIRE_ARTIFACTS", "").strip().lower() in {"1", "true", "yes"}:
        if not artifacts_present:
            print("artifacts=missing", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
