"""CLI opérations : restaure une sauvegarde Avenqo VERS UNE BASE CIBLE EXPLICITE.

Usage :
    python scripts/restore_db.py --backup-id <id> --target-database-url <url> [--force]

Sécurité :
  - Ne restaure JAMAIS silencieusement vers `DATABASE_URL` (la base configurée
    par défaut) : `--target-database-url` est TOUJOURS obligatoire.
  - Si la cible coïncide avec `DATABASE_URL` actuel, `--force` est requis pour
    confirmer explicitement l'intention (protection contre un écrasement
    accidentel de la base active).
  - Refuse toute archive dont la somme de contrôle ne correspond pas (voir
    BackupService.verify_backup).

Outil interne admin/opérations uniquement — jamais exposé via HTTP.
"""

from __future__ import annotations

import argparse
import sys

from backend.app.config.settings import get_settings
from backend.app.services.backup_service import BackupError, BackupService


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-id", required=True)
    parser.add_argument("--target-database-url", required=True)
    parser.add_argument(
        "--force", action="store_true",
        help="Requis si --target-database-url coïncide avec DATABASE_URL actif.",
    )
    args = parser.parse_args()

    settings = get_settings()
    if args.target_database_url == settings.database_url and not args.force:
        print(
            "REFUS : la cible correspond à DATABASE_URL actif. "
            "Utilisez --force pour confirmer explicitement.",
            file=sys.stderr,
        )
        return 2

    service = BackupService(settings)
    try:
        service.verify_backup(args.backup_id)
        service.restore_backup(args.backup_id, args.target_database_url)
    except BackupError as exc:
        print(f"ÉCHEC de la restauration : {exc}", file=sys.stderr)
        return 1

    print(f"Restauration réussie vers {args.target_database_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
