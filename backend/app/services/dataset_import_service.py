"""Importe et profile les datasets sans entraÃ®ner de modÃ¨le."""

from collections import Counter
import csv
from datetime import datetime
from io import StringIO
from pathlib import Path
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
from modules.catalog import MODULES_BY_CODE
from modules.entitlements import ModuleAccessService
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_management.service import DatasetManagementService
from shared.ai_engine.schema_detection.detector import SchemaDetector


class DatasetImportError(ValueError):
    """Signale un fichier vide, invalide ou non supportÃ©."""


class DatasetNotFoundError(ValueError):
    """Masque aussi les datasets appartenant Ã  un autre tenant."""


class DatasetImportService:
    """Valide, stocke, profile et persiste un CSV pour un tenant."""

    def __init__(
        self,
        session: Session,
        artifacts: ArtifactService,
        access: ModuleAccessService,
        max_upload_bytes: int,
    ) -> None:
        self._session = session
        self._artifacts = artifacts
        self._access = access
        self._max_upload_bytes = max_upload_bytes

    def import_csv(
        self,
        tenant: TenantContext,
        module_code: str,
        filename: str,
        content: bytes,
    ) -> Dataset:
        if module_code not in MODULES_BY_CODE:
            raise DatasetImportError("Module Avenqo inconnu")
        self._access.require_active(tenant, module_code)
        if not filename.lower().endswith(".csv"):
            raise DatasetImportError("Seuls les fichiers CSV sont acceptÃ©s Ã  cette Ã©tape")
        if not content or len(content) > self._max_upload_bytes:
            raise DatasetImportError("Fichier vide ou taille maximale dÃ©passÃ©e")
        try:
            rows = list(csv.DictReader(StringIO(content.decode("utf-8-sig"))))
        except (UnicodeDecodeError, csv.Error) as exc:
            raise DatasetImportError("CSV invalide ou encodage non supportÃ©") from exc
        if not rows or not rows[0]:
            raise DatasetImportError("Le CSV doit contenir un en-tÃªte et au moins une ligne")

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
