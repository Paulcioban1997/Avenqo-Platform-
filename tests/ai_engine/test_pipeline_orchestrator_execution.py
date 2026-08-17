"""Valide que `PipelineOrchestrator.execute()` enchaîne réellement le pipeline officiel :

Dataset → Cleaning → FeatureEngineering → AIEngine (ExecutionStrategy →
CandidateRegistry → Optimizer → Trainer → Evaluator → ModelSelector) →
ModelRegistry, sans étape simulée ni raccourci.
"""

from pathlib import Path
from uuid import UUID

from shared.ai_engine.cleaning.cleaner import Cleaner
from shared.ai_engine.connectors.registry import ConnectorRegistry
from shared.ai_engine.contracts import (
    DatasetArtifact,
    DetectedSchema,
    Task,
    TenantContext,
)
from shared.ai_engine.dataset_builder.service import DatasetBuilder
from shared.ai_engine.engine import AIEngine
from shared.ai_engine.evaluation.service import EvaluationService
from shared.ai_engine.experiments import InMemoryExperimentRepository
from shared.ai_engine.feature_engineering.feature_builder import FeatureBuilder
from shared.ai_engine.feature_engineering.registry import FeatureProviderRegistry
from shared.ai_engine.model_registry.repository import FileSystemModelRepository
from shared.ai_engine.model_registry.serializer import JoblibArtifactSerializer
from shared.ai_engine.pipelines.service import PipelineOrchestrator
from shared.ai_engine.registry.registry import ModelRegistry
from shared.ai_engine.training.service import TrainingService


class PassthroughFeatureProvider:
    """Fournisseur de features minimal, sans règle métier, pour le test."""

    module_code = "retail"

    def build_features(self, task: Task, dataset: DatasetArtifact) -> DatasetArtifact:
        return dataset


class UppercaseUriRule:
    """Règle de nettoyage triviale utilisée pour prouver que `Cleaner` est bien appelé."""

    def apply(self, data: DatasetArtifact) -> DatasetArtifact:
        return DatasetArtifact(
            tenant=data.tenant,
            module_code=data.module_code,
            task_code=data.task_code,
            uri=data.uri.upper(),
            schema=data.schema,
        )


class UppercaseFeatureStrategy:
    def __call__(self, data: DatasetArtifact) -> DatasetArtifact:
        return DatasetArtifact(
            tenant=data.tenant,
            module_code=data.module_code,
            task_code=data.task_code,
            uri=f"{data.uri}-features",
            schema=data.schema,
        )


class FakeMetrics:
    def __init__(self, scores: dict[str, float]) -> None:
        self._scores = scores

    def evaluate(self, model: str, dataset: DatasetArtifact) -> dict[str, float]:
        return {"score": self._scores[model]}


class FakeCandidate:
    def __init__(self, candidate_id: str) -> None:
        self.candidate_id = candidate_id
        self.seen_dataset_uri: str | None = None

    def train(self, dataset: DatasetArtifact) -> str:
        self.seen_dataset_uri = dataset.uri
        return self.candidate_id


def _build_source() -> DatasetArtifact:
    return DatasetArtifact(
        tenant=TenantContext(UUID("00000000-0000-0000-0000-000000000001")),
        module_code="retail",
        task_code="demand",
        uri="datasets/demand.csv",
        schema=DetectedSchema(tables={}),
    )


def test_execute_enchaine_reellement_cleaning_feature_engineering_et_automl(
    tmp_path: Path,
) -> None:
    providers = FeatureProviderRegistry()
    providers.register(PassthroughFeatureProvider())

    orchestrator = PipelineOrchestrator(
        connectors=ConnectorRegistry(),
        datasets=DatasetBuilder(providers),
        training=TrainingService(
            model_repository=FileSystemModelRepository(tmp_path / "repository"),
            experiments=InMemoryExperimentRepository(),
        ),
    )

    cleaner = Cleaner([UppercaseUriRule()])
    feature_builder = FeatureBuilder()
    feature_builder.register("retail", "demand", UppercaseFeatureStrategy())

    strong = FakeCandidate("strong")
    weak = FakeCandidate("weak")
    evaluator = EvaluationService(FakeMetrics({"weak": 0.4, "strong": 0.9}), "score")
    engine = AIEngine(evaluator)

    tenant = TenantContext(UUID("00000000-0000-0000-0000-000000000001"))
    model_registry = ModelRegistry(tmp_path, serializer=JoblibArtifactSerializer())

    result = orchestrator.execute(
        module_code="retail",
        task=Task(code="demand", name="Demand forecast"),
        source=_build_source(),
        engine=engine,
        candidates=[weak, strong],
        tenant=tenant,
        version="v1",
        model_registry=model_registry,
        cleaner=cleaner,
        feature_builder=feature_builder,
    )

    assert result.automl.candidate_id == "strong"
    # Cleaning (upper-case) then feature engineering (suffix) were really applied
    # before the dataset reached the candidates.
    assert strong.seen_dataset_uri == "DATASETS/DEMAND.CSV-features"
    assert weak.seen_dataset_uri == "DATASETS/DEMAND.CSV-features"
    # The winning candidate's model was really persisted through ModelRegistry.
    assert result.model_path.is_file()
    assert JoblibArtifactSerializer().load(result.model_path) == "strong"
