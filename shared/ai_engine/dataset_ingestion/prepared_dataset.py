"""Représentation finale préparée d'un dataset d'entreprise (Phase 26).

Ceci est l'entrée officielle attendue par RetailSenseAI en aval : plus aucun
service de la plateforme ne devrait consommer un dataset brut directement,
mais toujours ce `PreparedCompanyDataset`.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from shared.ai_engine.dataset_ingestion.cleaning import CleaningReport
from shared.ai_engine.dataset_ingestion.column_mapper import ColumnMappingSuggestion
from shared.ai_engine.dataset_ingestion.profiling import CompanyDatasetProfile
from shared.ai_engine.dataset_ingestion.quality import DataQualityAssessment
from shared.ai_engine.dataset_ingestion.readiness import CapabilityReadiness


@dataclass(frozen=True, slots=True)
class PreparedCompanyDataset:
    company_id: UUID
    dataset_id: UUID
    version: int
    canonical_columns: dict[str, str]
    rows: tuple[dict[str, object], ...]
    profile: CompanyDatasetProfile
    mapping: tuple[ColumnMappingSuggestion, ...]
    cleaning_report: CleaningReport
    quality: DataQualityAssessment
    capability_readiness: tuple[CapabilityReadiness, ...]
