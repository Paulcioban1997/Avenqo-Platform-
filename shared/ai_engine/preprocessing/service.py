from typing import Any, Protocol, Sequence


class PreprocessingStep(Protocol):
    def transform(self, data: Any) -> Any: ...


class PreprocessingPipeline:
    """Applique des étapes de prétraitement indépendantes des modules."""

    def __init__(self, steps: Sequence[PreprocessingStep] = ()) -> None:
        self._steps = tuple(steps)

    def run(self, data: Any) -> Any:
        for step in self._steps:
            data = step.transform(data)
        return data
