"""Contrats immuables dÃ©crivant un entraÃ®nement IA traÃ§able."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping
from uuid import UUID, uuid4

from shared.ai_engine.contracts import TenantContext


class ExperimentStatus(StrEnum):
    """Ã‰tats possibles d'un entraÃ®nement suivi par Avenqo."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SearchMethod(StrEnum):
    """MÃ©thodes de recherche d'hyperparamÃ¨tres reconnues."""

    GRID_SEARCH = "grid_search"
    RANDOMIZED_SEARCH = "randomized_search"
    OPTUNA = "optuna"
    KERAS_TUNER = "keras_tuner"
    FIXED = "fixed"


@dataclass(frozen=True, slots=True)
class DatasetSnapshot:
    """Identifie exactement le jeu de donnÃ©es utilisÃ© par un Run."""

    dataset_id: UUID
    version: str
    fingerprint: str
    uri: str
    row_count: int
    column_count: int
    numerical_columns: tuple[str, ...] = ()
    categorical_columns: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DataPreparationRecord:
    """DÃ©crit les transformations appliquÃ©es avant l'entraÃ®nement."""

    mapping: Mapping[str, str] = field(default_factory=dict)
    dropped_columns: tuple[str, ...] = ()
    created_columns: tuple[str, ...] = ()
    feature_engineering: tuple[str, ...] = ()
    cleaning_strategy: str | None = None
    imputation_strategy: str | None = None
    encoding_strategy: str | None = None
    scaling_strategy: str | None = None


@dataclass(frozen=True, slots=True)
class SearchRecord:
    """Conserve la recherche complÃ¨te ayant sÃ©lectionnÃ© le modÃ¨le."""

    model_name: str
    method: SearchMethod
    parameter_space: Mapping[str, Any]
    best_parameters: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ReproducibilityRecord:
    """Conserve l'environnement nÃ©cessaire pour rejouer l'entraÃ®nement."""

    random_seed: int
    split_strategy: str
    split_parameters: Mapping[str, Any]
    python_version: str
    library_versions: Mapping[str, str]
    code_version: str
    deterministic: bool = True
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    """RÃ©fÃ©rence un fichier produit sans le stocker dans le Run."""

    kind: str
    uri: str
    fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class ExperimentRun:
    """DÃ©crit un entraÃ®nement complet, consultable et reproductible."""

    tenant: TenantContext
    module_code: str
    task_code: str
    dataset: DatasetSnapshot
    preparation: DataPreparationRecord
    search: SearchRecord
    reproducibility: ReproducibilityRecord
    model_version: str
    metrics: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[ArtifactReference, ...] = ()
    id: UUID = field(default_factory=uuid4)
    status: ExperimentStatus = ExperimentStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    training_duration_seconds: float | None = None
