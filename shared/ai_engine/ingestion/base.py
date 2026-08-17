"""Contrats d'ingestion indépendants de la source."""

from typing import Any, Callable, Generic, Mapping, TypeVar

LoadedData = TypeVar("LoadedData")
Reader = Callable[..., LoadedData]


class DelegatingLoader(Generic[LoadedData]):
    """Délègue le chargement à un lecteur technologique injecté."""

    def __init__(self, reader: Reader[LoadedData]) -> None:
        self._reader = reader

    def load(self, location: str, **options: Any) -> LoadedData:
        return self._reader(location, **options)
