"""Correspondance déterministe avec des dictionnaires de synonymes extensibles."""

import re
from collections.abc import Iterable, Mapping


class SynonymMapper:
    """Associe les noms sources aux noms canoniques avec les alias enregistrés."""

    def __init__(self, synonyms: Mapping[str, set[str]] | None = None) -> None:
        self._synonyms: dict[str, set[str]] = {}
        for canonical, aliases in (synonyms or {}).items():
            self.register(canonical, aliases)

    def register(self, canonical: str, aliases: set[str]) -> None:
        normalized = {self._normalize(value) for value in aliases | {canonical}}
        self._synonyms.setdefault(canonical, set()).update(normalized)

    def map_columns(
        self,
        source_columns: Iterable[str],
        canonical_fields: Iterable[str],
    ) -> dict[str, str]:
        fields = tuple(canonical_fields)
        result: dict[str, str] = {}
        for source in source_columns:
            normalized = self._normalize(source)
            for canonical in fields:
                accepted = self._synonyms.get(canonical, {self._normalize(canonical)})
                if normalized in accepted:
                    result[source] = canonical
                    break
        return result

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.casefold())
