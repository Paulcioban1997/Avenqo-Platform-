"""Stratégie d'exécution Audio : branche le catalogue Audio sur l'algorithme générique."""

from shared.ai_engine.core.execution_domain import ExecutionDomain
from shared.ai_engine.core.generic_strategy import TrainEvaluateSelectStrategy
from shared.ai_engine.core.optimizer import HyperparameterOptimizer
from shared.ai_engine.evaluation.service import EvaluationService
from shared.ai_engine.families.audio.evaluator import AudioEvaluator
from shared.ai_engine.families.audio.optimizer import AudioHyperparameterOptimizer
from shared.ai_engine.families.audio.registry import build_audio_registry
from shared.ai_engine.families.audio.trainer import AudioTrainer
from shared.ai_engine.model_selection.service import ModelSelector


class AudioStrategy(TrainEvaluateSelectStrategy):
    """Entraîne, évalue et sélectionne le meilleur candidat Audio."""

    def __init__(
        self,
        evaluator: EvaluationService,
        selector: ModelSelector | None = None,
        optimizer: HyperparameterOptimizer | None = None,
    ) -> None:
        super().__init__(
            domain=ExecutionDomain.AUDIO,
            candidate_registry=build_audio_registry(),
            evaluator=AudioEvaluator(evaluator),
            trainer=AudioTrainer(),
            optimizer=optimizer or AudioHyperparameterOptimizer(),
            selector=selector,
        )
