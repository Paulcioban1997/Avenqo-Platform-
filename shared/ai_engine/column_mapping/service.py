"""Base extensible de correspondance des colonnes par alias."""

import re
from collections.abc import Mapping, Sequence

from shared.ai_engine.contracts import DetectedSchema, MappingCandidate


class AliasColumnMapper:
    """Associe les alias normalisés aux champs canoniques."""

    def __init__(self, aliases: Mapping[str, set[str]] | None = None) -> None:
        self._aliases = {
            canonical: {self._normalize(alias) for alias in values | {canonical}}
            for canonical, values in (aliases or {}).items()
        }

    def register_aliases(self, canonical_field: str, aliases: set[str]) -> None:
        normalized = {self._normalize(value) for value in aliases | {canonical_field}}
        self._aliases.setdefault(canonical_field, set()).update(normalized)

    def map_columns(
        self,
        schema: DetectedSchema,
        canonical_fields: Sequence[str],
    ) -> tuple[MappingCandidate, ...]:
        candidates: list[MappingCandidate] = []
        fields = set(canonical_fields)
        for columns in schema.tables.values():
            for column in columns:
                normalized = self._normalize(column.name)
                for canonical in fields:
                    aliases = self._aliases.get(canonical, {self._normalize(canonical)})
                    if normalized in aliases:
                        candidates.append(MappingCandidate(column.name, canonical, 1.0))
        return tuple(candidates)

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.casefold())
