from typing import Any, Protocol, Sequence


class CleaningRule(Protocol):
    def apply(self, data: Any) -> Any: ...


class Cleaner:
    """Applique dans l'ordre des règles de nettoyage injectées et réutilisables."""

    def __init__(self, rules: Sequence[CleaningRule] = ()) -> None:
        self._rules = tuple(rules)

    def clean(self, data: Any) -> Any:
        for rule in self._rules:
            data = rule.apply(data)
        return data
