from typing import Any, Callable

SplitStrategy = Callable[..., tuple[Any, ...]]


class Splitter:
    """Délègue la séparation du jeu de données à une stratégie injectée."""

    def __init__(self, strategy: SplitStrategy) -> None:
        self._strategy = strategy

    def split(self, features: Any, target: Any = None, **options: Any) -> tuple[Any, ...]:
        return self._strategy(features, target, **options)
