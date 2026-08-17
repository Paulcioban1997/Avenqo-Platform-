from typing import Any, Protocol


class ScalerAdapter(Protocol):
    def fit_transform(self, data: Any) -> Any: ...

    def transform(self, data: Any) -> Any: ...


class Scaler:
    """Façade indépendante du framework pour un normaliseur numérique injecté."""

    def __init__(self, adapter: ScalerAdapter) -> None:
        self._adapter = adapter

    def fit_transform(self, data: Any) -> Any:
        return self._adapter.fit_transform(data)

    def transform(self, data: Any) -> Any:
        return self._adapter.transform(data)
