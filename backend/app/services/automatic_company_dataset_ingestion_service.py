"""Automatic orchestration for the universal company-data pipeline.

Phase 26 deliberately kept ambiguous semantic mappings behind a manual review
state.  That is a safe foundation, but it is not the product experience Avenqo
wants: importing business data must continue automatically whenever ambiguity
is limited to optional/low-confidence columns.

This service layers production orchestration on top of the conservative
``CompanyDatasetIngestionService`` without weakening its core guarantees:

* EXACT/HIGH mappings remain accepted by the Phase 26 service.
* MEDIUM mappings are auto-accepted when they are type-compatible.
* LOW mappings are accepted only when the score is still strong enough and the
  mapper did not flag a semantic type incompatibility.
* UNRESOLVED/type-incompatible columns are ignored instead of blocking the
  whole dataset. They remain visible in mapping metadata for audit/manual
  correction later.
* A READY universal dataset is materialized as a canonical training CSV so the
  existing TrainingDispatcher can consume CSV/XLSX/JSON/Parquet imports through
  its proven training -> evaluation -> ModelRegistry -> activation pipeline.

The raw uploaded artifact is never overwritten. ``DatasetVersion.artifact_path``
continues to point at the original tenant-isolated file; ``Dataset.source`` is
updated to the generated training CSV only after the dataset is READY.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Dataset, DatasetStatus
from backend.app.services.company_dataset_ingestion_service import (
    CompanyDatasetIngestionService,
    InvalidMappingError,
)
from backend.app.services.data_import_policy import DataImportPolicy
from backend.app.services.dataset_relationship_service import DatasetRelationshipService
from backend.app.services.training_dispatcher import TrainingDispatcher
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_ingestion.column_mapper import MappingConfidence, MappingProvenance
from shared.ai_engine.dataset_ingestion.storage import LocalDatasetStorage

logger = logging.getLogger(__name__)


class AutomaticCompanyDatasetIngestionService(CompanyDatasetIngestionService):
    """Production wrapper that turns Phase 26 into a hands-off data pipeline."""

    _SAFE_LOW_SCORE = 0.70
    _AUTO_POLICY_VERSION = "automatic-business-data-v1"

    def __init__(
        self,
        session: Session,
        storage: LocalDatasetStorage,
        quota: DataImportPolicy,
        max_upload_bytes: int,
        dispatcher: TrainingDispatcher,
    ) -> None:
        super().__init__(
            session=session,
            storage=storage,
            quota=quota,
            max_upload_bytes=max_upload_bytes,
        )
        self._dispatcher = dispatcher

    def upload(
        self,
        tenant: TenantContext,
        module_code: str,
        filename: str,
        content: bytes,
    ) -> Dataset:
        dataset = super().upload(tenant, module_code, filename, content)

        try:
            dataset = self._hold_mapping_conflicts(dataset)
            dataset = self._resolve_mapping_without_blocking(tenant, dataset)
            if dataset.status == DatasetStatus.READY:
                dataset = self._finalize_automatic_pipeline(tenant, dataset)
        except Exception:
            # Importing company data must never be turned into a failed upload
            # merely because downstream automation could not complete. The raw
            # data and Phase 26 metadata remain persisted and diagnosable.
            logger.exception(
                "Automatic universal-data orchestration failed for company=%s dataset=%s",
                tenant.company_id,
                dataset.id,
            )

        return dataset

    def _hold_mapping_conflicts(self, dataset: Dataset) -> Dataset:
        if dataset.mapping is None:
            return dataset
        payload = dict(dataset.mapping.mapping_json or {})
        accepted = dict(payload.get("accepted") or {})
        conflicts = self._mapping_conflicts(accepted)
        if accepted and not conflicts:
            return dataset
        if conflicts:
            dataset.mapping.mapping_json = {
                **payload,
                "required_confirmation": conflicts,
            }
        dataset.mapping.approved = False
        dataset.status = DatasetStatus.MAPPING_REQUIRED
        self._session.add(dataset)
        self._session.commit()
        return dataset

    def submit_mapping(
        self,
        tenant: TenantContext,
        dataset_id: UUID,
        overrides: dict[str, str],
    ) -> Dataset:
        if len(set(overrides.values())) != len(overrides):
            raise InvalidMappingError(
                "Each canonical field can be assigned to only one source column."
            )
        dataset = self.get(tenant, dataset_id)
        payload = dict(dataset.mapping.mapping_json or {}) if dataset.mapping is not None else {}
        for conflict in payload.get("required_confirmation") or ():
            canonical = str(conflict.get("canonical_field") or "")
            columns = {str(column) for column in conflict.get("columns") or ()}
            selected = [column for column in overrides if column in columns]
            if canonical:
                selected = [
                    column for column in selected if overrides[column] == canonical
                ]
            if (canonical and len(selected) != 1) or (not canonical and not selected):
                raise InvalidMappingError(
                    f"Select a source column for '{canonical or 'a business concept'}'."
                )
        if dataset.mapping is not None and overrides:
            accepted = dict(payload.get("accepted") or {})
            provenance = dict(payload.get("provenance") or {})
            selected_fields = set(overrides.values())
            for column, canonical in tuple(accepted.items()):
                if canonical in selected_fields and column not in overrides:
                    accepted.pop(column)
                    provenance.pop(column, None)
            dataset.mapping.mapping_json = {
                **payload,
                "accepted": accepted,
                "provenance": provenance,
                "required_confirmation": [],
            }
        dataset = super().submit_mapping(tenant, dataset_id, overrides)
        return self._finalize_automatic_pipeline(tenant, dataset)

    def reconcile_existing(self, tenant: TenantContext) -> tuple[Dataset, ...]:
        datasets = tuple(
            self._session.scalars(
                select(Dataset).where(
                    Dataset.company_id == tenant.company_id,
                    Dataset.status == DatasetStatus.MAPPING_REQUIRED,
                )
            ).all()
        )
        reconciled: list[Dataset] = []
        for dataset in datasets:
            try:
                self._refresh_mapping_suggestions(dataset)
                resolved = self._resolve_mapping_without_blocking(tenant, dataset)
                if resolved.status == DatasetStatus.READY:
                    resolved = self._finalize_automatic_pipeline(tenant, resolved)
                reconciled.append(resolved)
            except Exception:
                logger.exception(
                    "Existing dataset reconciliation failed for company=%s dataset=%s",
                    tenant.company_id,
                    dataset.id,
                )
        return tuple(reconciled)

    def _refresh_mapping_suggestions(self, dataset: Dataset) -> None:
        if dataset.mapping is None:
            return
        rows = self._reload_current_version_rows(dataset)
        columns = tuple(dict.fromkeys(key for row in rows for key in row)) if rows else ()
        suggestions = self._mapper.suggest(columns, rows)
        accepted = {
            item.original_column: item.suggested_field
            for item in suggestions
            if item.confidence in {MappingConfidence.EXACT, MappingConfidence.HIGH}
            and item.suggested_field is not None
        }
        dataset.mapping.mapping_json = {
            "suggestions": [self._suggestion_to_dict(item) for item in suggestions],
            "accepted": accepted,
            "provenance": {column: MappingProvenance.AUTO.value for column in accepted},
        }
        dataset.mapping.approved = False
        self._session.add(dataset)
        self._session.commit()

    def _resolve_mapping_without_blocking(
        self,
        tenant: TenantContext,
        dataset: Dataset,
    ) -> Dataset:
        """Finalize a MAPPING_REQUIRED dataset using only safe automatic choices.

        Ambiguous columns that cannot be resolved safely are deliberately left
        unmapped. They do not prevent cleaning/profiling/readiness for the
        columns that Avenqo *does* understand.
        """

        if dataset.status != DatasetStatus.MAPPING_REQUIRED or dataset.mapping is None:
            return dataset

        payload = dict(dataset.mapping.mapping_json or {})
        accepted = dict(payload.get("accepted") or {})
        provenance = dict(payload.get("provenance") or {})
        suggestions = list(payload.get("suggestions") or [])
        used_canonical_fields = set(accepted.values())
        auto_added: list[str] = []
        ignored: list[str] = []

        conflicts = self._mapping_conflicts(accepted)
        if conflicts:
            dataset.mapping.mapping_json = {
                **payload,
                "required_confirmation": conflicts,
                "automatic_resolution": {
                    "policy": self._AUTO_POLICY_VERSION,
                    "auto_added_columns": [],
                    "ignored_columns": [],
                },
            }
            dataset.mapping.approved = False
            dataset.status = DatasetStatus.MAPPING_REQUIRED
            self._session.add(dataset)
            self._session.commit()
            return dataset

        for suggestion in suggestions:
            original = str(suggestion.get("original_column") or "")
            canonical = suggestion.get("suggested_field")
            if not original or not canonical or original in accepted:
                continue

            if self._should_auto_accept(suggestion) and canonical not in used_canonical_fields:
                accepted[original] = canonical
                provenance[original] = MappingProvenance.AUTO.value
                used_canonical_fields.add(canonical)
                auto_added.append(original)
            else:
                ignored.append(original)

        if not accepted:
            dataset.mapping.mapping_json = {
                **payload,
                "accepted": {},
                "provenance": {},
                "ignored_optional_columns": sorted(set(ignored)),
                "required_confirmation": [
                    {
                        "canonical_field": "",
                        "columns": sorted(
                            str(item.get("original_column"))
                            for item in suggestions
                            if item.get("original_column")
                        ),
                        "reason": "no_safe_canonical_mapping",
                    }
                ],
                "automatic_resolution": {
                    "policy": self._AUTO_POLICY_VERSION,
                    "auto_added_columns": [],
                    "ignored_columns": sorted(set(ignored)),
                },
            }
            dataset.mapping.approved = False
            dataset.status = DatasetStatus.MAPPING_REQUIRED
            self._session.add(dataset)
            self._session.commit()
            return dataset

        # Assign a brand-new dict so SQLAlchemy JSON mutation tracking sees the
        # change reliably on both SQLite tests and PostgreSQL production.
        dataset.mapping.mapping_json = {
            **payload,
            "accepted": accepted,
            "provenance": provenance,
            "ignored_optional_columns": sorted(set(ignored)),
            "automatic_resolution": {
                "policy": self._AUTO_POLICY_VERSION,
                "auto_added_columns": sorted(set(auto_added)),
                "ignored_columns": sorted(set(ignored)),
            },
        }

        # submit_mapping with no manual overrides reuses the accepted AUTO map,
        # performs non-destructive cleaning + quality + prepared storage, marks
        # the mapping approved, and moves the dataset to READY.
        return super().submit_mapping(tenant, dataset.id, {})

    @staticmethod
    def _mapping_conflicts(accepted: dict[str, str]) -> list[dict[str, Any]]:
        columns_by_field: dict[str, list[str]] = {}
        for column, canonical in accepted.items():
            columns_by_field.setdefault(canonical, []).append(column)
        return [
            {"canonical_field": canonical, "columns": sorted(columns)}
            for canonical, columns in sorted(columns_by_field.items())
            if len(columns) > 1
        ]

    def _finalize_automatic_pipeline(
        self,
        tenant: TenantContext,
        dataset: Dataset,
    ) -> Dataset:
        dataset = self._materialize_canonical_training_source(tenant, dataset)
        DatasetRelationshipService(self._session).refresh_for_dataset(tenant, dataset, self)
        self._dispatch_training_safely(tenant, dataset)
        return dataset

    @classmethod
    def _should_auto_accept(cls, suggestion: dict[str, Any]) -> bool:
        confidence = str(suggestion.get("confidence") or "").lower()
        score = float(suggestion.get("score") or 0.0)
        reason = str(suggestion.get("reason") or "").lower()

        if confidence == MappingConfidence.MEDIUM.value:
            # By construction SemanticColumnMapper only emits MEDIUM after the
            # semantic type compatibility guard has passed.
            return True

        if confidence == MappingConfidence.LOW.value:
            # LOW can mean either "weaker name similarity but compatible type"
            # or "strong name but incompatible semantic type". Never automate
            # the second case.
            incompatible = "incompatible" in reason or "incompatib" in reason
            return score >= cls._SAFE_LOW_SCORE and not incompatible

        return False

    def _materialize_canonical_training_source(
        self,
        tenant: TenantContext,
        dataset: Dataset,
    ) -> Dataset:
        """Create a CSV training artifact usable by the existing AI pipeline.

        Original columns are preserved and canonical aliases are added beside
        them. This keeps all information available while guaranteeing that the
        existing TaskResolution/TargetResolution/TrainingDispatcher stack can
        see standard business fields regardless of the company's source names
        or original file format.
        """

        prepared = super().get_prepared_dataset(tenant, dataset.id)
        rows = self._canonicalize_rows(list(prepared.rows), prepared.canonical_columns)
        if not rows:
            return dataset

        current_version = next((v for v in dataset.versions if v.is_current), None)
        if current_version is None or not current_version.artifact_path:
            return dataset

        raw_path = Path(current_version.artifact_path)
        prepared_dir = raw_path.parent.parent / "prepared"
        prepared_dir.mkdir(parents=True, exist_ok=True)
        destination = prepared_dir / "training.csv"

        fieldnames = list(dict.fromkeys(key for row in rows for key in row.keys()))
        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                dir=prepared_dir,
                delete=False,
            ) as temporary:
                writer = csv.DictWriter(temporary, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
                temporary.flush()
                temporary_path = Path(temporary.name)
            temporary_path.replace(destination)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        # Keep the raw original in DatasetVersion.artifact_path. Downstream AI
        # jobs read Dataset.source, so point that field at the canonical CSV.
        dataset.source = str(destination)
        self._session.add(dataset)
        self._session.commit()
        return dataset

    @staticmethod
    def _canonicalize_rows(
        rows: list[dict[str, Any]],
        mapping: dict[str, str],
    ) -> list[dict[str, Any]]:
        canonicalized: list[dict[str, Any]] = []
        for row in rows:
            output = dict(row)
            for original_column, canonical_field in mapping.items():
                if original_column in row and canonical_field not in output:
                    output[canonical_field] = row[original_column]
            canonicalized.append(output)
        return canonicalized

    def _dispatch_training_safely(self, tenant: TenantContext, dataset: Dataset) -> None:
        try:
            self._dispatcher.dispatch(tenant, dataset)
        except Exception:
            # The upload is already READY. A scheduler/training outage must be
            # observable in logs but must not send the customer back to a
            # manual mapping screen or destroy their imported data.
            logger.exception(
                "Automatic training dispatch failed for company=%s dataset=%s",
                tenant.company_id,
                dataset.id,
            )
