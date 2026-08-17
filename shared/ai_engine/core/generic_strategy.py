"""Algorithme unique partagé par toutes les familles : entraîner, évaluer, sélectionner.

Machine Learning, Deep Learning, Forecasting, NLP, Vision, OCR, Graph Neural Networks,
Recommendation, Anomaly Detection, Synthetic Data, LLM, RAG et Audio exécutent tous
exactement cet algorithme. Seuls le domaine, le catalogue de modèles, l'entraîneur,
l'évaluateur et l'optimiseur d'hyperparamètres changent d'une famille à l'autre.
"""

from typing import Sequence

from shared.ai_engine.contracts import DatasetArtifact, TrainingCandidate
from shared.ai_engine.core.evaluator import Evaluator
from shared.ai_engine.core.execution_domain import ExecutionDomain
from shared.ai_engine.core.model_candidate_registry import ModelCandidateRegistry
from shared.ai_engine.core.optimizer import HyperparameterOptimizer, NoOpHyperparameterOptimizer
from shared.ai_engine.core.result import AutoMLResult
from shared.ai_engine.core.trainer import Trainer
from shared.ai_engine.model_selection.service import ModelSelector


class TrainEvaluateSelectStrategy:
    """Implémentation générique de `ExecutionStrategy`, réutilisée par chaque famille."""

    def __init__(
        self,
        domain: ExecutionDomain,
        candidate_registry: ModelCandidateRegistry,
        evaluator: Evaluator,
        trainer: Trainer | None = None,
        optimizer: HyperparameterOptimizer | None = None,
        selector: ModelSelector | None = None,
    ) -> None:
        self.domain = domain
        self._candidate_registry = candidate_registry
        self._evaluator = evaluator
        self._trainer = trainer or Trainer()
        self._optimizer = optimizer or NoOpHyperparameterOptimizer()
        self._selector = selector or ModelSelector()

    def execute(
        self,
        dataset: DatasetArtifact,
        candidates: Sequence[TrainingCandidate] | None = None,
    ) -> AutoMLResult:
        pool = candidates if candidates is not None else self._candidate_registry.build_all()
        trained: dict[str, object] = {}
        evaluations = []
        for candidate in pool:
            tuned = self._optimizer.optimize(candidate, dataset)
            model = self._trainer.train(tuned, dataset)
            trained[tuned.candidate_id] = model
            evaluations.append(self._evaluator.evaluate(tuned.candidate_id, model, dataset))
        selected = self._selector.select(evaluations)
        return AutoMLResult(
            candidate_id=selected.candidate_id,
            model=trained[selected.candidate_id],
            evaluation=selected,
        )
