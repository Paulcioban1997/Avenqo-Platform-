"""Stockage tenant-isolé et versionné des datasets d'entreprise (Phase 26).

Modélisé sur le pattern déjà éprouvé de `ArtifactService` (normalisation de
nom de fichier, vérification anti-traversée de chemin, écriture atomique),
étendu avec une séparation stricte raw/prepared et une structure de version.
GCS/S3 ne sont volontairement PAS implémentés ici : seuls des points
d'extension `DatasetStorage` sont prévus pour une Phase future.
"""

from __future__ import annotations

import json
import os
import re
import shutil
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

    @abstractmethod
    def save_canonical(
        self,
        company_id: UUID,
        dataset_id: UUID,
        version: int,
        entities: dict[str, list[dict[str, Any]]],
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

    def save_canonical(
        self,
        company_id: UUID,
        dataset_id: UUID,
        version: int,
        entities: dict[str, list[dict[str, Any]]],
    ) -> str:
        directory = self._version_dir(company_id, dataset_id, version) / "canonical"
        payload = json.dumps(entities, default=str).encode("utf-8")
        return str(self._write_bytes(directory, "entities.json", payload))

    def _version_dir(self, company_id: UUID, dataset_id: UUID, version: int) -> Path:
        return self._root / str(company_id) / "datasets" / str(dataset_id) / f"v{version}"

    def prepared_path(self, company_id: UUID, dataset_id: UUID, version: int) -> Path:
        """Emplacement canonique du JSON nettoyé, indépendant de l'origine
        (pipeline actuel ou legacy) du fichier brut original."""
        return self._version_dir(company_id, dataset_id, version) / "prepared" / "prepared.json"

    def metadata_path(self, company_id: UUID, dataset_id: UUID, version: int) -> Path:
        return self._version_dir(company_id, dataset_id, version) / "metadata" / "metadata.json"

    def canonical_path(self, company_id: UUID, dataset_id: UUID, version: int) -> Path:
        return self._version_dir(company_id, dataset_id, version) / "canonical" / "entities.json"

    def delete_dataset(self, company_id: UUID, dataset_id: UUID) -> None:
        directory = (self._root / str(company_id) / "datasets" / str(dataset_id)).resolve()
        if self._root not in directory.parents:
            raise ValueError("Chemin de dataset invalide (traversée de répertoire détectée)")
        if directory.exists():
            shutil.rmtree(directory)

    def _write_bytes(self, directory: Path, safe_name: str, content: bytes) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(directory.stat().st_mode | 0o2770)
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
            os.chmod(destination, 0o660)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return destination

class S3DatasetStorage(DatasetStorage):
    """Stockage S3-compatible (AWS S3, MinIO, Cloudflare R2, Railway Bucket)."""

    def __init__(
        self,
        bucket: str,
        access_key: str,
        secret_key: str,
        endpoint_url: str | None = None,
        region: str = "auto",
        local_fallback: DatasetStorage | None = None,
    ) -> None:
        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self.region = region
        self.local_fallback = local_fallback
        try:
            import boto3
            from botocore.config import Config
            s3_config = Config(connect_timeout=1, read_timeout=1, retries={"max_attempts": 0})
            self._s3 = boto3.client(
                "s3",
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                endpoint_url=endpoint_url,
                region_name=region if region != "auto" else None,
                config=s3_config,
            )
        except Exception:
            self._s3 = None

    def _s3_key(self, company_id: UUID, dataset_id: UUID, version: int, folder: str, filename: str) -> str:
        safe_name = _SAFE_FILENAME.sub("_", Path(filename).name) or "dataset"
        return f"{company_id}/datasets/{dataset_id}/v{version}/{folder}/{safe_name}"

    def save_raw(
        self,
        company_id: UUID,
        dataset_id: UUID,
        version: int,
        filename: str,
        content: bytes,
    ) -> str:
        key = self._s3_key(company_id, dataset_id, version, "raw", filename)
        if self._s3 is not None:
            try:
                self._s3.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=content,
                    ContentType="application/octet-stream",
                )
                if self.local_fallback:
                    self.local_fallback.save_raw(company_id, dataset_id, version, filename, content)
                return f"s3://{self.bucket}/{key}"
            except Exception:
                if self.local_fallback:
                    return self.local_fallback.save_raw(company_id, dataset_id, version, filename, content)
                raise
        if self.local_fallback:
            return self.local_fallback.save_raw(company_id, dataset_id, version, filename, content)
        raise RuntimeError("Aucun stockage S3 ni fallback local disponible")

    def save_prepared(
        self,
        company_id: UUID,
        dataset_id: UUID,
        version: int,
        rows: list[dict[str, Any]],
    ) -> str:
        key = self._s3_key(company_id, dataset_id, version, "prepared", "prepared.json")
        payload = json.dumps(rows, default=str).encode("utf-8")
        if self._s3 is not None:
            try:
                self._s3.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=payload,
                    ContentType="application/json",
                )
                if self.local_fallback:
                    self.local_fallback.save_prepared(company_id, dataset_id, version, rows)
                return f"s3://{self.bucket}/{key}"
            except Exception:
                if self.local_fallback:
                    return self.local_fallback.save_prepared(company_id, dataset_id, version, rows)
                raise
        if self.local_fallback:
            return self.local_fallback.save_prepared(company_id, dataset_id, version, rows)
        raise RuntimeError("Aucun stockage S3 ni fallback local disponible")

    def save_metadata(
        self,
        company_id: UUID,
        dataset_id: UUID,
        version: int,
        metadata: dict[str, Any],
    ) -> str:
        key = self._s3_key(company_id, dataset_id, version, "metadata", "metadata.json")
        payload = json.dumps(metadata, default=str).encode("utf-8")
        if self._s3 is not None:
            try:
                self._s3.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=payload,
                    ContentType="application/json",
                )
                if self.local_fallback:
                    self.local_fallback.save_metadata(company_id, dataset_id, version, metadata)
                return f"s3://{self.bucket}/{key}"
            except Exception:
                if self.local_fallback:
                    return self.local_fallback.save_metadata(company_id, dataset_id, version, metadata)
                raise
        if self.local_fallback:
            return self.local_fallback.save_metadata(company_id, dataset_id, version, metadata)
        raise RuntimeError("Aucun stockage S3 ni fallback local disponible")

    def save_canonical(
        self,
        company_id: UUID,
        dataset_id: UUID,
        version: int,
        entities: dict[str, list[dict[str, Any]]],
    ) -> str:
        key = self._s3_key(company_id, dataset_id, version, "canonical", "entities.json")
        payload = json.dumps(entities, default=str).encode("utf-8")
        if self._s3 is not None:
            try:
                self._s3.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=payload,
                    ContentType="application/json",
                )
                if self.local_fallback:
                    self.local_fallback.save_canonical(company_id, dataset_id, version, entities)
                return f"s3://{self.bucket}/{key}"
            except Exception:
                if self.local_fallback:
                    return self.local_fallback.save_canonical(company_id, dataset_id, version, entities)
                raise
        if self.local_fallback:
            return self.local_fallback.save_canonical(company_id, dataset_id, version, entities)
        raise RuntimeError("Aucun stockage S3 ni fallback local disponible")

    @property
    def _root(self) -> Path:
        if self.local_fallback and hasattr(self.local_fallback, "_root"):
            return self.local_fallback._root
        return Path("data/artifacts/company_datasets").resolve()

    def prepared_path(self, company_id: UUID, dataset_id: UUID, version: int) -> Path:
        if self.local_fallback and hasattr(self.local_fallback, "prepared_path"):
            return self.local_fallback.prepared_path(company_id, dataset_id, version)
        return (self._root / str(company_id) / "datasets" / str(dataset_id) / f"v{version}" / "prepared" / "prepared.json").resolve()

    def metadata_path(self, company_id: UUID, dataset_id: UUID, version: int) -> Path:
        if self.local_fallback and hasattr(self.local_fallback, "metadata_path"):
            return self.local_fallback.metadata_path(company_id, dataset_id, version)
        return (self._root / str(company_id) / "datasets" / str(dataset_id) / f"v{version}" / "metadata" / "metadata.json").resolve()

    def canonical_path(self, company_id: UUID, dataset_id: UUID, version: int) -> Path:
        if self.local_fallback and hasattr(self.local_fallback, "canonical_path"):
            return self.local_fallback.canonical_path(company_id, dataset_id, version)
        return (self._root / str(company_id) / "datasets" / str(dataset_id) / f"v{version}" / "canonical" / "entities.json").resolve()

    def delete_dataset(self, company_id: UUID, dataset_id: UUID) -> None:
        if self.local_fallback and hasattr(self.local_fallback, "delete_dataset"):
            self.local_fallback.delete_dataset(company_id, dataset_id)
        if self._s3 is not None:
            try:
                prefix = f"{company_id}/datasets/{dataset_id}/"
                response = self._s3.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
                objects = [{"Key": obj["Key"]} for obj in response.get("Contents", [])]
                if objects:
                    self._s3.delete_objects(Bucket=self.bucket, Delete={"Objects": objects})
            except Exception:
                pass

