"""CLI opérations : crée une sauvegarde de la base de données Avenqo.

Usage :
    python scripts/backup_db.py

Outil interne admin/opérations uniquement — jamais exposé via HTTP (voir
docs/backup-and-disaster-recovery.md et tests/security/test_backup_restore_security.py).
"""

from __future__ import annotations

from backend.app.config.settings import get_settings
from backend.app.services.backup_service import BackupService, database_scheme


def main() -> None:
    settings = get_settings()
    # Log SAFE de démarrage : présence + scheme uniquement — jamais l'URL
    # complète (elle contient user/password de la base).
    scheme = database_scheme(settings.database_url)
    print(
        f"Backup démarré : database_url_present={scheme is not None} "
        f"database_scheme={scheme or 'unknown'}"
    )
    service = BackupService(settings)
    metadata = service.create_backup()
    print("Sauvegarde créée avec succès :")
    for key, value in metadata.to_safe_dict().items():
        print(f"  {key}: {value}")
    print(f"Répertoire : {service.root}")


if __name__ == "__main__":
    main()
