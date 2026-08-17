from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from shared.ai_engine.cleaning.cleaner import Cleaner
from shared.ai_engine.connectors.registry import ConnectorRegistry
from shared.ai_engine.contracts import DatasetArtifact, Task, TenantContext, TrainingCandidate
from shared.ai_engine.core.execution_domain import ExecutionDomain
from shared.ai_engine.core.result import AutoMLResult
from shared.ai_engine.dataset_builder.service import DatasetBuilder
from shared.ai_engine.engine import AIEngine
from shared.ai_engine.feature_engineering.feature_builder import FeatureBuilder
from shared.ai_engine.registry.registry import ModelRegistry
from shared.ai_engine.training.service import TrainingService


@dataclass(frozen=True, slots=True)
class PipelinePlan:
    module_code: str
    task_code: str
    stages: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PipelineExecutionResult:
    """Résultat réel d'une exécution complète du pipeline officiel de l'AI Engine."""

    automl: AutoMLResult
    model_path: Path


class PipelineOrchestrator:
    """Assemble et exécute réellement les pipelines IA propres à chaque entreprise.

    `plan()` décrit les étapes officielles du pipeline. `execute()` les enchaîne
    réellement en réutilisant les autorités uniques déjà en place : `Cleaner`
    (nettoyage), `FeatureBuilder` (feature engineering), `DatasetBuilder`
    (construction du jeu de données), puis le pipeline officiel unique
    `AIEngine → ExecutionStrategy → CandidateRegistry → Optimizer → Trainer →
    Evaluator → ModelSelector`, et enfin `ModelRegistry` pour la persistance
    isolée par entreprise.

    Le nettoyage et le feature engineering restent des points d'extension
    explicitement injectés par l'appelant : aucune règle métier n'est codée en
    dur ici. Si aucun `Cleaner`/`FeatureBuilder` n'est fourni, l'étape
    correspondante est simplement ignorée.
    """

    def __init__(
        self,
        connectors: ConnectorRegistry,
        datasets: DatasetBuilder,
        training: TrainingService,
    ) -> None:
        self.connectors = connectors
        self.datasets = datasets
        self.training = training

    def plan(self, module_code: str, task_code: str) -> PipelinePlan:
        return PipelinePlan(
            module_code=module_code,
            task_code=task_code,
            stages=(
                "ingestion",
                "schema_detection",
                "column_mapping",
                "validation",
                "cleaning",
                "preprocessing",
                "feature_engineering",
                "dataset_builder",
                "automl",
                "evaluation",
                "model_selection",
                "model_registry",
            ),
        )

    def execute(
        self,
        module_code: str,
        task: Task,
        source: DatasetArtifact,
        engine: AIEngine,
        candidates: Sequence[TrainingCandidate],
        tenant: TenantContext,
        version: str,
        model_registry: ModelRegistry,
        cleaner: Cleaner | None = None,
        feature_builder: FeatureBuilder | None = None,
        domain: ExecutionDomain | None = None,
        model_filename: str = "model.bin",
    ) -> PipelineExecutionResult:
        """Exécute réellement la chaîne officielle pour un jeu de données donné.

        `cleaner`/`feature_builder` sont optionnels : ce sont des points
        d'extension déjà prévus par l'architecture (`cleaning.Cleaner`,
        `feature_engineering.FeatureBuilder`) qui n'embarquent aucune règle
        codée en dur ici. `dataset_builder`, `automl` (AIEngine), `evaluation`
        et `model_selection` sont toujours exécutés réellement, puisqu'ils
        forment le pipeline officiel unique.
        """

        cleaned = cleaner.clean(source) if cleaner is not None else source
        featured = (
            feature_builder.build(module_code, task.code, cleaned)
            if feature_builder is not None
            else cleaned
        )
        dataset = self.datasets.build(module_code, task, featured)

        automl_result = engine.run(dataset, candidates, domain)

        model_path = model_registry.save(
            automl_result.model,
            tenant,
            module_code,
            task.code,
            version,
            model_filename,
        )
        return PipelineExecutionResult(automl=automl_result, model_path=model_path)

