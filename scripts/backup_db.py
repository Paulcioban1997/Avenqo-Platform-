"""CLI opérations : crée une sauvegarde de la base de données Avenqo.

Usage :
    python scripts/backup_db.py

Outil interne admin/opérations uniquement — jamais exposé via HTTP (voir
docs/backup-and-disaster-recovery.md et tests/security/test_backup_restore_security.py).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

# Quand Python exécute directement `scripts/backup_db.py`, sys.path[0] pointe
# vers `/srv/scripts` et non vers la racine `/srv`. Ajouter explicitement la
# racine du projet permet d'importer le package `backend` de façon fiable dans
# le Cron Railway sans dépendre d'un PYTHONPATH externe.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.backup_service import BackupService, database_scheme


@dataclass(slots=True)
class BackupRuntimeSettings:
    """Configuration minimale du job de backup.

    Le cron de sauvegarde ne doit pas dépendre de la configuration HTTP,
    d'authentification ou Stripe de l'application principale. Il ne charge que
    les paramètres effectivement utilisés par ``BackupService``.
    """

    database_url: str
    environment: str
    app_version: str
    backup_root: str
    backup_retention_days: int
    backup_s3_endpoint_url: str | None
    backup_s3_bucket: str | None
    backup_s3_access_key: str | None
    backup_s3_secret_key: str | None
    backup_s3_region: str

    @property
    def backup_s3_enabled(self) -> bool:
        return bool(
            self.backup_s3_bucket
            and self.backup_s3_access_key
            and self.backup_s3_secret_key
        )


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _load_backup_settings() -> BackupRuntimeSettings:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL est requis pour exécuter une sauvegarde.")

    retention_raw = os.getenv("BACKUP_RETENTION_DAYS", "30").strip() or "30"
    try:
        retention_days = int(retention_raw)
    except ValueError as exc:
        raise RuntimeError("BACKUP_RETENTION_DAYS doit être un entier positif.") from exc
    if retention_days < 1:
        raise RuntimeError("BACKUP_RETENTION_DAYS doit être supérieur ou égal à 1.")

    return BackupRuntimeSettings(
        database_url=database_url,
        environment=os.getenv("ENVIRONMENT", "production").strip() or "production",
        app_version=os.getenv("APP_VERSION", "0.1.0").strip() or "0.1.0",
        backup_root=os.getenv("BACKUP_ROOT", "var/backups").strip() or "var/backups",
        backup_retention_days=retention_days,
        backup_s3_endpoint_url=_optional_env("BACKUP_S3_ENDPOINT_URL"),
        backup_s3_bucket=_optional_env("BACKUP_S3_BUCKET"),
        backup_s3_access_key=_optional_env("BACKUP_S3_ACCESS_KEY"),
        backup_s3_secret_key=_optional_env("BACKUP_S3_SECRET_KEY"),
        backup_s3_region=os.getenv("BACKUP_S3_REGION", "auto").strip() or "auto",
    )


def main() -> None:
    settings = _load_backup_settings()
    # Diagnostic SAFE : ne journalise jamais DATABASE_URL car elle contient des secrets.
    scheme = database_scheme(settings.database_url)
    print(
        "Backup démarré : "
        "env_database_url_present=true "
        "settings_database_url_present=true "
        f"database_scheme={scheme or 'unknown'}"
    )
    service = BackupService(settings)  # type: ignore[arg-type]
    metadata = service.create_backup()
    print("Sauvegarde créée avec succès :")
    for key, value in metadata.to_safe_dict().items():
        print(f"  {key}: {value}")
    print(f"Répertoire : {service.root}")


if __name__ == "__main__":
    main()
