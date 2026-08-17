"""Étape d'évaluation commune, réutilisée à l'identique par chaque famille IA."""

from shared.ai_engine.contracts import DatasetArtifact, EvaluationResult
from shared.ai_engine.evaluation.service import EvaluationService


class Evaluator:
    """Délègue l'évaluation au service d'évaluation partagé de l'AI Engine."""

    def __init__(self, service: EvaluationService) -> None:
        self._service = service

    def evaluate(
        self,
        candidate_id: str,
        model: object,
        dataset: DatasetArtifact,
    ) -> EvaluationResult:
        return self._service.evaluate(candidate_id, model, dataset)
