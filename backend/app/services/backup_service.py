"""Sauvegarde/restauration (remédiation post-Phase 34).

Outil INTERNE opérations/admin uniquement — jamais exposé via une route HTTP
(voir tests/security/test_backup_restore_security.py). Utilisation prévue via
`scripts/backup_db.py` / `scripts/restore_db.py`.

Limitation connue : ne prend en charge que SQLite pour l'instant (seule base
utilisée par ce dépôt à ce stade — voir docs/production-deployment.md § Base
de données). Une migration vers PostgreSQL nécessiterait `pg_dump`/`pg_restore`
au lieu de l'API de sauvegarde SQLite utilisée ici.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.app.config.settings import Settings


class BackupError(Exception):
    """Erreur générique de sauvegarde/restauration."""


class UnsupportedDatabaseError(BackupError):
    """`DATABASE_URL` ne pointe pas vers une base prise en charge (SQLite)."""


class CorruptBackupError(BackupError):
    """La somme de contrôle de l'archive ne correspond pas — restauration refusée."""


@dataclass(slots=True)
class BackupMetadata:
    backup_id: str
    created_at: str
    environment: str
    database_type: str
    app_version: str
    git_revision: str | None
    format_version: int
    checksum_sha256: str
    size_bytes: int

    def to_safe_dict(self) -> dict:
        """Jamais de secret dans les métadonnées — uniquement des faits techniques."""

        return asdict(self)


def _database_kind(database_url: str) -> str:
    if database_url.startswith("sqlite"):
        return "sqlite"
    if database_url.startswith("postgresql") or database_url.startswith("postgres"):
        return "postgresql"
    raise UnsupportedDatabaseError(
        f"Base de données non prise en charge pour la sauvegarde : {database_url.split(':')[0]}"
    )


def _sqlite_path_from_url(database_url: str) -> Path:
    if not database_url.startswith("sqlite"):
        raise UnsupportedDatabaseError(
            "Le chemin fichier ne s'applique qu'à une base SQLite."
        )
    raw = database_url.split("///", 1)[1]
    return Path(raw)


def _sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_revision() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return None
    return result.stdout.strip() or None


class LocalBackupStorage:
    """Stockage local sur disque. Abstraction volontairement minimale :

    un futur backend `S3BackupStorage`/`GCSBackupStorage` pourra implémenter la
    même interface (`root`, résolution/écriture de fichiers) sans changer
    `BackupService`. Pas de plateforme cloud imposée avant qu'elle soit choisie.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)


class BackupService:
    FORMAT_VERSION = 1

    def __init__(self, settings: Settings, storage: LocalBackupStorage | None = None) -> None:
        self._settings = settings
        backup_root = Path(settings.backup_root)
        if not backup_root.is_absolute():
            backup_root = Path.cwd() / backup_root
        self._storage = storage or LocalBackupStorage(backup_root)

    @property
    def root(self) -> Path:
        return self._storage.root

    def create_backup(self) -> BackupMetadata:
        kind = _database_kind(self._settings.database_url)
        backup_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + "Z"
        suffix = ".sql" if kind == "postgresql" else ".db"
        destination_path = self.root / f"{backup_id}{suffix}"

        if kind == "sqlite":
            source_path = _sqlite_path_from_url(self._settings.database_url)
            if not source_path.exists():
                raise BackupError(f"Base de données introuvable : {source_path}")
            # API de sauvegarde SQLite native (snapshot cohérent) plutôt qu'une
            # simple copie de fichier — évite une archive incohérente si des
            # écritures sont en cours pendant la sauvegarde.
            source_conn = sqlite3.connect(str(source_path))
            try:
                dest_conn = sqlite3.connect(str(destination_path))
                try:
                    source_conn.backup(dest_conn)
                finally:
                    dest_conn.close()
            finally:
                source_conn.close()
        else:  # postgresql — pg_dump cohérent, jamais de secret dans les logs
            result = subprocess.run(
                ["pg_dump", "--format=plain", "--no-owner", "--no-privileges",
                 "--file", str(destination_path), self._settings.database_url],
                capture_output=True, text=True, timeout=600, check=False,
            )
            if result.returncode != 0:
                destination_path.unlink(missing_ok=True)
                raise BackupError(f"pg_dump a échoué (code {result.returncode})")

        checksum = _sha256_of_file(destination_path)
        metadata = BackupMetadata(
            backup_id=backup_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            environment=self._settings.environment,
            database_type=kind,
            app_version=self._settings.app_version,
            git_revision=_git_revision(),
            format_version=self.FORMAT_VERSION,
            checksum_sha256=checksum,
            size_bytes=destination_path.stat().st_size,
        )
        (self.root / f"{backup_id}.json").write_text(
            json.dumps(metadata.to_safe_dict(), indent=2), encoding="utf-8"
        )
        self._apply_retention()
        return metadata

    def list_backups(self) -> list[BackupMetadata]:
        return [
            self._load_metadata(metadata_path)
            for metadata_path in sorted(self.root.glob("*.json"))
        ]

    def _load_metadata(self, metadata_path: Path) -> BackupMetadata:
        return BackupMetadata(**json.loads(metadata_path.read_text(encoding="utf-8")))

    def _resolve_backup_id(self, backup_id: str) -> tuple[Path, Path]:
        # Confine toujours l'identifiant au répertoire de sauvegarde : refuse
        # toute tentative de traversée de chemin (`../`, chemins absolus, `/`).
        safe_id = Path(backup_id).name
        if safe_id != backup_id or ".." in backup_id or not backup_id:
            raise BackupError("Identifiant de sauvegarde invalide.")
        metadata_path = self.root / f"{safe_id}.json"
        if not metadata_path.exists():
            raise BackupError(f"Sauvegarde introuvable : {backup_id}")
        db_path = self.root / f"{safe_id}.db"
        if not db_path.exists():
            db_path = self.root / f"{safe_id}.sql"
        if not db_path.exists():
            raise BackupError(f"Archive introuvable pour la sauvegarde : {backup_id}")
        return db_path, metadata_path

    def verify_backup(self, backup_id: str) -> BackupMetadata:
        db_path, metadata_path = self._resolve_backup_id(backup_id)
        metadata = self._load_metadata(metadata_path)
        actual_checksum = _sha256_of_file(db_path)
        if actual_checksum != metadata.checksum_sha256:
            raise CorruptBackupError(
                f"Somme de contrôle invalide pour la sauvegarde {backup_id} : "
                "archive corrompue, restauration refusée."
            )
        return metadata

    def restore_backup(self, backup_id: str, target_database_url: str) -> None:
        """Restaure vers une base CIBLE explicite. N'écrase jamais silencieusement
        la base configurée par défaut — l'appelant (script CLI) doit fournir
        `target_database_url` explicitement, voir scripts/restore_db.py."""

        metadata = self._load_metadata(self._resolve_backup_id(backup_id)[1])
        self.verify_backup(backup_id)  # refuse toute archive corrompue avant restauration
        kind = metadata.database_type
        db_path = self._resolve_backup_id(backup_id)[0]
        target_kind = _database_kind(target_database_url)
        if target_kind != kind:
            raise BackupError(
                f"Type de base cible ({target_kind}) incompatible avec l'archive ({kind})."
            )

        if kind == "sqlite":
            target_path = _sqlite_path_from_url(target_database_url)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            source_conn = sqlite3.connect(str(db_path))
            try:
                dest_conn = sqlite3.connect(str(target_path))
                try:
                    source_conn.backup(dest_conn)
                finally:
                    dest_conn.close()
            finally:
                source_conn.close()
        else:  # postgresql
            result = subprocess.run(
                ["psql", target_database_url, "-f", str(db_path)],
                capture_output=True, text=True, timeout=1800, check=False,
            )
            if result.returncode != 0:
                raise BackupError(f"psql restore a échoué (code {result.returncode})")

    def _apply_retention(self) -> None:
        cutoff = datetime.now(timezone.utc).timestamp() - (
            self._settings.backup_retention_days * 86400
        )
        for metadata_path in self.root.glob("*.json"):
            if metadata_path.stat().st_mtime < cutoff:
                backup_id = metadata_path.stem
                (self.root / f"{backup_id}.db").unlink(missing_ok=True)
                metadata_path.unlink(missing_ok=True)
