"""Conteneur explicite des dépendances de l'AI Engine."""

from __future__ import annotations

from dataclasses import dataclass, field

from shared.ai_engine.connectors.registry import (
    ConnectorRegistry,
    build_default_connector_registry,
)
from shared.ai_engine.dataset_builder.service import DatasetBuilder
from shared.ai_engine.experiments import InMemoryExperimentRepository
from shared.ai_engine.model_registry.repository import FileSystemModelRepository
from shared.ai_engine.pipelines.service import PipelineOrchestrator
from shared.ai_engine.prediction.service import PredictionService
from shared.ai_engine.training.service import TrainingService


@dataclass(slots=True)
class AIEngineContainer:
    """Point d'assemblage utilisé par les modules pour obtenir les services IA."""

    connectors: ConnectorRegistry = field(default_factory=build_default_connector_registry)
    datasets: DatasetBuilder = field(default_factory=DatasetBuilder)
    models: FileSystemModelRepository = field(default_factory=FileSystemModelRepository)
    experiments: InMemoryExperimentRepository = field(
        default_factory=InMemoryExperimentRepository
    )

    def training_service(self) -> TrainingService:
        return TrainingService(
            model_repository=self.models,
            experiments=self.experiments,
        )

    def prediction_service(self) -> PredictionService:
        return PredictionService(model_repository=self.models)

    def pipeline_orchestrator(self) -> PipelineOrchestrator:
        return PipelineOrchestrator(
            connectors=self.connectors,
            datasets=self.datasets,
            training=self.training_service(),
        )
