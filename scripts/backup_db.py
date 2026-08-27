"""CLI opérations : crée une sauvegarde de la base de données Avenqo.

Usage :
    python scripts/backup_db.py

Outil interne admin/opérations uniquement — jamais exposé via HTTP (voir
docs/backup-and-disaster-recovery.md et tests/security/test_backup_restore_security.py).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Quand Python exécute directement `scripts/backup_db.py`, sys.path[0] pointe
# vers `/srv/scripts` et non vers la racine `/srv`. Ajouter explicitement la
# racine du projet permet d'importer le package `backend` de façon fiable dans
# le Cron Railway sans dépendre d'un PYTHONPATH externe.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config.settings import get_settings
from backend.app.services.backup_service import BackupService, database_scheme


def main() -> None:
    settings = get_settings()
    # Diagnostic SAFE : compare la présence côté env OS vs lecture Settings.
    # Jamais la valeur de l'URL (elle contient user/password de la base).
    env_present = bool(os.getenv("DATABASE_URL", "").strip())
    settings_present = bool(settings.database_url and settings.database_url.strip())
    scheme = database_scheme(settings.database_url)
    print(
        "Backup démarré : "
        f"env_database_url_present={str(env_present).lower()} "
        f"settings_database_url_present={str(settings_present).lower()} "
        f"database_scheme={scheme or 'unknown'}"
    )
    if env_present and not settings_present:
        print(
            "ALERTE : DATABASE_URL est définie dans l'environnement mais non lue "
            "par Settings — vérifiez la configuration Pydantic (alias/env_file)."
        )
    service = BackupService(settings)
    metadata = service.create_backup()
    print("Sauvegarde créée avec succès :")
    for key, value in metadata.to_safe_dict().items():
        print(f"  {key}: {value}")
    print(f"Répertoire : {service.root}")


if __name__ == "__main__":
    main()
