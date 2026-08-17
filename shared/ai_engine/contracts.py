"""Contrats stables partagés par l'AI Engine et les modules métiers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable
from uuid import UUID


class SourceKind(StrEnum):
    CSV = "csv"
    EXCEL = "excel"
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLSERVER = "sqlserver"
    REST_API = "rest_api"


@dataclass(frozen=True, slots=True)

# TenantContext: Represente le contexte d'un locataire (tenant) dans l'application, incluant l'identifiant de l'entreprise.
class TenantContext:
    """Contexte d'entreprise vérifié transmis par le code de confiance."""

    company_id: UUID


@dataclass(frozen=True, slots=True)
class DataSource:
    kind: SourceKind
    location: str
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ColumnProfile:
    name: str
    data_type: str
    nullable: bool
    missing_count: int = 0
    duplicate_count: int = 0


@dataclass(frozen=True, slots=True)
class DetectedSchema:
    tables: Mapping[str, tuple[ColumnProfile, ...]]
    issues: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MappingCandidate:
    source_column: str
    canonical_field: str
    confidence: float


@dataclass(frozen=True, slots=True)
class DatasetArtifact:
    tenant: TenantContext
    module_code: str
    task_code: str
    uri: str
    schema: DetectedSchema


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    candidate_id: str
    metrics: Mapping[str, float]
    score: float


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    tenant: TenantContext
    module_code: str
    task_code: str
    version: str
    path: Path
    metrics: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class Task:
    code: str
    name: str
    required_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ModuleDefinition:
    code: str
    name: str
    agent_name: str
    tasks: tuple[Task, ...]


@dataclass(frozen=True, slots=True)
class BusinessStrategy:
    """Sortie métier de l'AI Strategy Planner, consommée par le pipeline technique."""

    module_code: str
    task_family: str
    target: str | None = None
    time_column: str | None = None
    granularity: str | None = None
    horizon: str | None = None
    constraints: Mapping[str, Any] = field(default_factory=dict)

    @property
    def task_code(self) -> str:
        return self.task_family.lower().replace(" ", "_").replace("-", "_")


@dataclass(frozen=True, slots=True)
class FeatureEngineeringPlan:
    """Plan de transformations explicite, testable et réutilisable."""

    tenant_id: str
    dataset_id: str
    dataset_version: str
    module_code: str
    task_family: str
    target: str | None
    excluded_columns: tuple[str, ...]
    numerical_columns: tuple[str, ...]
    categorical_columns: tuple[str, ...]
    datetime_columns: tuple[str, ...]
    text_columns: tuple[str, ...]
    identifier_columns: tuple[str, ...]
    transformations: tuple[str, ...]
    temporal_features: tuple[str, ...]
    aggregation_features: tuple[str, ...]
    missing_value_strategy: str
    encoding_strategy: str
    scaling_requirement: bool
    leakage_constraints: tuple[str, ...]
    fit_transform_safe: bool
    output_schema: tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PreparedFeatureDataset:
    """Représentation interne d'un dataset préparé pour l'étape d'exécution IA."""

    tenant_id: str
    dataset_id: str
    dataset_version: str
    module_code: str
    task_family: str
    X: Any
    y: Any | None
    feature_names: tuple[str, ...]
    feature_types: Mapping[str, str]
    target_name: str | None
    feature_plan: FeatureEngineeringPlan
    metadata: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class DataConnector(Protocol):
    kind: SourceKind

    def inspect(self, source: DataSource) -> DetectedSchema: ...

    def ingest(self, tenant: TenantContext, source: DataSource) -> str: ...


@runtime_checkable
class ColumnMapper(Protocol):
    def map_columns(
        self,
        schema: DetectedSchema,
        canonical_fields: Sequence[str],
    ) -> tuple[MappingCandidate, ...]: ...


@runtime_checkable
class FeatureProvider(Protocol):
    module_code: str

    def build_features(
        self,
        task: Task,
        dataset: DatasetArtifact,
    ) -> DatasetArtifact: ...


@runtime_checkable
class TrainingCandidate(Protocol):
    candidate_id: str

    def train(self, dataset: DatasetArtifact) -> Any: ...


@runtime_checkable
class ArtifactSerializer(Protocol):
    def save(self, model: Any, destination: Path) -> None: ...

    def load(self, source: Path) -> Any: ...



