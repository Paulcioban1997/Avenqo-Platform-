"""Stratégie d'exécution Recommendation : branche le catalogue Recommendation sur l'algorithme générique."""

from shared.ai_engine.core.execution_domain import ExecutionDomain
from shared.ai_engine.core.generic_strategy import TrainEvaluateSelectStrategy
from shared.ai_engine.core.optimizer import HyperparameterOptimizer
from shared.ai_engine.evaluation.service import EvaluationService
from shared.ai_engine.families.recommendation.evaluator import RecommendationEvaluator
from shared.ai_engine.families.recommendation.optimizer import (
    RecommendationHyperparameterOptimizer,
)
from shared.ai_engine.families.recommendation.registry import build_recommendation_registry
from shared.ai_engine.families.recommendation.trainer import RecommendationTrainer
from shared.ai_engine.model_selection.service import ModelSelector


class RecommendationStrategy(TrainEvaluateSelectStrategy):
    """Entraîne, évalue et sélectionne le meilleur candidat Recommendation."""

    def __init__(
        self,
        evaluator: EvaluationService,
        selector: ModelSelector | None = None,
        optimizer: HyperparameterOptimizer | None = None,
    ) -> None:
        super().__init__(
            domain=ExecutionDomain.RECOMMENDATION,
            candidate_registry=build_recommendation_registry(),
            evaluator=RecommendationEvaluator(evaluator),
            trainer=RecommendationTrainer(),
            optimizer=optimizer or RecommendationHyperparameterOptimizer(),
            selector=selector,
        )
