"""Importe et profile les datasets sans entraîner de modèle."""

from collections import Counter
import csv
from datetime import datetime
from io import StringIO
from pathlib import Path
import shutil
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import (
    DataQualityReport,
    Dataset,
    DatasetProfile,
    DatasetStatus,
    DatasetVersion,
    DatasetVersionStatus,
)
from backend.app.services.artifact_service import ArtifactService
from backend.app.services.data_import_policy import DataImportPolicy
from modules.catalog import MODULES_BY_CODE
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_management.service import DatasetManagementService
from shared.ai_engine.registry.registry import ModelRegistry
from shared.ai_engine.schema_detection.detector import SchemaDetector
from shared.ai_engine.versioning.service import invalidate_dataset_versions


class DatasetImportError(ValueError):
    """Signale un fichier vide, invalide ou non supporté."""


class DatasetNotFoundError(ValueError):
    """Masque aussi les datasets appartenant à un autre tenant."""


class DatasetImportService:
    """Valide, stocke, profile et persiste un CSV pour un tenant."""

    def __init__(
        self,
        session: Session,
        artifacts: ArtifactService,
        quota: DataImportPolicy,
        max_upload_bytes: int,
        model_registry: ModelRegistry | None = None,
    ) -> None:
        self._session = session
        self._artifacts = artifacts
        self._quota = quota
        self._max_upload_bytes = max_upload_bytes
        self._model_registry = model_registry

    def import_csv(
        self,
        tenant: TenantContext,
        module_code: str,
        filename: str,
        content: bytes,
    ) -> Dataset:
        if module_code not in MODULES_BY_CODE:
            raise DatasetImportError("Module Avenqo inconnu")
        # L'ingestion de données est une capacité CORE Avenqo : jamais
        # subordonnée à l'activation d'un module optionnel. Seule une limite
        # de plan (nombre de datasets) s'applique ici.
        self._quota.check_dataset_quota(tenant)
        if not filename.lower().endswith(".csv"):
            raise DatasetImportError("Seuls les fichiers CSV sont acceptés à cette étape")
        max_upload_bytes = self._quota.max_upload_bytes(tenant, self._max_upload_bytes)
        if not content or len(content) > max_upload_bytes:
            raise DatasetImportError("Fichier vide ou taille maximale dépassée")
        try:
            rows = list(csv.DictReader(StringIO(content.decode("utf-8-sig"))))
        except (UnicodeDecodeError, csv.Error) as exc:
            raise DatasetImportError("CSV invalide ou encodage non supporté") from exc
        if not rows or not rows[0]:
            raise DatasetImportError("Le CSV doit contenir un en-tête et au moins une ligne")

        normalized = [{key: self._coerce(value) for key, value in row.items()} for row in rows]
        report = SchemaDetector().detect(normalized)
        validation = DatasetManagementService.validate_rows(normalized)
        missing_values = sum(field.missing_count for field in report.fields)
        total_cells = max(report.row_count * len(report.fields), 1)
        error_cells = missing_values + report.duplicate_count * len(report.fields)
        quality_score = max(0.0, round(1 - error_cells / total_cells, 4))
        dataset_id = uuid4()
        artifact_path: Path | None = None
        try:
            artifact_path = self._artifacts.save_dataset(
                tenant,
                dataset_id,
                filename,
                content,
            )
            schema_json = [
                {
                    "name": field.name,
                    "inferred_type": field.inferred_type,
                    "nullable": field.nullable,
                    "missing_count": field.missing_count,
                    "distinct_count": field.distinct_count,
                }
                for field in report.fields
            ]
            numerical = sum(
                field.inferred_type in {"integer", "number"} for field in report.fields
            )
            dataset = Dataset(
                id=dataset_id,
                company_id=tenant.company_id,
                name=Path(filename).name,
                type="csv",
                source=str(artifact_path),
                rows_count=report.row_count,
                columns_count=len(report.fields),
                status=DatasetStatus.VALIDATED,
            )
            dataset.profile = DatasetProfile(
                module_code=module_code,
                numerical_columns=numerical,
                categorical_columns=len(report.fields) - numerical,
                schema_json={"columns": schema_json},
                distribution_json=self._distributions(normalized, report.fields),
            )
            dataset.quality_report = DataQualityReport(
                duplicates=report.duplicate_count,
                missing_values=missing_values,
                invalid_dates=0,
                negative_values=self._negative_values(normalized),
                quality_score=quality_score,
            )
            version_record = DatasetVersion(
                dataset_id=dataset.id,
                version_number=1,
                name=f"{Path(filename).stem}-v1",
                status=DatasetVersionStatus.READY,
                is_current=True,
                file_name=filename,
                artifact_path=str(artifact_path),
                row_count=report.row_count,
                column_count=len(report.fields),
                checksum=DatasetManagementService.build_version_record(
                    dataset_id=str(dataset.id),
                    version_number=1,
                    module_code=module_code,
                    filename=filename,
                    source_uri=str(artifact_path),
                    content=content,
                    metadata={
                        "validation_status": validation.status.value,
                        "quality_score": quality_score,
                    },
                ).checksum,
            )
            dataset.versions = [version_record]
            self._session.add(dataset)
            self._session.commit()
            return dataset
        except Exception:
            self._session.rollback()
            if artifact_path is not None:
                self._artifacts.delete(artifact_path)
            raise

    def list(self, tenant: TenantContext) -> list[Dataset]:
        return list(self._session.scalars(
            select(Dataset)
            .where(Dataset.company_id == tenant.company_id)
            .order_by(Dataset.uploaded_at.desc())
        ))

    def get(self, tenant: TenantContext, dataset_id: UUID) -> Dataset:
        dataset = self._session.scalar(select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.company_id == tenant.company_id,
        ))
        if dataset is None:
            raise DatasetNotFoundError("Dataset introuvable")
        return dataset

    def delete(self, tenant: TenantContext, dataset_id: UUID) -> None:
        """Supprime un dataset du tenant et son dossier d'artefacts local.

        La suppression est strictement tenant-scoped : un identifiant appartenant
        à une autre entreprise reste indistinguable d'un dataset inexistant.
        La suppression passe par l'ORM pour appliquer les cascades configurées
        (versions, profil, mapping, rapport qualité) même sur les bases historiques
        dont certaines FK ne possèdent pas encore ``ON DELETE CASCADE``.
        Le dossier physique du dataset est ensuite retiré en entier afin de ne
        pas laisser de raw/prepared/training.csv orphelins.
        """

        dataset = self.get(tenant, dataset_id)
        artifact_roots = self._dataset_artifact_roots(dataset)

        try:
            # IMPORTANT: ne pas utiliser un bulk DELETE SQL ici. Un bulk delete
            # contourne les cascades ORM et cassait les anciens datasets lorsque
            # dataset_versions.dataset_id n'avait pas ON DELETE CASCADE en base.
            self._session.delete(dataset)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

        if self._model_registry is not None:
            invalidate_dataset_versions(self._model_registry, tenant, str(dataset_id))

        for root in artifact_roots:
            shutil.rmtree(root, ignore_errors=True)

    @staticmethod
    def _dataset_artifact_roots(dataset: Dataset) -> set[Path]:
        """Retourne uniquement les dossiers ``.../<company>/datasets/<dataset>``.

        On ne supprime jamais un parent générique ``datasets``/``company`` :
        chaque chemin doit contenir à la fois le company_id et le dataset_id
        attendus avant d'être accepté comme racine de suppression.
        """

        raw_paths = [dataset.source]
        raw_paths.extend(
            version.artifact_path
            for version in dataset.versions
            if version.artifact_path
        )
        roots: set[Path] = set()
        expected_dataset = str(dataset.id)
        expected_company = str(dataset.company_id)

        for raw_path in raw_paths:
            if not raw_path:
                continue
            path = Path(raw_path).resolve()
            for parent in (path, *path.parents):
                if parent.name != expected_dataset:
                    continue
                datasets_dir = parent.parent
                company_dir = datasets_dir.parent
                if datasets_dir.name == "datasets" and company_dir.name == expected_company:
                    roots.add(parent)
                break
        return roots

    @staticmethod
    def _coerce(value: str | None) -> object:
        if value is None or not value.strip():
            return None
        stripped = value.strip()
        lowered = stripped.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            return int(stripped)
        except ValueError:
            pass
        try:
            return float(stripped)
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(stripped)
        except ValueError:
            return stripped

    @staticmethod
    def _distributions(rows, fields) -> dict[str, dict[str, int]]:
        return {
            field.name: dict(Counter(
                "<missing>" if row.get(field.name) is None else str(row.get(field.name))
                for row in rows
            ).most_common(20))
            for field in fields
        }

    @staticmethod
    def _negative_values(rows) -> int:
        return sum(
            isinstance(value, (int, float)) and not isinstance(value, bool) and value < 0
            for row in rows
            for value in row.values()
        )
