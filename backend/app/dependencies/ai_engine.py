"""Dépendances FastAPI assemblant l'AI Engine partagé.

Première instanciation réelle de `AIEngineContainer` dans le backend. L'AI
Engine reste indépendant de FastAPI : ce module ne fait qu'assembler ses
services déjà existants et résoudre le dossier de stockage des modèles.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from uuid import uuid4

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

logger = logging.getLogger(__name__)


def _is_usable_directory(candidate: Path) -> bool:
    """Verifies that candidate directory exists (or can be created) and is writable."""
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        if not candidate.is_dir():
            return False
        # Canary write test: probe actual write permissions for unprivileged process
        probe = candidate / f".probe_write_{uuid4().hex[:8]}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except (PermissionError, OSError):
        return False


def get_model_registry_root() -> Path:
    """Resolves the model registry root with multi-tier fallback ensuring a guaranteed writable directory.
    
    Priority:
    1. Configured `settings.model_registry_root`
    2. Persistent storage under `settings.artifact_root / 'models'` (e.g. Railway volume)
    3. System temporary directory `tempfile.gettempdir() / 'avenqo' / 'models'`
    4. Dedicated tempdir `tempfile.mkdtemp(prefix='avenqo_models_')`
    
    Guarantees that the returned Path is an existing, writable directory. Never raises PermissionError
    or returns a non-existent/inaccessible path.
    """
    settings = get_settings()

    # 1. Configured primary path
    primary = Path(settings.model_registry_root)
    if not primary.is_absolute():
        primary = PROJECT_ROOT / primary
    if _is_usable_directory(primary):
        return primary

    # 2. Persistent volume candidate if artifact_root is configured
    try:
        artifact_path = Path(settings.artifact_root)
        if not artifact_path.is_absolute():
            artifact_path = PROJECT_ROOT / artifact_path
        persistent_candidate = artifact_path / "models"
        if persistent_candidate != primary and _is_usable_directory(persistent_candidate):
            logger.warning(
                "Primary model registry root '%s' is not writable. "
                "Using persistent volume candidate '%s'.",
                primary,
                persistent_candidate,
            )
            return persistent_candidate
    except Exception as exc:
        logger.debug("Failed checking persistent candidate: %s", exc)

    # 3. Standard temporary directory
    temp_candidate = Path(tempfile.gettempdir()) / "avenqo" / "models"
    if _is_usable_directory(temp_candidate):
        logger.warning(
            "Primary model registry root '%s' is not writable. "
            "Falling back to system temp directory '%s'.",
            primary,
            temp_candidate,
        )
        return temp_candidate

    # 4. OS-guaranteed temporary directory
    guaranteed = Path(tempfile.mkdtemp(prefix="avenqo_models_"))
    logger.warning(
        "Model registry falling back to newly created temporary directory '%s'.",
        guaranteed,
    )
    return guaranteed


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
