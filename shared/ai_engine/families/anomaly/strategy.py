"""Stratégie d'exécution Anomaly Detection : branche le catalogue Anomaly sur l'algorithme générique."""

from shared.ai_engine.core.execution_domain import ExecutionDomain
from shared.ai_engine.core.generic_strategy import TrainEvaluateSelectStrategy
from shared.ai_engine.core.optimizer import HyperparameterOptimizer
from shared.ai_engine.evaluation.service import EvaluationService
from shared.ai_engine.families.anomaly.evaluator import AnomalyDetectionEvaluator
from shared.ai_engine.families.anomaly.optimizer import AnomalyDetectionHyperparameterOptimizer
from shared.ai_engine.families.anomaly.registry import build_anomaly_registry
from shared.ai_engine.families.anomaly.trainer import AnomalyDetectionTrainer
from shared.ai_engine.model_selection.service import ModelSelector


class AnomalyDetectionStrategy(TrainEvaluateSelectStrategy):
    """Entraîne, évalue et sélectionne le meilleur candidat Anomaly Detection."""

    def __init__(
        self,
        evaluator: EvaluationService,
        selector: ModelSelector | None = None,
        optimizer: HyperparameterOptimizer | None = None,
    ) -> None:
        super().__init__(
            domain=ExecutionDomain.ANOMALY_DETECTION,
            candidate_registry=build_anomaly_registry(),
            evaluator=AnomalyDetectionEvaluator(evaluator),
            trainer=AnomalyDetectionTrainer(),
            optimizer=optimizer or AnomalyDetectionHyperparameterOptimizer(),
            selector=selector,
        )
