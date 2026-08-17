from typing import Any, Mapping, Protocol

from shared.ai_engine.contracts import DatasetArtifact, EvaluationResult


class MetricsProvider(Protocol):
    def evaluate(self, model: Any, dataset: DatasetArtifact) -> Mapping[str, float]: ...


class EvaluationService:
    """Évalue un candidat avec des métriques injectées propres à la tâche."""

    def __init__(self, metrics: MetricsProvider, primary_metric: str) -> None:
        self._metrics = metrics
        self._primary_metric = primary_metric

    def evaluate(
        self,
        candidate_id: str,
        model: Any,
        dataset: DatasetArtifact,
    ) -> EvaluationResult:
        metrics = dict(self._metrics.evaluate(model, dataset))
        return EvaluationResult(
            candidate_id=candidate_id,
            metrics=metrics,
            score=metrics[self._primary_metric],
        )
