"""Importe et profile les datasets sans entraîner de modèle."""

from collections import Counter
from collections.abc import Sequence
import csv
from datetime import datetime
from io import StringIO
from pathlib import Path
import shutil
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.models import (
    CommerceConnection,
    DataQualityReport,
    Dataset,
    DatasetProfile,
    DatasetStatus,
    DatasetVersion,
    DatasetVersionStatus,
    NormalizedCommerceRecord,
    RetailActiveSource,
    TrainingJob,
)
from backend.app.services.artifact_service import ArtifactService
from backend.app.services.audit_log_service import AuditLogService
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


class DatasetAccessDeniedError(ValueError):
    """Signale une tentative de suppression d'un dataset d'un autre tenant."""


class DatasetImportService:
    """Valide, stocke, profile et persiste un CSV pour un tenant."""

    def __init__(
        self,
        session: Session,
        artifacts: ArtifactService,
        quota: DataImportPolicy,
        max_upload_bytes: int,
        model_registry: ModelRegistry | None = None,
        audit_log: AuditLogService | None = None,
    ) -> None:
        self._session = session
        self._artifacts = artifacts
        self._quota = quota
        self._max_upload_bytes = max_upload_bytes
        self._model_registry = model_registry
        self._audit_log = audit_log

    def import_csv(
        self,
        tenant: TenantContext,
        module_code: str,
        filename: str,
        content: bytes,
    ) -> Dataset:
        if module_code not in MODULES_BY_CODE:
            raise DatasetImportError("Module Avenqo inconnu")
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

    def delete(
        self,
        tenant: TenantContext,
        dataset_id: UUID,
        *,
        actor_user_id: UUID | None = None,
    ) -> None:
        self.delete_many(
            tenant,
            [dataset_id],
            actor_user_id=actor_user_id,
        )

    def delete_many(
        self,
        tenant: TenantContext,
        dataset_ids: Sequence[UUID],
        *,
        actor_user_id: UUID | None = None,
    ) -> Sequence[UUID]:
        """Supprime atomiquement des datasets et leurs données dérivées tenant-scoped."""

        unique_ids = list(dict.fromkeys(dataset_ids))
        if not unique_ids:
            return []
        datasets = list(
            self._session.scalars(
                select(Dataset).where(
                    Dataset.id.in_(unique_ids),
                    Dataset.company_id == tenant.company_id,
                ).with_for_update()
            )
        )
        found_ids = {dataset.id for dataset in datasets}
        if found_ids != set(unique_ids):
            existing_ids = set(
                self._session.scalars(
                    select(Dataset.id).where(Dataset.id.in_(unique_ids))
                )
            )
            if existing_ids - found_ids:
                raise DatasetAccessDeniedError("Accès interdit à ce dataset")
            raise DatasetNotFoundError("Dataset introuvable")

        artifact_roots = {
            root
            for dataset in datasets
            for root in self._dataset_artifact_roots(dataset)
        }
        linked_connections = []
        connector_metadata: dict[UUID, list[dict[str, str]]] = {
            dataset_id: [] for dataset_id in unique_ids
        }
        for connection in self._session.scalars(
            select(CommerceConnection).where(
                CommerceConnection.company_id == tenant.company_id
            ).with_for_update()
        ):
            references = dict(connection.dataset_ids or {})
            matching_keys = {
                key
                for key, value in references.items()
                if self._reference_matches(value, found_ids)
            }
            if not matching_keys:
                continue
            connection.dataset_ids = {
                key: value
                for key, value in references.items()
                if key not in matching_keys
            }
            connection.sync_cursor = {}
            connection.records_processed = 0
            connection.current_entity = None
            linked_connections.append(connection)
            for dataset_id in found_ids:
                if any(
                    self._reference_matches(value, {dataset_id})
                    for value in references.values()
                ):
                    connector_metadata[dataset_id].append(
                        {
                            "connection_id": str(connection.id),
                            "provider": connection.provider,
                        }
                    )

        try:
            # Les anciennes bases sandbox ont bien un FK ON DELETE CASCADE sur
            # training_jobs.dataset_id, mais l'ORM tentait auparavant de mettre
            # dataset_id à NULL avant de supprimer le Dataset, ce qui viole le
            # NOT NULL. On supprime explicitement ces jobs en premier; leurs
            # dépendances DB (ex. model_registries) suivent leur cascade FK.
            self._session.execute(
                delete(TrainingJob).where(
                    TrainingJob.dataset_id.in_(unique_ids),
                    TrainingJob.company_id == tenant.company_id,
                )
            )
            for connection in linked_connections:
                self._session.execute(
                    delete(NormalizedCommerceRecord).where(
                        NormalizedCommerceRecord.company_id == tenant.company_id,
                        NormalizedCommerceRecord.connection_id == connection.id,
                    )
                )
                self._session.execute(
                    delete(RetailActiveSource).where(
                        RetailActiveSource.company_id == tenant.company_id,
                        RetailActiveSource.connection_id == connection.id,
                    )
                )
            self._session.execute(
                delete(RetailActiveSource).where(
                    RetailActiveSource.company_id == tenant.company_id,
                    RetailActiveSource.dataset_id.in_(unique_ids),
                )
            )
            for dataset in datasets:
                self._session.delete(dataset)
            if actor_user_id is not None and self._audit_log is not None:
                for dataset_id in unique_ids:
                    connectors = connector_metadata[dataset_id]
                    self._audit_log.record(
                        actor_user_id=actor_user_id,
                        action="dataset_deleted",
                        target_type="dataset",
                        target_id=str(dataset_id),
                        company_id=tenant.company_id,
                        metadata={
                            "result": "success",
                            "source_type": "synchronized" if connectors else "uploaded",
                            "connectors": connectors,
                        },
                        commit=False,
                    )
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

        if self._model_registry is not None:
            for dataset_id in unique_ids:
                invalidate_dataset_versions(self._model_registry, tenant, str(dataset_id))

        for root in artifact_roots:
            shutil.rmtree(root, ignore_errors=True)
        return unique_ids

    @staticmethod
    def _reference_matches(value: object, dataset_ids: set[UUID]) -> bool:
        try:
            return UUID(str(value)) in dataset_ids
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _dataset_artifact_roots(dataset: Dataset) -> set[Path]:
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
