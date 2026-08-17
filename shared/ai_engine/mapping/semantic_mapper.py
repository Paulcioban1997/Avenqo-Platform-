"""Correspondance sémantique avec un calculateur de similarité injecté."""

from collections.abc import Callable, Iterable

SimilarityScorer = Callable[[str, str], float]


class SemanticMapper:
    """Sélectionne les champs canoniques avec un calculateur remplaçable."""

    def __init__(self, scorer: SimilarityScorer) -> None:
        self._scorer = scorer

    def map_columns(
        self,
        source_columns: Iterable[str],
        canonical_fields: Iterable[str],
        threshold: float = 0.8,
    ) -> dict[str, str]:
        fields = tuple(canonical_fields)
        result: dict[str, str] = {}
        for source in source_columns:
            scores = [(target, self._scorer(source, target)) for target in fields]
            if not scores:
                continue
            target, score = max(scores, key=lambda item: item[1])
            if score >= threshold:
                result[source] = target
        return result
