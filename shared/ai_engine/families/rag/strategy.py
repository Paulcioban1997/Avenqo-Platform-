"""Stratégie d'exécution RAG : branche le catalogue RAG sur l'algorithme générique."""

from shared.ai_engine.core.execution_domain import ExecutionDomain
from shared.ai_engine.core.generic_strategy import TrainEvaluateSelectStrategy
from shared.ai_engine.core.optimizer import HyperparameterOptimizer
from shared.ai_engine.evaluation.service import EvaluationService
from shared.ai_engine.families.rag.evaluator import RAGEvaluator
from shared.ai_engine.families.rag.optimizer import RAGHyperparameterOptimizer
from shared.ai_engine.families.rag.registry import build_rag_registry
from shared.ai_engine.families.rag.trainer import RAGTrainer
from shared.ai_engine.model_selection.service import ModelSelector


class RAGStrategy(TrainEvaluateSelectStrategy):
    """Entraîne, évalue et sélectionne le meilleur candidat RAG."""

    def __init__(
        self,
        evaluator: EvaluationService,
        selector: ModelSelector | None = None,
        optimizer: HyperparameterOptimizer | None = None,
    ) -> None:
        super().__init__(
            domain=ExecutionDomain.RAG,
            candidate_registry=build_rag_registry(),
            evaluator=RAGEvaluator(evaluator),
            trainer=RAGTrainer(),
            optimizer=optimizer or RAGHyperparameterOptimizer(),
            selector=selector,
        )
