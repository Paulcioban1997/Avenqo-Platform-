"""Dépendances FastAPI assemblant l'AI Engine partagé.

Première instanciation réelle de `AIEngineContainer` dans le backend. L'AI
Engine reste indépendant de FastAPI : ce module ne fait qu'assembler ses
services déjà existants et résoudre le dossier de stockage des modèles.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends

from backend.app.config.settings import get_settings
from backend.app.database.session import PROJECT_ROOT
from shared.ai_engine.container import AIEngineContainer
from shared.ai_engine.model_registry.repository import FileSystemModelRepository
from shared.ai_engine.model_registry.serializer import JoblibArtifactSerializer
from shared.ai_engine.prediction.service import PredictionService
from shared.ai_engine.registry.registry import ModelRegistry as AIModelRegistry
from shared.ai_engine.training.service import TrainingService

from backend.app.services.prediction_runtime import PredictionRuntime


def get_model_registry_root() -> Path:
    settings = get_settings()
    root = Path(settings.model_registry_root)
    if not root.is_absolute():
        root = PROJECT_ROOT / root
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_ai_engine_container(
    root: Path = Depends(get_model_registry_root),
) -> AIEngineContainer:
    return AIEngineContainer(models=FileSystemModelRepository(root))


def get_training_service(
    container: AIEngineContainer = Depends(get_ai_engine_container),
) -> TrainingService:
    return container.training_service()


def get_prediction_service(
    container: AIEngineContainer = Depends(get_ai_engine_container),
) -> PredictionService:
    return container.prediction_service()


def get_prediction_runtime(
    prediction_service: PredictionService = Depends(get_prediction_service),
) -> PredictionRuntime:
    return PredictionRuntime(prediction_service)


def get_ai_model_registry(
    root: Path = Depends(get_model_registry_root),
) -> AIModelRegistry:
    return AIModelRegistry(root=root, serializer=JoblibArtifactSerializer())
