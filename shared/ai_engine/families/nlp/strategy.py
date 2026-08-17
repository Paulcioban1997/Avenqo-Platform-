"""Stratégie d'exécution NLP : branche le catalogue NLP sur l'algorithme générique."""

from shared.ai_engine.core.execution_domain import ExecutionDomain
from shared.ai_engine.core.generic_strategy import TrainEvaluateSelectStrategy
from shared.ai_engine.core.optimizer import HyperparameterOptimizer
from shared.ai_engine.evaluation.service import EvaluationService
from shared.ai_engine.families.nlp.evaluator import NLPEvaluator
from shared.ai_engine.families.nlp.optimizer import NLPHyperparameterOptimizer
from shared.ai_engine.families.nlp.registry import build_nlp_registry
from shared.ai_engine.families.nlp.trainer import NLPTrainer
from shared.ai_engine.model_selection.service import ModelSelector


class NLPStrategy(TrainEvaluateSelectStrategy):
    """Entraîne, évalue et sélectionne le meilleur candidat NLP."""

    def __init__(
        self,
        evaluator: EvaluationService,
        selector: ModelSelector | None = None,
        optimizer: HyperparameterOptimizer | None = None,
    ) -> None:
        super().__init__(
            domain=ExecutionDomain.NLP,
            candidate_registry=build_nlp_registry(),
            evaluator=NLPEvaluator(evaluator),
            trainer=NLPTrainer(),
            optimizer=optimizer or NLPHyperparameterOptimizer(),
            selector=selector,
        )
