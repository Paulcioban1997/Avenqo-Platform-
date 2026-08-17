"""Schémas HTTP business-friendly : statut d'entraînement et prédictions.

Ces schémas n'exposent jamais de nom de modèle, d'algorithme ni de métrique
technique — uniquement des messages métier et un résultat.
"""

from __future__ import annotations

from typing import Any, Mapping
from uuid import UUID

from pydantic import BaseModel


class TrainingStatusResponse(BaseModel):
    ai_job_id: UUID
    ready: bool
    message: str


class PredictionRequest(BaseModel):
    module_code: str
    task_code: str
    features: Mapping[str, Any]


class PredictionResponse(BaseModel):
    result: Any
    confidence: float | None = None


class BusinessDecisionResponse(BaseModel):
    """Sortie 100% business : jamais de nom de modèle, d'algorithme ni de métrique."""

    title: str
    impact: str
    recommendation: str
    priority: str


class PortfolioDecisionsRequest(BaseModel):
    """Phase 22 : décisions métier agrégées sur le portefeuille client d'un module."""

    module_code: str


class RetrainingCheckRequest(BaseModel):
    module_code: str
    task_code: str


class RetrainingCheckResponse(BaseModel):
    queued: bool
    ai_job_id: UUID | None = None


class ModelVersionSummaryResponse(BaseModel):
    """Fiche interne d'une version — jamais exposée telle quelle au frontend."""

    version: str
    version_number: int
    parent_version: str | None
    model_name: str
    is_active: bool
    state: str
    retraining_reason: str | None
    created_at: str


class ModelVersionListResponse(BaseModel):
    versions: list[ModelVersionSummaryResponse]


class ModelVersionCompareRequest(BaseModel):
    module_code: str
    task_code: str
    version_a: str
    version_b: str


class ModelVersionCompareResponse(BaseModel):
    version_a: str
    version_b: str
    metric_name: str
    higher_is_better: bool
    value_a: float | None
    value_b: float | None
    delta: float | None
    b_is_better: bool
    blocked_by_drift: bool


class ModelVersionRollbackRequest(BaseModel):
    module_code: str
    task_code: str
    target_version: str


class ModelVersionRollbackResponse(BaseModel):
    previous_active_version: str | None
    target_version: str
    activated: bool


class BusinessOpportunityResponse(BaseModel):
    """Opportunité 100% business (Phase 25) — jamais de nom de modèle ni de jargon ML."""

    id: UUID
    capability: str
    title: str
    summary: str
    direction: str
    priority: str
    severity: str
    confidence: float
    estimated_impact: float | None
    impact_unit: str | None
    recommended_action: str
    status: str
    created_at: str


class PortfolioOpportunitiesResponse(BaseModel):
    """Phase 25 : opportunités métier agrégées sur le portefeuille d'un module."""

    company_id: UUID
    opportunity_count: int
    critical_count: int
    high_count: int
    opportunities: list[BusinessOpportunityResponse]
