"""Stratégie d'exécution Forecasting : branche le catalogue Forecasting sur l'algorithme générique."""

from shared.ai_engine.core.execution_domain import ExecutionDomain
from shared.ai_engine.core.generic_strategy import TrainEvaluateSelectStrategy
from shared.ai_engine.core.optimizer import HyperparameterOptimizer
from shared.ai_engine.evaluation.service import EvaluationService
from shared.ai_engine.families.forecasting.evaluator import ForecastingEvaluator
from shared.ai_engine.families.forecasting.optimizer import ForecastingHyperparameterOptimizer
from shared.ai_engine.families.forecasting.registry import build_forecasting_registry
from shared.ai_engine.families.forecasting.trainer import ForecastingTrainer
from shared.ai_engine.model_selection.service import ModelSelector


class ForecastingStrategy(TrainEvaluateSelectStrategy):
    """Entraîne, évalue et sélectionne le meilleur candidat de prévision de série temporelle."""

    def __init__(
        self,
        evaluator: EvaluationService,
        selector: ModelSelector | None = None,
        optimizer: HyperparameterOptimizer | None = None,
    ) -> None:
        super().__init__(
            domain=ExecutionDomain.FORECASTING,
            candidate_registry=build_forecasting_registry(),
            evaluator=ForecastingEvaluator(evaluator),
            trainer=ForecastingTrainer(),
            optimizer=optimizer or ForecastingHyperparameterOptimizer(),
            selector=selector,
        )
