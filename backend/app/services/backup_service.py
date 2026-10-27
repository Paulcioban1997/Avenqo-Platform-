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
import os
import sqlite3
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.config.settings import Settings


class BackupError(Exception):
    """Erreur générique de sauvegarde/restauration."""


def _postgres_subprocess_connection(database_url: str) -> tuple[str, dict[str, str]]:
    """Keep authentication out of process arguments and error messages."""
    from sqlalchemy.engine import URL, make_url

    try:
        url = make_url(database_url.strip())
        if any("password" in key.lower() for key in url.query):
            raise ValueError("Password query parameters are not supported")
        child_env = os.environ.copy()
        if url.password is not None:
            child_env["PGPASSWORD"] = url.password
        safe_url = URL.create("postgresql", username=url.username, host=url.host,
                              port=url.port, database=url.database, query=url.query).render_as_string(hide_password=False)
        return safe_url, child_env
    except Exception:
        raise BackupError("Configuration PostgreSQL invalide ; détails sensibles masqués") from None


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
    artifacts_checksum_sha256: str | None = None
    artifacts_size_bytes: int | None = None
    alembic_revision: str | None = None

    def to_safe_dict(self) -> dict:
        """Jamais de secret dans les métadonnées — uniquement des faits techniques."""

        return asdict(self)


from urllib.parse import urlsplit

def database_scheme(database_url: str) -> str | None:
    """Scheme de connexion SAFE à logger (ex. `postgresql`) — jamais l'URL
    complète ni les credentials. `None` si l'URL est absente/vide."""

    if not database_url or not database_url.strip():
        return None
    return urlsplit(database_url.strip()).scheme.lower() or None


_POSTGRES_SCHEMES = frozenset({"postgresql", "postgres"})
ALLOWED_BACKUP_ENVIRONMENTS = frozenset(
    {"production", "sandbox", "staging", "development", "test"}
)
_BACKUP_SUFFIXES = (".db", ".sql", ".json", "_artifacts.tar.gz")


class BackupEnvironmentError(BackupError):
    """ENVIRONMENT et RAILWAY_ENVIRONMENT sont absents ou contradictoires."""


def normalize_backup_environment(value: str) -> str:
    environment = (value or "").strip().lower()
    if environment not in ALLOWED_BACKUP_ENVIRONMENTS:
        raise BackupEnvironmentError(
            "ENVIRONMENT doit être production, sandbox, staging, development ou test."
        )
    return environment


def resolve_backup_environment(
    explicit: str | None = None,
    railway: str | None = None,
) -> str:
    """Refuse le défaut silencieux `production` et toute contradiction Railway."""

    explicit_name = (explicit or "").strip().lower()
    railway_name = (railway or "").strip().lower()
    if explicit_name and railway_name and explicit_name != railway_name:
        raise BackupEnvironmentError(
            f"ENVIRONMENT={explicit_name} contredit RAILWAY_ENVIRONMENT={railway_name}."
        )
    chosen = explicit_name or railway_name
    if not chosen:
        raise BackupEnvironmentError(
            "ENVIRONMENT ou RAILWAY_ENVIRONMENT est requis pour une sauvegarde."
        )
    return normalize_backup_environment(chosen)


def _database_kind(database_url: str) -> str:
    """Détecte le type de base depuis le schéma — robuste aux variantes Railway :
    `postgresql://`, `postgres://`, `postgresql+psycopg://` (et casse/espaces).
    Ne logue ni n'inclut JAMAIS l'URL (elle contient les credentials)."""

    scheme = urlsplit(database_url.strip()).scheme.lower()
    # `postgresql+psycopg` → dialecte avant le '+', `postgres` → alias historique.
    dialect = scheme.split("+", 1)[0]
    if dialect == "sqlite":
        return "sqlite"
    if dialect in _POSTGRES_SCHEMES:
        return "postgresql"
    raise UnsupportedDatabaseError(
        "Schéma de base de données non pris en charge pour la sauvegarde."
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


def read_alembic_revision(database_url: str) -> str | None:
    """Return alembic_version.version_num without logging the connection URL."""
    try:
        kind = _database_kind(database_url)
    except Exception:
        return None
    try:
        if kind == "sqlite":
            path = _sqlite_path_from_url(database_url)
            connection = sqlite3.connect(str(path))
            try:
                row = connection.execute(
                    "SELECT version_num FROM alembic_version LIMIT 1"
                ).fetchone()
                return str(row[0]) if row and row[0] else None
            except sqlite3.Error:
                return None
            finally:
                connection.close()
        from sqlalchemy import create_engine, text

        engine = create_engine(database_url)
        try:
            with engine.connect() as connection:
                value = connection.execute(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                ).scalar()
        finally:
            engine.dispose()
        return str(value) if value else None
    except Exception:
        return None


def extract_alembic_revision_from_dump(sql_text: str) -> str | None:
    """Read alembic_version from a pg_dump plain SQL archive without restoring it."""
    if "alembic_version" not in sql_text:
        return None
    copy_marker = "COPY public.alembic_version"
    copy_at = sql_text.find(copy_marker)
    if copy_at == -1:
        copy_marker = "COPY alembic_version"
        copy_at = sql_text.find(copy_marker)
    if copy_at != -1:
        stdin_at = sql_text.find("FROM stdin;", copy_at)
        if stdin_at != -1:
            remainder = sql_text[stdin_at + len("FROM stdin;") :].lstrip()
            revision = remainder.splitlines()[0].strip() if remainder else ""
            if revision and revision != "\\." and " " not in revision:
                return revision
    import re

    match = re.search(
        r"INSERT INTO (?:public\.)?alembic_version[^;]*?'([^']+)'",
        sql_text,
    )
    if match:
        return match.group(1)
    return None


class LocalBackupStorage:
    """Stockage local sur disque. Abstraction volontairement minimale :

    un futur backend `S3BackupStorage`/`GCSBackupStorage` pourra implémenter la
    même interface (`root`, résolution/écriture de fichiers) sans changer
    `BackupService`. Pas de plateforme cloud imposée avant qu'elle soit choisie.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)


class S3BackupStorage:
    """Stockage S3-compatible (Railway Storage Bucket, MinIO, AWS S3).

    Utilise le disque local comme staging temporaire pour pg_dump, puis upload
    vers S3. Le restore télécharge d'abord depuis S3 vers le staging local.
    """

    def __init__(self, settings: Settings, staging_root: Path) -> None:
        import boto3

        self._bucket = settings.backup_s3_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.backup_s3_endpoint_url,
            aws_access_key_id=settings.backup_s3_access_key,
            aws_secret_access_key=settings.backup_s3_secret_key,
            region_name=settings.backup_s3_region,
        )
        self.root = staging_root
        self.root.mkdir(parents=True, exist_ok=True)

    def upload(self, local_path: Path, key: str | None = None) -> None:
        self._client.upload_file(str(local_path), self._bucket, key or local_path.name)

    def download(self, name: str, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self._client.download_file(self._bucket, name, str(local_path))

    def exists(self, name: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=name)
            return True
        except Exception:
            return False

    def delete(self, name: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=name)

    def list_names(self) -> list[str]:
        names: list[str] = []
        token = None
        while True:
            kwargs: dict[str, object] = {"Bucket": self._bucket}
            if token:
                kwargs["ContinuationToken"] = token
            response = self._client.list_objects_v2(**kwargs)
            names.extend(item["Key"] for item in response.get("Contents") or [])
            if not response.get("IsTruncated"):
                break
            token = response.get("NextContinuationToken")
        return names


class BackupService:
    FORMAT_VERSION = 1

    def __init__(self, settings: Settings, storage: LocalBackupStorage | S3BackupStorage | None = None) -> None:
        self._settings = settings
        backup_root = Path(settings.backup_root)
        if not backup_root.is_absolute():
            backup_root = Path.cwd() / backup_root
        if storage is not None:
            self._storage = storage
        elif settings.backup_s3_enabled:
            self._storage = S3BackupStorage(settings, backup_root)
        else:
            self._storage = LocalBackupStorage(backup_root)
        self._s3 = self._storage if isinstance(self._storage, S3BackupStorage) else None

    @property
    def root(self) -> Path:
        return self._storage.root

    @property
    def environment(self) -> str:
        return normalize_backup_environment(self._settings.environment)

    def _object_key(self, filename: str, *, prefixed: bool = True) -> str:
        if prefixed:
            return f"{self.environment}/{filename}"
        return filename

    def _candidate_keys(self, filename: str) -> list[str]:
        return [self._object_key(filename), filename]

    def _s3_exists(self, filename: str) -> str | None:
        if self._s3 is None:
            return None
        for key in self._candidate_keys(filename):
            if self._s3.exists(key):
                return key
        return None

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
            connection, child_env = _postgres_subprocess_connection(self._settings.database_url)
            result = subprocess.run(
                ["pg_dump", "--format=plain", "--no-owner", "--no-privileges",
                 "--file", str(destination_path), connection],
                env=child_env,
                capture_output=True, text=True, timeout=600, check=False,
            )
            if result.returncode != 0:
                destination_path.unlink(missing_ok=True)
                raise BackupError(f"pg_dump a échoué (code {result.returncode})")

        checksum = _sha256_of_file(destination_path)

        # Sauvegarde des artefacts fichiers (données brutes et nettoyées)
        artifacts_path: Path | None = None
        artifacts_checksum: str | None = None
        artifacts_size: int | None = None

        import os
        artifact_root_val = getattr(self._settings, "artifact_root", None) or os.getenv("ARTIFACT_ROOT", "var/artifacts")
        artifact_dir = Path(artifact_root_val)
        if not artifact_dir.is_absolute():
            artifact_dir = Path.cwd() / artifact_dir

        if artifact_dir.exists() and any(artifact_dir.iterdir()):
            artifacts_archive_path = self.root / f"{backup_id}_artifacts.tar.gz"
            import tarfile
            with tarfile.open(artifacts_archive_path, "w:gz") as tar:
                tar.add(str(artifact_dir), arcname="artifacts")
            artifacts_checksum = _sha256_of_file(artifacts_archive_path)
            artifacts_size = artifacts_archive_path.stat().st_size
            artifacts_path = artifacts_archive_path

        metadata = BackupMetadata(
            backup_id=backup_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            environment=self.environment,
            database_type=kind,
            app_version=self._settings.app_version,
            git_revision=_git_revision(),
            format_version=self.FORMAT_VERSION,
            checksum_sha256=checksum,
            size_bytes=destination_path.stat().st_size,
            artifacts_checksum_sha256=artifacts_checksum,
            artifacts_size_bytes=artifacts_size,
            alembic_revision=read_alembic_revision(self._settings.database_url),
        )
        metadata_path = self.root / f"{backup_id}.json"
        metadata_path.write_text(
            json.dumps(metadata.to_safe_dict(), indent=2), encoding="utf-8"
        )
        if self._s3 is not None:
            self._s3.upload(destination_path, self._object_key(destination_path.name))
            self._s3.upload(metadata_path, self._object_key(metadata_path.name))
            if artifacts_path is not None and artifacts_path.exists():
                self._s3.upload(artifacts_path, self._object_key(artifacts_path.name))
        self._apply_retention()
        return metadata

    def list_backups(self) -> list[BackupMetadata]:
        if self._s3 is not None:
            names = [n for n in self._s3.list_names() if n.endswith(".json")]
            result = []
            for name in sorted(names):
                local_meta = self.root / Path(name).name
                if not local_meta.exists():
                    self._s3.download(name, local_meta)
                result.append(self._load_metadata(local_meta))
            return result
        return [
            self._load_metadata(metadata_path)
            for metadata_path in sorted(self.root.glob("*.json"))
        ]

    def _load_metadata(self, metadata_path: Path) -> BackupMetadata:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        valid_fields = set(BackupMetadata.__dataclass_fields__.keys())
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        filtered.setdefault("app_version", "unknown")
        filtered.setdefault("git_revision", None)
        filtered.setdefault("format_version", 1)
        filtered.setdefault("size_bytes", 0)
        filtered.setdefault("checksum_sha256", "")
        filtered.setdefault("database_type", "unknown")
        filtered.setdefault("alembic_revision", None)
        return BackupMetadata(**filtered)

    def _resolve_backup_id(self, backup_id: str) -> tuple[Path, Path]:
        # Confine toujours l'identifiant au répertoire de sauvegarde : refuse
        # toute tentative de traversée de chemin (`../`, chemins absolus, `/`).
        safe_id = Path(backup_id).name
        if safe_id != backup_id or ".." in backup_id or not backup_id:
            raise BackupError("Identifiant de sauvegarde invalide.")
        metadata_path = self.root / f"{safe_id}.json"
        if not metadata_path.exists() and self._s3 is not None:
            meta_key = self._s3_exists(f"{safe_id}.json")
            if meta_key is not None:
                self._s3.download(meta_key, metadata_path)
        if not metadata_path.exists():
            raise BackupError(f"Sauvegarde introuvable : {backup_id}")
        db_path = self.root / f"{safe_id}.db"
        if not db_path.exists():
            db_path = self.root / f"{safe_id}.sql"
        if not db_path.exists() and self._s3 is not None:
            for suffix in (".db", ".sql"):
                archive_key = self._s3_exists(f"{safe_id}{suffix}")
                if archive_key is not None:
                    db_path = self.root / f"{safe_id}{suffix}"
                    self._s3.download(archive_key, db_path)
                    break
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
            connection, child_env = _postgres_subprocess_connection(target_database_url)
            result = subprocess.run(
                ["psql", connection, "--set=ON_ERROR_STOP=1", "--single-transaction", "-f", str(db_path)],
                env=child_env,
                capture_output=True, text=True, timeout=1800, check=False,
            )
            if result.returncode != 0:
                raise BackupError(f"psql restore a échoué (code {result.returncode})")

    def restore_artifacts(self, backup_id: str, target_dir: Path) -> dict[str, str]:
        """Restaure les artefacts archivés vers un répertoire cible isolé.

        Vérifie l'empreinte SHA256 de l'archive avant toute extraction et
        retourne un dictionnaire {chemin_relatif: sha256} pour vérification.
        Ne touche ni n'écrase jamais les données de production.
        """
        target_path = Path(target_dir)
        target_path.mkdir(parents=True, exist_ok=True)
        safe_id = Path(backup_id).name
        if safe_id != backup_id or ".." in backup_id or not backup_id:
            raise BackupError("Identifiant de sauvegarde invalide.")

        metadata_path = self.root / f"{safe_id}.json"
        if not metadata_path.exists() and self._s3 is not None:
            meta_key = self._s3_exists(f"{safe_id}.json")
            if meta_key is not None:
                self._s3.download(meta_key, metadata_path)
        if not metadata_path.exists():
            raise BackupError(f"Métadonnées introuvables : {backup_id}")

        metadata = self._load_metadata(metadata_path)
        archive_name = f"{safe_id}_artifacts.tar.gz"
        archive_path = self.root / archive_name
        if not archive_path.exists() and self._s3 is not None:
            archive_key = self._s3_exists(archive_name)
            if archive_key is not None:
                self._s3.download(archive_key, archive_path)
        if not archive_path.exists():
            raise BackupError(f"Archive d'artefacts introuvable pour la sauvegarde {backup_id}")

        if metadata.artifacts_checksum_sha256 is not None:
            actual_checksum = _sha256_of_file(archive_path)
            if actual_checksum != metadata.artifacts_checksum_sha256:
                raise CorruptBackupError(
                    f"Somme de contrôle invalide pour les artefacts {backup_id}."
                )

        import tarfile
        extracted_manifest: dict[str, str] = {}
        with tarfile.open(archive_path, "r:gz") as tar:
            for member in tar.getmembers():
                resolved = (target_path / member.name).resolve()
                if not str(resolved).startswith(str(target_path.resolve())):
                    raise BackupError(f"Traversée de chemin interdite : {member.name}")
            tar.extractall(path=str(target_path))
            for member in tar.getmembers():
                if member.isfile():
                    file_path = target_path / member.name
                    extracted_manifest[member.name] = _sha256_of_file(file_path)
        return extracted_manifest

    def _metadata_created_at(self, metadata_path: Path) -> datetime | None:
        try:
            metadata = self._load_metadata(metadata_path)
            return datetime.fromisoformat(metadata.created_at)
        except Exception:
            return None

    def _apply_retention(self) -> None:
        """Purge uniquement les objets préfixés trop anciens.

        Les sauvegardes plates historiques ne sont pas supprimées : la
        rétention `created_at` s'applique aux nouvelles clés `{env}/…`.
        """

        cutoff = datetime.now(timezone.utc) - timedelta(days=self._settings.backup_retention_days)
        prefix = f"{self.environment}/"
        expired_ids: set[str] = set()
        if self._s3 is not None:
            for name in self._s3.list_names():
                if not name.startswith(prefix) or not name.endswith(".json"):
                    continue
                backup_id = Path(name).name.removesuffix(".json")
                local_meta = self.root / f"{backup_id}.json"
                if not local_meta.exists():
                    self._s3.download(name, local_meta)
                created_at = self._metadata_created_at(local_meta)
                if created_at is not None and created_at < cutoff:
                    expired_ids.add(backup_id)
        else:
            for metadata_path in self.root.glob("*.json"):
                created_at = self._metadata_created_at(metadata_path)
                if created_at is not None and created_at < cutoff:
                    expired_ids.add(metadata_path.stem)
        for backup_id in expired_ids:
            for suffix in _BACKUP_SUFFIXES:
                filename = f"{backup_id}{suffix}"
                (self.root / filename).unlink(missing_ok=True)
                if self._s3 is not None:
                    key = self._object_key(filename)
                    if self._s3.exists(key):
                        self._s3.delete(key)
