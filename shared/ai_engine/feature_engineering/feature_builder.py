from typing import Any, Callable, Mapping

FeatureStrategy = Callable[[Any], Any]


class FeatureBuilder:
    """Sélectionne les stratégies par module et tâche sans colonne codée en dur."""

    def __init__(self) -> None:
        self._strategies: dict[tuple[str, str], FeatureStrategy] = {}

    def register(self, module_code: str, task_code: str, strategy: FeatureStrategy) -> None:
        self._strategies[(module_code, task_code)] = strategy

    def build(self, module_code: str, task_code: str, data: Any) -> Any:
        try:
            strategy = self._strategies[(module_code, task_code)]
        except KeyError as exc:
            raise KeyError(
                f"No feature strategy is registered for {module_code}/{task_code}"
            ) from exc
        return strategy(data)
