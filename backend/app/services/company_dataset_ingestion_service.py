"""Ingestion universelle de datasets d'entreprise, tous formats (Phase 26).

Ce service NE remplace PAS `DatasetImportService` (chemin CSV historique,
conservÃ© pour compatibilitÃ©) : il ajoute un pipeline gÃ©nÃ©rique
CSV/XLSX/JSON/Parquet avec mapping sÃ©mantique, nettoyage, qualitÃ© et
prÃ©paration, en rÃ©utilisant les mÃªmes fondations tenant-isolÃ©es
(`ArtifactService`-like storage, `Dataset`/`DatasetVersion`/`Mapping`/
`DataQualityReport`/`DatasetProfile`).
"""

from __future__ import annotations

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
    Mapping as MappingModel,
)
from backend.app.services.data_import_policy import DataImportPolicy
from modules.catalog import MODULES_BY_CODE
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_ingestion.canonical_fields import CANONICAL_FIELDS
from shared.ai_engine.dataset_ingestion.cleaning import CompanyDatasetCleaner
from shared.ai_engine.dataset_ingestion.column_mapper import (
    ColumnMappingSuggestion,
    MappingConfidence,
    MappingProvenance,
    SemanticColumnMapper,
)
from shared.ai_engine.dataset_ingestion.exceptions import DatasetIngestionError
from shared.ai_engine.dataset_ingestion.loader import CompanyDatasetLoader
from shared.ai_engine.dataset_ingestion.prepared_dataset import PreparedCompanyDataset
from shared.ai_engine.dataset_ingestion.profiling import CompanyDatasetProfile, DatasetProfiler
from shared.ai_engine.dataset_ingestion.quality import DataQualityStatus, assess_quality
from shared.ai_engine.dataset_ingestion.readiness import CapabilityReadiness, assess_capability_readiness
from shared.ai_engine.dataset_ingestion.storage import LocalDatasetStorage
from shared.ai_engine.dataset_management.service import DatasetManagementService
from shared.ai_engine.schema_detection.detector import SchemaDetector

_AMBIGUOUS_CONFIDENCES = (MappingConfidence.MEDIUM, MappingConfidence.LOW)
_AUTO_ACCEPTED_CONFIDENCES = (MappingConfidence.EXACT, MappingConfidence.HIGH)


class DatasetNotFoundError(ValueError):
    """Masque aussi les datasets appartenant Ã  un autre tenant."""


class InvalidMappingError(ValueError):
    """Le mapping proposÃ© rÃ©fÃ©rence un champ canonique inconnu ou incohÃ©rent."""


class DatasetProfileSummary:
    """Objet de transport (non-ORM) renvoyÃ© par `GET /datasets/{id}/profile`."""

    def __init__(
        self,
        dataset: Dataset,
        profile: CompanyDatasetProfile,
        mapping_suggestions: tuple[ColumnMappingSuggestion, ...],
        review_required: bool,
        quality_status: DataQualityStatus | None,
        quality_reasons: tuple[str, ...],
        capability_readiness: tuple[CapabilityReadiness, ...],
    ) -> None:
        self.dataset = dataset
        self.profile = profile
        self.mapping_suggestions = mapping_suggestions
        self.review_required = review_required
        self.quality_status = quality_status
        self.quality_reasons = quality_reasons
        self.capability_readiness = capability_readiness


class CompanyDatasetIngestionService:
    """Pipeline universel d'ingestion : charge, mappe, nettoie, prÃ©pare."""

    def __init__(
        self,
        session: Session,
        storage: LocalDatasetStorage,
        quota: DataImportPolicy,
        max_upload_bytes: int,
    ) -> None:
        self._session = session
        self._storage = storage
        self._quota = quota
        self._max_upload_bytes = max_upload_bytes
        self._loader = CompanyDatasetLoader(max_upload_bytes)
        self._mapper = SemanticColumnMapper()
        self._profiler = DatasetProfiler()
        self._cleaner = CompanyDatasetCleaner()

    def upload(
        self,
        tenant: TenantContext,
        module_code: str,
        filename: str,
        content: bytes,
    ) -> Dataset:
        if module_code not in MODULES_BY_CODE:
            raise DatasetIngestionError("Module Avenqo inconnu")
        plan_max_bytes = self._quota.max_upload_bytes(tenant, self._max_upload_bytes)
        if not content or len(content) > plan_max_bytes:
            raise DatasetIngestionError("Fichier vide ou taille maximale dépassée pour votre offre")

        loaded = self._loader.load(filename, content)
        rows = [dict(row) for row in loaded.rows]

        existing = self._find_existing_dataset(tenant, Path(filename).name)
        # L'ingestion de données est une capacité CORE Avenqo : jamais
        # subordonnée à l'activation d'un module optionnel (retail/crm/
        # accounting). Seule une limite de plan s'applique, et uniquement
        # pour un NOUVEAU dataset (un nouvel import de fichier existant
        # crée une nouvelle version, pas une nouvelle entrée de quota).
        if existing is None:
            self._quota.check_dataset_quota(tenant)
        version_number = 1
        dataset_id = uuid4()
        if existing is not None:
            dataset_id = existing.id
            version_number = max((v.version_number for v in existing.versions), default=0) + 1
            for previous in existing.versions:
                previous.is_current = False

        raw_path = self._storage.save_raw(
            tenant.company_id, dataset_id, version_number, filename, content
        )

        schema_report = SchemaDetector().detect(rows)
        validation = DatasetManagementService.validate_rows(rows)
        suggestions = self._mapper.suggest(loaded.columns, rows)
        review_required = any(s.confidence in _AMBIGUOUS_CONFIDENCES for s in suggestions)
        accepted_mapping = {
            s.original_column: s.suggested_field
            for s in suggestions
            if s.confidence in _AUTO_ACCEPTED_CONFIDENCES and s.suggested_field is not None
        }

        dataset = existing or Dataset(
            id=dataset_id,
            company_id=tenant.company_id,
            name=Path(filename).name,
            type=loaded.source_format,
            source=raw_path,
            status=DatasetStatus.PARSING,
        )
        if existing is not None:
            # Une nouvelle version remplace le profil/mapping/qualitÃ© prÃ©cÃ©dents :
            # on les supprime explicitement et on synchronise avant de recrÃ©er,
            # pour Ã©viter un conflit d'unicitÃ© entre l'ancienne et la nouvelle ligne.
            if existing.profile is not None:
                self._session.delete(existing.profile)
            if existing.mapping is not None:
                self._session.delete(existing.mapping)
            if existing.quality_report is not None:
                self._session.delete(existing.quality_report)
            self._session.flush()
            self._session.expire(existing, ["profile", "mapping", "quality_report"])
        dataset.source = raw_path
        dataset.type = loaded.source_format
        dataset.rows_count = schema_report.row_count
        dataset.columns_count = len(loaded.columns)

        numerical = sum(
            field.inferred_type in {"integer", "number"} for field in schema_report.fields
        )
        dataset.profile = DatasetProfile(
            module_code=module_code,
            numerical_columns=numerical,
            categorical_columns=len(schema_report.fields) - numerical,
            schema_json={
                "columns": [
                    {
                        "name": field.name,
                        "inferred_type": field.inferred_type,
                        "nullable": field.nullable,
                        "missing_count": field.missing_count,
                        "distinct_count": field.distinct_count,
                    }
                    for field in schema_report.fields
                ]
            },
            distribution_json={},
        )

        confidence_avg = (
            sum(1.0 if s.confidence == MappingConfidence.EXACT else s.score for s in suggestions)
            / len(suggestions)
            if suggestions
            else 0.0
        )
        dataset.mapping = MappingModel(
            mapping_json={
                "suggestions": [self._suggestion_to_dict(s) for s in suggestions],
                "accepted": accepted_mapping,
                "provenance": {column: MappingProvenance.AUTO.value for column in accepted_mapping},
            },
            confidence=round(confidence_avg, 4),
            approved=not review_required,
        )

        version_record = DatasetVersion(
            dataset_id=dataset.id,
            version_number=version_number,
            name=f"{Path(filename).stem}-v{version_number}",
            status=DatasetVersionStatus.UPLOADED,
            is_current=True,
            file_name=filename,
            artifact_path=raw_path,
            row_count=schema_report.row_count,
            column_count=len(loaded.columns),
            checksum=DatasetManagementService.build_version_record(
                dataset_id=str(dataset.id),
                version_number=version_number,
                module_code=module_code,
                filename=filename,
                source_uri=raw_path,
                content=content,
                metadata={"validation_status": validation.status.value},
            ).checksum,
        )
        dataset.versions.append(version_record)

        if review_required:
            dataset.status = DatasetStatus.MAPPING_REQUIRED
            self._session.add(dataset)
            self._session.commit()
            return dataset

        try:
            self._finalize_dataset(
                tenant, dataset, rows, loaded.columns, accepted_mapping, version_number
            )
            version_record.status = DatasetVersionStatus.READY
        except Exception:
            dataset.status = DatasetStatus.FAILED
            self._session.add(dataset)
            self._session.commit()
            raise
        self._session.add(dataset)
        self._session.commit()
        return dataset

    def get(self, tenant: TenantContext, dataset_id: UUID) -> Dataset:
        dataset = self._session.scalar(
            select(Dataset).where(
                Dataset.id == dataset_id,
                Dataset.company_id == tenant.company_id,
            )
        )
        if dataset is None:
            raise DatasetNotFoundError("Dataset introuvable")
        return dataset

    def get_module_code(self, tenant: TenantContext, dataset_id: UUID) -> str | None:
        """Module Avenqo associé à l'import, utilisé uniquement pour gérer
        l'exécution de capacités métier optionnelles sur ce dataset
        (voir `CapabilityExecutionGate`) — jamais pour l'ingestion elle-même.
        """
        dataset = self.get(tenant, dataset_id)
        return dataset.profile.module_code if dataset.profile else None

    def get_profile_summary(self, tenant: TenantContext, dataset_id: UUID) -> DatasetProfileSummary:
        dataset = self.get(tenant, dataset_id)
        rows = self._reload_current_version_rows(dataset)
        columns = tuple(dict.fromkeys(key for row in rows for key in row)) if rows else ()
        profile = self._profiler.profile(rows, columns)
        suggestions = ()
        if dataset.mapping is not None:
            suggestions = tuple(
                self._dict_to_suggestion(item) for item in dataset.mapping.mapping_json.get("suggestions", [])
            )
        review_required = dataset.status == DatasetStatus.MAPPING_REQUIRED
        quality_status = None
        quality_reasons: tuple[str, ...] = ()
        if dataset.quality_report is not None:
            quality_status = self._quality_status_from_score(dataset.quality_report.quality_score)
            quality_reasons = ("Voir score de qualitÃ© dÃ©taillÃ©.",)
        mapped_fields = set(
            (dataset.mapping.mapping_json.get("accepted") or {}).values()
            if dataset.mapping is not None
            else ()
        )
        readiness = assess_capability_readiness(mapped_fields)
        return DatasetProfileSummary(
            dataset=dataset,
            profile=profile,
            mapping_suggestions=suggestions,
            review_required=review_required,
            quality_status=quality_status,
            quality_reasons=quality_reasons,
            capability_readiness=readiness,
        )

    def submit_mapping(
        self,
        tenant: TenantContext,
        dataset_id: UUID,
        overrides: dict[str, str],
    ) -> Dataset:
        dataset = self.get(tenant, dataset_id)
        for canonical_field in overrides.values():
            if canonical_field not in CANONICAL_FIELDS:
                raise InvalidMappingError(f"Champ canonique inconnu : '{canonical_field}'")

        existing_mapping = dataset.mapping
        accepted: dict[str, str] = {}
        provenance: dict[str, str] = {}
        if existing_mapping is not None:
            accepted.update(existing_mapping.mapping_json.get("accepted", {}))
            provenance.update(existing_mapping.mapping_json.get("provenance", {}))
        for column, canonical_field in overrides.items():
            accepted[column] = canonical_field
            provenance[column] = MappingProvenance.MANUAL.value

        rows = self._reload_current_version_rows(dataset)
        columns = tuple(dict.fromkeys(key for row in rows for key in row)) if rows else ()
        version_number = max((v.version_number for v in dataset.versions), default=1)

        try:
            self._finalize_dataset(tenant, dataset, rows, columns, accepted, version_number)
        except Exception:
            dataset.status = DatasetStatus.FAILED
            self._session.add(dataset)
            self._session.commit()
            raise

        if dataset.mapping is not None:
            dataset.mapping.mapping_json = {
                **dataset.mapping.mapping_json,
                "accepted": accepted,
                "provenance": provenance,
            }
            dataset.mapping.approved = True

        self._session.add(dataset)
        self._session.commit()
        return dataset

    def get_prepared_dataset(self, tenant: TenantContext, dataset_id: UUID) -> PreparedCompanyDataset:
        """Point d'entrÃ©e pour la passation Ã  l'entraÃ®nement (Phase 26).

        Reconstruit la reprÃ©sentation `PreparedCompanyDataset` officielle Ã 
        partir d'un dataset dÃ©jÃ  `READY`. Aucun moteur d'entraÃ®nement n'est
        dÃ©clenchÃ© ici (hors pÃ©rimÃ¨tre Phase 26) : ce point d'entrÃ©e expose
        simplement les donnÃ©es prÃªtes, dans le format canonique attendu par
        les capacitÃ©s en aval.
        """
        dataset = self.get(tenant, dataset_id)
        if dataset.status != DatasetStatus.READY:
            raise DatasetIngestionError(
                "Le dataset n'est pas prÃªt (statut attendu : READY)."
            )
        if dataset.mapping is None:
            raise DatasetIngestionError("Aucun mapping validÃ© pour ce dataset.")

        accepted_mapping: dict[str, str] = dict(dataset.mapping.mapping_json.get("accepted", {}))
        suggestions = tuple(
            self._dict_to_suggestion(item)
            for item in dataset.mapping.mapping_json.get("suggestions", [])
        )
        rows = self._reload_current_version_rows(dataset)
        columns = tuple(dict.fromkeys(key for row in rows for key in row)) if rows else ()
        cleaned_rows, cleaning_report = self._cleaner.clean(rows, accepted_mapping)
        quality = assess_quality(cleaning_report)
        profile = self._profiler.profile(cleaned_rows, columns)
        readiness = assess_capability_readiness(set(accepted_mapping.values()))
        version_number = max((v.version_number for v in dataset.versions), default=1)

        return PreparedCompanyDataset(
            company_id=tenant.company_id,
            dataset_id=dataset.id,
            version=version_number,
            canonical_columns=accepted_mapping,
            rows=tuple(cleaned_rows),
            profile=profile,
            mapping=suggestions,
            cleaning_report=cleaning_report,
            quality=quality,
            capability_readiness=readiness,
        )

    def _finalize_dataset(
        self,
        tenant: TenantContext,
        dataset: Dataset,
        rows: list[dict],
        columns: tuple[str, ...],
        accepted_mapping: dict[str, str],
        version_number: int,
    ) -> None:
        cleaned_rows, cleaning_report = self._cleaner.clean(rows, accepted_mapping)
        quality = assess_quality(cleaning_report)

        quality_score = {
            DataQualityStatus.GOOD: 0.95,
            DataQualityStatus.WARNING: 0.6,
            DataQualityStatus.POOR: 0.2,
        }[quality.status]

        if dataset.quality_report is None:
            dataset.quality_report = DataQualityReport(
                duplicates=cleaning_report.duplicates_removed,
                missing_values=cleaning_report.null_cells_detected,
                invalid_dates=0,
                negative_values=0,
                quality_score=quality_score,
            )
        else:
            dataset.quality_report.duplicates = cleaning_report.duplicates_removed
            dataset.quality_report.missing_values = cleaning_report.null_cells_detected
            dataset.quality_report.quality_score = quality_score

        self._storage.save_prepared(
            tenant.company_id, dataset.id, version_number, list(cleaned_rows)
        )
        self._storage.save_metadata(
            tenant.company_id,
            dataset.id,
            version_number,
            {
                "canonical_columns": accepted_mapping,
                "quality_status": quality.status.value,
                "quality_reasons": list(quality.reasons),
                "rows_count": len(cleaned_rows),
                "columns_count": len(columns),
            },
        )
        dataset.status = DatasetStatus.READY

    def _find_existing_dataset(self, tenant: TenantContext, name: str) -> Dataset | None:
        return self._session.scalar(
            select(Dataset).where(
                Dataset.company_id == tenant.company_id,
                Dataset.name == name,
            )
        )

    def _reload_current_version_rows(self, dataset: Dataset) -> list[dict]:
        current_version = next((v for v in dataset.versions if v.is_current), None)
        if current_version is None or current_version.artifact_path is None:
            return []
        raw_path = Path(current_version.artifact_path)
        if not raw_path.is_file():
            return []
        content = raw_path.read_bytes()
        loaded = CompanyDatasetLoader(max_upload_bytes=len(content) + 1).load(
            current_version.file_name or raw_path.name, content
        )
        return [dict(row) for row in loaded.rows]

    @staticmethod
    def _suggestion_to_dict(suggestion: ColumnMappingSuggestion) -> dict:
        return {
            "original_column": suggestion.original_column,
            "suggested_field": suggestion.suggested_field,
            "confidence": suggestion.confidence.value,
            "score": suggestion.score,
            "alternatives": list(suggestion.alternatives),
            "reason": suggestion.reason,
        }

    @staticmethod
    def _dict_to_suggestion(data: dict) -> ColumnMappingSuggestion:
        return ColumnMappingSuggestion(
            original_column=data["original_column"],
            suggested_field=data.get("suggested_field"),
            confidence=MappingConfidence(data["confidence"]),
            score=data.get("score", 0.0),
            alternatives=tuple(data.get("alternatives", ())),
            reason=data.get("reason", ""),
        )

    @staticmethod
    def _quality_status_from_score(score: float) -> DataQualityStatus:
        if score >= 0.8:
            return DataQualityStatus.GOOD
        if score >= 0.4:
            return DataQualityStatus.WARNING
        return DataQualityStatus.POOR

