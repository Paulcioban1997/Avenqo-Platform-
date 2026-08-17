"""Composition du déclenchement automatique de l'entraînement."""

from __future__ import annotations

from fastapi import BackgroundTasks, Depends
from sqlalchemy.orm import sessionmaker

from backend.app.database.session import get_session_factory
from backend.app.dependencies.ai_engine import get_ai_model_registry, get_training_service
from backend.app.services.background_job_scheduler import FastAPIBackgroundJobScheduler
from backend.app.services.target_resolution_service import TargetResolutionService
from backend.app.services.training_dispatcher import TrainingDispatcher
from shared.ai_engine.registry.registry import ModelRegistry as AIModelRegistry
from shared.ai_engine.training.service import TrainingService


def get_training_dispatcher(
    background_tasks: BackgroundTasks,
    session_factory: sessionmaker = Depends(get_session_factory),
    training_service: TrainingService = Depends(get_training_service),
    ai_model_registry: AIModelRegistry = Depends(get_ai_model_registry),
) -> TrainingDispatcher:
    dispatcher = TrainingDispatcher(
        session_factory=session_factory,
        training_service=training_service,
        ai_model_registry=ai_model_registry,
        target_resolver=TargetResolutionService(),
    )
    dispatcher.attach_scheduler(
        FastAPIBackgroundJobScheduler(background_tasks, dispatcher.run_job)
    )
    return dispatcher
