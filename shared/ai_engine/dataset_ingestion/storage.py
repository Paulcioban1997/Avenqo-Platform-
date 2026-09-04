"""Stockage tenant-isolé et versionné des datasets d'entreprise (Phase 26).

Modélisé sur le pattern déjà éprouvé de `ArtifactService` (normalisation de
nom de fichier, vérification anti-traversée de chemin, écriture atomique),
étendu avec une séparation stricte raw/prepared et une structure de version.
GCS/S3 ne sont volontairement PAS implémentés ici : seuls des points
d'extension `DatasetStorage` sont prévus pour une Phase future.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from uuid import UUID

_SAFE_FILENAME = re.compile(r"[^a-zA-Z0-9._-]+")


class DatasetStorage(ABC):
    """Abstraction de stockage tenant-isolé, indépendante du backend physique."""

    @abstractmethod
    def save_raw(
        self,
        company_id: UUID,
        dataset_id: UUID,
        version: int,
        filename: str,
        content: bytes,
    ) -> str:
        ...

    @abstractmethod
    def save_prepared(
        self,
        company_id: UUID,
        dataset_id: UUID,
        version: int,
        rows: list[dict[str, Any]],
    ) -> str:
        ...

    @abstractmethod
    def save_metadata(
        self,
        company_id: UUID,
        dataset_id: UUID,
        version: int,
        metadata: dict[str, Any],
    ) -> str:
        ...


class LocalDatasetStorage(DatasetStorage):
    """Implémentation locale sur disque (GCS/S3 : placeholders pour Phase future)."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def save_raw(
        self,
        company_id: UUID,
        dataset_id: UUID,
        version: int,
        filename: str,
        content: bytes,
    ) -> str:
        directory = self._version_dir(company_id, dataset_id, version) / "raw"
        safe_name = _SAFE_FILENAME.sub("_", Path(filename).name) or "dataset"
        return str(self._write_bytes(directory, safe_name, content))

    def save_prepared(
        self,
        company_id: UUID,
        dataset_id: UUID,
        version: int,
        rows: list[dict[str, Any]],
    ) -> str:
        directory = self._version_dir(company_id, dataset_id, version) / "prepared"
        payload = json.dumps(rows, default=str).encode("utf-8")
        return str(self._write_bytes(directory, "prepared.json", payload))

    def save_metadata(
        self,
        company_id: UUID,
        dataset_id: UUID,
        version: int,
        metadata: dict[str, Any],
    ) -> str:
        directory = self._version_dir(company_id, dataset_id, version) / "metadata"
        payload = json.dumps(metadata, default=str).encode("utf-8")
        return str(self._write_bytes(directory, "metadata.json", payload))

    def _version_dir(self, company_id: UUID, dataset_id: UUID, version: int) -> Path:
        return self._root / str(company_id) / "datasets" / str(dataset_id) / f"v{version}"

    def prepared_path(self, company_id: UUID, dataset_id: UUID, version: int) -> Path:
        """Emplacement canonique du JSON nettoyé, indépendant de l'origine
        (pipeline actuel ou legacy) du fichier brut original."""
        return self._version_dir(company_id, dataset_id, version) / "prepared" / "prepared.json"

    def metadata_path(self, company_id: UUID, dataset_id: UUID, version: int) -> Path:
        return self._version_dir(company_id, dataset_id, version) / "metadata" / "metadata.json"

    def _write_bytes(self, directory: Path, safe_name: str, content: bytes) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        destination = (directory / safe_name).resolve()
        if self._root not in destination.parents:
            raise ValueError("Chemin de dataset invalide (traversée de répertoire détectée)")
        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(dir=directory, delete=False) as temporary:
                temporary.write(content)
                temporary.flush()
                temporary_path = Path(temporary.name)
            temporary_path.replace(destination)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return destination
