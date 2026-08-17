from typing import Any, Callable, Mapping

DriftStrategy = Callable[[Any, Any], Mapping[str, float]]


class DriftDetector:
    """Calcule les scores de dérive avec une stratégie statistique injectée."""

    def __init__(self, strategy: DriftStrategy, threshold: float) -> None:
        self._strategy = strategy
        self._threshold = threshold

    def detect(self, reference: Any, current: Any) -> dict[str, object]:
        scores = dict(self._strategy(reference, current))
        return {
            "detected": any(score >= self._threshold for score in scores.values()),
            "scores": scores,
            "threshold": self._threshold,
        }
