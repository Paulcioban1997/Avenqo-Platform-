from typing import Any, Callable, Mapping

Metric = Callable[[Any, Any], float]


class Evaluator:
    """Calcule les métriques injectées sans imposer de tâche ni de framework ML."""

    def __init__(self, metrics: Mapping[str, Metric]) -> None:
        self._metrics = dict(metrics)

    def evaluate(self, expected: Any, predicted: Any) -> dict[str, float]:
        return {
            name: float(metric(expected, predicted))
            for name, metric in self._metrics.items()
        }
