"""Stratégie d'exécution LLM : branche le catalogue LLM sur l'algorithme générique."""

from shared.ai_engine.core.execution_domain import ExecutionDomain
from shared.ai_engine.core.generic_strategy import TrainEvaluateSelectStrategy
from shared.ai_engine.core.optimizer import HyperparameterOptimizer
from shared.ai_engine.evaluation.service import EvaluationService
from shared.ai_engine.families.llm.evaluator import LLMEvaluator
from shared.ai_engine.families.llm.optimizer import LLMHyperparameterOptimizer
from shared.ai_engine.families.llm.registry import build_llm_registry
from shared.ai_engine.families.llm.trainer import LLMTrainer
from shared.ai_engine.model_selection.service import ModelSelector


class LLMStrategy(TrainEvaluateSelectStrategy):
    """Entraîne, évalue et sélectionne le meilleur candidat LLM."""

    def __init__(
        self,
        evaluator: EvaluationService,
        selector: ModelSelector | None = None,
        optimizer: HyperparameterOptimizer | None = None,
    ) -> None:
        super().__init__(
            domain=ExecutionDomain.LLM,
            candidate_registry=build_llm_registry(),
            evaluator=LLMEvaluator(evaluator),
            trainer=LLMTrainer(),
            optimizer=optimizer or LLMHyperparameterOptimizer(),
            selector=selector,
        )
