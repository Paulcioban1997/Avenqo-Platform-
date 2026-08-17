from typing import Any, Protocol


class EncoderAdapter(Protocol):
    def fit_transform(self, data: Any) -> Any: ...

    def transform(self, data: Any) -> Any: ...


class Encoder:
    """Façade indépendante du framework pour un encodeur catégoriel injecté."""

    def __init__(self, adapter: EncoderAdapter) -> None:
        self._adapter = adapter

    def fit_transform(self, data: Any) -> Any:
        return self._adapter.fit_transform(data)

    def transform(self, data: Any) -> Any:
        return self._adapter.transform(data)
