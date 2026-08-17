"""Correspondance explicite validée par l'utilisateur et indépendante de la source."""

from collections.abc import Iterable, Mapping


class ManualMapper:
    """Filtre une correspondance selon les colonnes présentes dans la source."""

    def __init__(self, mapping: Mapping[str, str]) -> None:
        self._mapping = dict(mapping)

    def map_columns(self, source_columns: Iterable[str]) -> dict[str, str]:
        available = set(source_columns)
        return {
            source: canonical
            for source, canonical in self._mapping.items()
            if source in available
        }
