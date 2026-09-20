"""Test isolé de sauvegarde et restauration des artefacts avec vérification d'empreinte SHA256."""

import hashlib
import os
import shutil
import tempfile
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.backup_service import BackupService


@dataclass
class DummySettings:
    database_url: str
    environment: str = "test"
    app_version: str = "0.1.0"
    backup_root: str = ""
    backup_retention_days: int = 7
    backup_s3_enabled: bool = False
    artifact_root: str = ""


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_artifact_backup_and_restore():
    with tempfile.TemporaryDirectory() as base_tmp:
        base = Path(base_tmp)
        db_path = base / "test.db"
        # Create minimal sqlite db
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (id INT)")
        conn.commit()
        conn.close()

        # Create isolated artifacts dir with raw and cleaned files
        artifacts_dir = base / "data_artifacts"
        raw_file = artifacts_dir / "company_datasets" / "test_company" / "datasets" / "d1" / "v1" / "raw" / "source.csv"
        raw_file.parent.mkdir(parents=True, exist_ok=True)
        raw_content = b"col1,col2\nval1,val2\nval3,val4\n"
        raw_file.write_bytes(raw_content)

        cleaned_file = artifacts_dir / "company_datasets" / "test_company" / "datasets" / "d1" / "v1" / "cleaned" / "cleaned.csv"
        cleaned_file.parent.mkdir(parents=True, exist_ok=True)
        cleaned_content = b"col1,col2\nVAL1,VAL2\nVAL3,VAL4\n"
        cleaned_file.write_bytes(cleaned_content)

        raw_sha256 = compute_sha256(raw_file)
        cleaned_sha256 = compute_sha256(cleaned_file)

        # Configure BackupService with isolated backup_root and artifact_root
        backup_root = base / "backups"
        settings = DummySettings(
            database_url=f"sqlite:///{db_path}",
            backup_root=str(backup_root),
            artifact_root=str(artifacts_dir),
        )

        service = BackupService(settings)  # type: ignore[arg-type]
        metadata = service.create_backup()

        print(f"[OK] Backup créé : ID={metadata.backup_id}")
        print(f"[OK] Checksum DB : {metadata.checksum_sha256}")
        print(f"[OK] Checksum Artefacts : {metadata.artifacts_checksum_sha256}")
        print(f"[OK] Taille Artefacts : {metadata.artifacts_size_bytes} octets")

        assert metadata.artifacts_checksum_sha256 is not None, "Artifacts checksum should not be None"
        assert metadata.artifacts_size_bytes is not None and metadata.artifacts_size_bytes > 0

        # Isolated restore target (must not overwrite artifacts_dir)
        isolated_restore_dir = base / "isolated_restore_target"
        manifest = service.restore_artifacts(metadata.backup_id, isolated_restore_dir)

        print(f"[OK] Fichiers restaurés dans {isolated_restore_dir} :")
        for rel_name, sha in manifest.items():
            print(f"  - {rel_name} (sha256: {sha})")

        # Locate restored files
        restored_raw = isolated_restore_dir / "artifacts" / "company_datasets" / "test_company" / "datasets" / "d1" / "v1" / "raw" / "source.csv"
        restored_cleaned = isolated_restore_dir / "artifacts" / "company_datasets" / "test_company" / "datasets" / "d1" / "v1" / "cleaned" / "cleaned.csv"

        assert restored_raw.exists(), "Restored raw file must exist"
        assert restored_cleaned.exists(), "Restored cleaned file must exist"

        restored_raw_sha = compute_sha256(restored_raw)
        restored_cleaned_sha = compute_sha256(restored_cleaned)

        assert restored_raw_sha == raw_sha256, f"Checksum mismatch for raw: {restored_raw_sha} vs {raw_sha256}"
        assert restored_cleaned_sha == cleaned_sha256, f"Checksum mismatch for cleaned: {restored_cleaned_sha} vs {cleaned_sha256}"
        assert restored_raw.read_bytes() == raw_content, "Raw file content mismatch"
        assert restored_cleaned.read_bytes() == cleaned_content, "Cleaned file content mismatch"

        # Verify original files were NOT touched/overwritten
        assert raw_file.exists() and compute_sha256(raw_file) == raw_sha256
        assert cleaned_file.exists() and compute_sha256(cleaned_file) == cleaned_sha256

        print("\n=== SUCCÈS TOTAL : Restauration en emplacement isolé validée avec 100% de concordance des empreintes SHA256 ===")


if __name__ == "__main__":
    test_artifact_backup_and_restore()
