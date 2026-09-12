"""Ingestion universelle de datasets d'entreprise, tous formats (Phase 26).

Ce service NE remplace PAS `DatasetImportService` (chemin CSV historique,
conservÃ© pour compatibilitÃ©) : il ajoute un pipeline gÃ©nÃ©rique
CSV/XLSX/JSON/Parquet avec mapping sÃ©mantique, nettoyage, qualitÃ© et
prÃ©paration, en rÃ©utilisant les mÃªmes fondations tenant-isolÃ©es
(`ArtifactService`-like storage, `Dataset`/`DatasetVersion`/`Mapping`/
`DataQualityReport`/`DatasetProfile`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.models import (
    DataQualityReport,
    Dataset,
    DatasetProfile,
    DatasetStatus,
    DatasetVersion,
    DatasetVersionStatus,
    Mapping as MappingModel,
    TrainingJob,
)
from backend.app.services.data_import_policy import DataImportPolicy
from backend.app.services import retail_kpi_cache
from modules.catalog import MODULES_BY_CODE
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_ingestion.canonical_fields import CANONICAL_FIELDS
from shared.ai_engine.dataset_ingestion.canonical_retail import (
    CanonicalRetailContext,
    project_flat_canonical_retail,
)
from shared.ai_engine.dataset_ingestion.cleaning import CompanyDatasetCleaner
from shared.ai_engine.dataset_ingestion.column_mapper import (
    ColumnMappingSuggestion,
    MappingConfidence,
    MappingProvenance,
    SemanticColumnMapper,
)
from shared.ai_engine.dataset_ingestion.exceptions import (
    DatasetArtifactMissingError,
    DatasetIngestionError,
)
from shared.ai_engine.dataset_ingestion.loader import CompanyDatasetLoader
from shared.ai_engine.dataset_ingestion.prepared_dataset import PreparedCompanyDataset
from shared.ai_engine.dataset_ingestion.profiling import CompanyDatasetProfile, DatasetProfiler
from shared.ai_engine.dataset_ingestion.quality import DataQualityStatus, assess_quality
from shared.ai_engine.dataset_ingestion.readiness import CapabilityReadiness, assess_capability_readiness
from shared.ai_engine.dataset_ingestion.storage import LocalDatasetStorage
from shared.ai_engine.dataset_management.service import DatasetManagementService
from shared.ai_engine.schema_detection.detector import SchemaDetector

_AMBIGUOUS_CONFIDENCES = (MappingConfidence.LOW, MappingConfidence.UNRESOLVED)
_AUTO_ACCEPTED_CONFIDENCES = (
    MappingConfidence.EXACT,
    MappingConfidence.HIGH,
    MappingConfidence.MEDIUM,
)


class DatasetNotFoundError(ValueError):
    """Masque aussi les datasets appartenant Ã  un autre tenant."""


CompanyDatasetNotFoundError = DatasetNotFoundError


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
        
        # Auto-mapping multi-signal sans intervention client
        raw_accepted = {
            s.original_column: s.suggested_field
            for s in suggestions
            if s.confidence in _AUTO_ACCEPTED_CONFIDENCES and s.suggested_field is not None
        }
        # Dé-dupliquer les champs canoniques pour attribuer la meilleure colonne
        best_by_canonical: dict[str, tuple[str, float]] = {}
        for s in suggestions:
            if s.original_column in raw_accepted and s.suggested_field:
                canon = s.suggested_field
                if canon not in best_by_canonical or s.score > best_by_canonical[canon][1]:
                    best_by_canonical[canon] = (s.original_column, s.score)
        accepted_mapping = {col: canon for canon, (col, _) in best_by_canonical.items()}
        review_required = False

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

        try:
            self._persist_cleaning(
                tenant, dataset, rows, loaded.columns, accepted_mapping, version_number
            )
        except Exception:
            dataset.status = DatasetStatus.FAILED
            self._session.add(dataset)
            self._session.commit()
            raise
        dataset.status = DatasetStatus.READY
        version_record.status = DatasetVersionStatus.READY
        self._session.add(dataset)
        self._session.commit()
        if dataset.status == DatasetStatus.READY and self._expected_row_count(dataset) > 50_000:
            retail_kpi_cache.read_or_schedule(tenant, dataset)
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

    def delete_if_exists(self, tenant: TenantContext, dataset_id: UUID) -> None:
        dataset = self._session.scalar(
            select(Dataset).where(
                Dataset.id == dataset_id,
                Dataset.company_id == tenant.company_id,
            )
        )
        if dataset is None:
            return
        try:
            self._session.execute(
                delete(TrainingJob).where(
                    TrainingJob.dataset_id == dataset_id,
                    TrainingJob.company_id == tenant.company_id,
                )
            )
            self._session.delete(dataset)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        self._storage.delete_dataset(tenant.company_id, dataset_id)

    def reconcile_existing(self, tenant: TenantContext) -> tuple[Dataset, ...]:
        return ()

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
        review_required = False
        quality_status = None
        quality_reasons: tuple[str, ...] = ()
        if dataset.quality_report is not None:
            quality_status = self._quality_status_from_score(dataset.quality_report.quality_score)
            quality_reasons = ("Voir score de qualitÃ© dÃ©taillÃ©.",)
        mapped_fields: set[str] = set()
        if dataset.mapping is not None:
            accepted_dict = dataset.mapping.mapping_json.get("accepted") or {}
            mapped_fields = {str(v) for v in accepted_dict.values()}
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
        version_number = self._current_version_number(dataset)

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
        if dataset.status == DatasetStatus.READY and self._expected_row_count(dataset) > 50_000:
            retail_kpi_cache.read_or_schedule(tenant, dataset)
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
        version_number = self._current_version_number(dataset)

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

    def get_cleaned_rows(
        self,
        tenant: TenantContext,
        dataset_id: UUID,
    ) -> tuple[dict, ...]:
        dataset = self.get(tenant, dataset_id)
        current_version = next((item for item in dataset.versions if item.is_current), None)
        if current_version is None or not current_version.artifact_path:
            raise DatasetIngestionError("No current cleaned dataset version is available.")
        version_number = current_version.version_number
        # Toujours dérivé de (company_id, dataset_id, version), jamais de
        # `artifact_path` : un dataset créé avant ce pipeline (import legacy)
        # peut avoir un `artifact_path` situé sous une arborescence de
        # stockage totalement différente, ce qui rendait l'ancien calcul
        # `artifact_path.parent.parent` incohérent avec l'endroit où
        # `_persist_cleaning` écrit réellement le JSON nettoyé.
        prepared_path = self._storage.prepared_path(tenant.company_id, dataset.id, version_number)
        try:
            payload = json.loads(prepared_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DatasetIngestionError("Cleaned dataset artifact is unavailable.") from exc
        if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
            raise DatasetIngestionError("Cleaned dataset artifact is invalid.")
        return tuple(dict(row) for row in payload)

    @staticmethod
    def _expected_row_count(dataset: Dataset) -> int:
        """Nombre de lignes attendu d'après les métadonnées déjà persistées.

        Sert uniquement à détecter qu'un fichier original a disparu du
        stockage (0 ligne rechargée alors qu'on en attendait) : ne doit
        jamais être utilisé pour fabriquer des données, seulement pour
        distinguer un dataset réellement vide d'un artefact perdu.
        """
        current_version = next((item for item in dataset.versions if item.is_current), None)
        if current_version is not None and current_version.row_count:
            return int(current_version.row_count)
        return int(dataset.rows_count or 0)

    def ensure_cleaning_artifacts(
        self,
        tenant: TenantContext,
        dataset: Dataset,
    ) -> None:
        if dataset.company_id != tenant.company_id:
            raise DatasetNotFoundError("Dataset introuvable")
        rows = self._reload_current_version_rows(dataset)
        if not rows and self._expected_row_count(dataset) > 0:
            # Le fichier original n'est plus lisible sur le stockage alors que
            # ce dataset avait des lignes lors de son import : ne jamais
            # persister silencieusement un artefact nettoyé à 0 ligne (cela
            # masquerait une vraie perte de données comme un succès).
            raise DatasetArtifactMissingError(
                "Le fichier original de ce dataset n'est plus disponible sur le "
                "stockage. Réimportez le fichier pour restaurer les données "
                "nettoyées."
            )
        columns = tuple(dict.fromkeys(key for row in rows for key in row)) if rows else ()
        accepted = (
            dict(dataset.mapping.mapping_json.get("accepted") or {})
            if dataset.mapping is not None
            else {}
        )
        version_number = self._current_version_number(dataset)
        self._persist_cleaning(
            tenant, dataset, rows, columns, accepted, version_number
        )
        current_version = next((item for item in dataset.versions if item.is_current), None)
        if current_version is not None and dataset.status == DatasetStatus.MAPPING_REQUIRED:
            current_version.status = DatasetVersionStatus.VALIDATED
        self._session.add(dataset)
        self._session.commit()

    def _finalize_dataset(
        self,
        tenant: TenantContext,
        dataset: Dataset,
        rows: list[dict],
        columns: tuple[str, ...],
        accepted_mapping: dict[str, str],
        version_number: int,
    ) -> None:
        self._persist_cleaning(
            tenant, dataset, rows, columns, accepted_mapping, version_number
        )
        dataset.status = DatasetStatus.READY
        current_version = next((item for item in dataset.versions if item.is_current), None)
        if current_version is not None:
            current_version.status = DatasetVersionStatus.READY

    def save_canonical_entities(
        self,
        tenant: TenantContext,
        dataset: Dataset,
        entities: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> str:
        if dataset.company_id != tenant.company_id:
            raise CompanyDatasetNotFoundError(str(dataset.id))
        version_number = self._current_version_number(dataset)
        payload = {
            name: [dict(record) for record in records]
            for name, records in entities.items()
        }
        return self._storage.save_canonical(
            tenant.company_id, dataset.id, version_number, payload
        )

    def _persist_cleaning(
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
        _, post_cleaning_report = self._cleaner.clean(
            [dict(row) for row in cleaned_rows], accepted_mapping
        )
        quality_after = assess_quality(post_cleaning_report)
        null_counts = {kind.value: count for kind, count in quality.null_counts}
        relevant_missing_values = sum(
            null_counts.get(kind, 0)
            for kind in ("required_missing", "optional_missing", "unknown")
        )
        quality_score = quality.score / 100.0

        if dataset.quality_report is None:
            dataset.quality_report = DataQualityReport(
                duplicates=cleaning_report.duplicates_removed,
                missing_values=relevant_missing_values,
                invalid_dates=0,
                negative_values=0,
                quality_score=quality_score,
            )
        else:
            dataset.quality_report.duplicates = cleaning_report.duplicates_removed
            dataset.quality_report.missing_values = relevant_missing_values
            dataset.quality_report.quality_score = quality_score

        self._storage.save_prepared(
            tenant.company_id, dataset.id, version_number, list(cleaned_rows)
        )
        canonical = project_flat_canonical_retail(
            CanonicalRetailContext(
                tenant_id=tenant.company_id,
                company_id=tenant.company_id,
                source_id=dataset.id,
                source_provider="uploaded_dataset",
                store_id=f"dataset:{dataset.id}",
            ),
            cleaned_rows,
            accepted_mapping,
        )
        self._storage.save_canonical(
            tenant.company_id,
            dataset.id,
            version_number,
            {
                name: [dict(record) for record in records]
                for name, records in canonical.entities.items()
            },
        )
        self._storage.save_metadata(
            tenant.company_id,
            dataset.id,
            version_number,
            {
                "pipeline_version": "company-ingestion-v2",
                "schema_version": "canonical-business-v1",
                "source_snapshot_id": self._current_source_snapshot_id(dataset),
                "dataset_version": version_number,
                "canonical_columns": accepted_mapping,
                "mapping_audit": self._mapping_audit(dataset),
                "inferred_data_types": {
                    str(column.get("name")): str(column.get("inferred_type"))
                    for column in (
                        dataset.profile.schema_json.get("columns", [])
                        if dataset.profile is not None
                        else []
                    )
                },
                "quality_status": quality.status.value,
                "quality_score": quality.score,
                "quality_score_before": quality.score,
                "quality_score_after": quality_after.score,
                "quality_reasons": list(quality.reasons),
                "quality_dimensions": (
                    {
                        name: getattr(quality.dimensions, name)
                        for name in quality.dimensions.__slots__
                    }
                    if quality.dimensions is not None
                    else {}
                ),
                "null_classification": null_counts,
                "column_strategies": self._build_column_strategies(
                    cleaning_report,
                    dataset.profile.schema_json.get("columns", [])
                    if dataset.profile is not None
                    else [],
                ),
                "column_reports": [
                    cr if isinstance(cr, dict) else cr.to_dict()
                    for cr in (cleaning_report.column_reports or ())
                ],
                "modifications": [
                    m if isinstance(m, dict) else m.to_dict()
                    for m in (cleaning_report.modifications or ())
                ],
                "cleaning_report": {
                    "original_row_count": cleaning_report.rows_before,
                    "cleaned_row_count": cleaning_report.rows_after,
                    "column_count": len(columns),
                    "columns_renamed": {},
                    "missing_values_detected": relevant_missing_values,
                    "structural_nulls": null_counts.get("structural_null", 0),
                    "not_applicable_fields": null_counts.get("not_applicable", 0),
                    "required_values_missing": null_counts.get("required_missing", 0),
                    "optional_values_missing": null_counts.get("optional_missing", 0),
                    "missing_values_corrected": 0,
                    "duplicate_rows_detected": cleaning_report.duplicates_removed,
                    "duplicate_rows_removed": cleaning_report.duplicates_removed,
                    "invalid_rows_rejected": 0,
                    "invalid_values_detected": cleaning_report.invalid_values_detected,
                    "invalid_values_corrected": cleaning_report.invalid_values_corrected,
                    "numeric_normalizations": cleaning_report.numeric_conversions,
                    "date_normalizations": cleaning_report.date_conversions,
                    "boolean_normalizations": cleaning_report.boolean_conversions,
                    "outlier_handling": None,
                    "mappings_applied": accepted_mapping,
                    "dataset_version": version_number,
                    "quality_score_before": quality.score,
                    "quality_score_after": quality_after.score,
                },
            },
        )

    @staticmethod
    def _mapping_audit(dataset: Dataset) -> list[dict[str, Any]]:
        if dataset.mapping is None:
            return []
        payload = dict(dataset.mapping.mapping_json or {})
        accepted = dict(payload.get("accepted") or {})
        provenance = dict(payload.get("provenance") or {})
        suggestions = {
            str(item.get("original_column")): item
            for item in payload.get("suggestions") or ()
            if isinstance(item, dict) and item.get("original_column")
        }
        return [
            {
                "source_column": column,
                "canonical_field": accepted.get(column),
                "confidence": suggestions.get(column, {}).get("score", 0.0),
                "mapping_reason": suggestions.get(column, {}).get(
                    "reason", "Unmapped: insufficient confidence."
                ),
                "mapping_method": provenance.get(column, "unmapped"),
            }
            for column in sorted(set(suggestions) | set(accepted))
        ]

    @staticmethod
    def _current_source_snapshot_id(dataset: Dataset) -> str | None:
        current = next((version for version in dataset.versions if version.is_current), None)
        return current.checksum if current is not None else None

    @classmethod
    def _build_column_strategies(
        cls,
        cleaning_report,
        profile_columns: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        profile_by_name = {
            str(column.get("name")): column for column in profile_columns if column.get("name")
        }
        output: list[dict[str, Any]] = []
        total_rows = max(cleaning_report.rows_before, 1)
        for report in cleaning_report.column_reports:
            profile = profile_by_name.get(report.column_name, {})
            inferred_type = str(profile.get("inferred_type") or report.semantic_type)
            missing_ratio = report.missing_values_detected / total_rows
            output.append(
                {
                    "column_name": report.column_name,
                    "mapped_field": report.canonical_field,
                    "inferred_type": inferred_type,
                    "semantic_type": report.semantic_type,
                    "missing_values_detected": report.missing_values_detected,
                    "missing_values_corrected": report.missing_values_corrected,
                    "invalid_values_detected": report.invalid_values_detected,
                    "invalid_values_corrected": report.invalid_values_corrected,
                    "type_conversions": report.numeric_conversions
                    + report.date_conversions
                    + report.boolean_conversions,
                    "numeric_conversions": report.numeric_conversions,
                    "date_conversions": report.date_conversions,
                    "boolean_conversions": report.boolean_conversions,
                    "applied_strategies": cls._applied_strategies(report),
                    "suggested_missing_strategy": cls._suggested_missing_strategy(
                        report.canonical_field,
                        inferred_type,
                        missing_ratio,
                    ),
                }
            )
        return output

    @staticmethod
    def _applied_strategies(report) -> list[str]:
        strategies = ["preserve_non_duplicate_rows", "preserve_missing_values"]
        if report.numeric_conversions:
            strategies.append("normalize_numeric")
        if report.date_conversions:
            strategies.append("normalize_date")
        if report.boolean_conversions:
            strategies.append("normalize_boolean")
        if report.invalid_values_corrected:
            strategies.append("coerce_invalid_to_empty")
        return strategies

    @staticmethod
    def _suggested_missing_strategy(
        canonical_field: str | None,
        inferred_type: str,
        missing_ratio: float,
    ) -> str:
        lowered_type = inferred_type.casefold()
        identifier_like = canonical_field in {
            "customer_id",
            "order_id",
            "product_id",
            "invoice_id",
            "employee_id",
        }
        time_like = canonical_field in {"order_timestamp", "invoice_date"}
        if missing_ratio >= 0.95:
            return "suppression"
        if identifier_like or time_like or lowered_type == "datetime":
            return "suppression" if missing_ratio >= 0.5 else "leave_empty"
        if lowered_type in {"integer", "number", "float", "currency"}:
            return "mean" if missing_ratio <= 0.05 else "median"
        return "mode"

    def _find_existing_dataset(self, tenant: TenantContext, name: str) -> Dataset | None:
        return self._session.scalar(
            select(Dataset).where(
                Dataset.company_id == tenant.company_id,
                Dataset.name == name,
            )
        )

    @staticmethod
    def _current_version_number(dataset: Dataset) -> int:
        version = retail_kpi_cache.current_version(dataset)
        if version is None:
            raise DatasetArtifactMissingError("No unique current dataset version is available.")
        return version.version_number

    def _reload_current_version_rows(self, dataset: Dataset) -> list[dict]:
        current_version = next((v for v in dataset.versions if v.is_current), None)
        if current_version is None or current_version.artifact_path is None:
            return []
        raw_path = Path(current_version.artifact_path)
        if not raw_path.is_file():
            # Support cross-environment paths (e.g. /data/artifacts on Linux vs local Windows paths)
            normalized_str = str(current_version.artifact_path).replace("\\", "/")
            if "company_datasets/" in normalized_str:
                rel = normalized_str.split("company_datasets/", 1)[1]
                candidates = [
                    self._storage._root / rel,
                    Path("var/artifacts/company_datasets") / rel,
                    Path("artifacts/company_datasets") / rel,
                ]
                for c in candidates:
                    if c.is_file():
                        raw_path = c
                        break
            if not raw_path.is_file() and dataset.company_id and dataset.id:
                fname = current_version.file_name or Path(current_version.artifact_path).name
                v_rel = f"{dataset.company_id}/datasets/{dataset.id}/v{current_version.version_number}/raw/{fname}"
                for base in [self._storage._root, Path("var/artifacts/company_datasets"), Path("artifacts/company_datasets")]:
                    cand = base / v_rel
                    if cand.is_file():
                        raw_path = cand
                        break
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

