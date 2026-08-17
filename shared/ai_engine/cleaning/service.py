from typing import Any, Protocol, Sequence


class CleaningStep(Protocol):
    def apply(self, data: Any) -> Any: ...


class CleaningPipeline:
    """Applique les étapes de nettoyage injectées dans un ordre déterministe."""

    def __init__(self, steps: Sequence[CleaningStep] = ()) -> None:
        self._steps = tuple(steps)

    def run(self, data: Any) -> Any:
        for step in self._steps:
            data = step.apply(data)
        return data
