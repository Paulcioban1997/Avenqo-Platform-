from collections.abc import Sequence

from shared.ai_engine.contracts import EvaluationResult


class ModelSelector:
    """Sélectionne le candidat ayant le meilleur score pour une tâche."""

    def select(self, results: Sequence[EvaluationResult]) -> EvaluationResult:
        if not results:
            raise ValueError("At least one evaluation result is required")
        return max(results, key=lambda result: result.score)
