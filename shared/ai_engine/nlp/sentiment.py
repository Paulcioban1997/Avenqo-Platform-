"""Analyse de sentiment - Tier 1 (Phase 23).

Modèle de base par lexique, sans entraînement par entreprise : contrairement
aux autres capacités (classification/regression/...), aucune donnée
spécifique à une entreprise n'est nécessaire pour produire un premier
résultat exploitable (voir `modules/retailsense/training_specs.py` pour le
statut EXECUTABLE sans `MODULE_TRAINING_SPECS`, documenté explicitement).

Tier 2 (futur, non implémenté ici) : une fois qu'une entreprise dispose de
suffisamment de texte étiqueté, un lexique/modèle propre à cette entreprise
pourra remplacer les constantes ci-dessous SANS changer la signature de
`classify_text`/`aggregate_sentiment` — l'architecture reste extensible sans
réécriture de ses appelants (`business_signal_bridge`, `portfolio_decision_service`).

Jamais de jargon ML exposé : les fonctions ci-dessous ne retournent que des
labels métier ("positive"/"neutral"/"negative") et des mesures agrégées
compréhensibles (taux, tendance, thèmes), jamais un score de modèle brut ou
un nom d'algorithme.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

# Lexique volontairement simple (Tier 1) : liste de mots dont la présence
# indique un sentiment positif ou négatif. Bilingue (anglais/français) car les
# textes clients réels peuvent être dans l'une ou l'autre langue.
_POSITIVE_WORDS: frozenset[str] = frozenset(
    {
        "great", "good", "excellent", "amazing", "love", "loved", "happy",
        "satisfied", "perfect", "awesome", "wonderful", "pleased", "recommend",
        "fast", "friendly", "helpful",
        "excellent", "genial", "parfait", "content", "satisfait", "super",
        "rapide", "agreable", "recommande",
    }
)
_NEGATIVE_WORDS: frozenset[str] = frozenset(
    {
        "bad", "terrible", "awful", "horrible", "hate", "hated", "disappointed",
        "not satisfied", "unsatisfied", "poor", "slow", "rude", "broken",
        "worst", "never", "complaint", "delay", "delayed", "issue", "problem",
        "mauvais", "horrible", "decu", "insatisfait", "lent", "retard",
        "probleme", "casse",
    }
)

_WORD_PATTERN = re.compile(r"[a-zA-Z']+")


@dataclass(frozen=True, slots=True)
class SentimentResult:
    """Résultat métier d'une analyse de texte unique — jamais un score de modèle brut."""

    label: str  # "positive" | "neutral" | "negative"
    score: float  # -1.0 (très négatif) .. 1.0 (très positif)


def classify_text(text: str) -> SentimentResult:
    """Classe un texte en positive/neutral/negative (Tier 1 : lexique simple).

    Compte les mots positifs/négatifs connus et dérive un score entre -1 et 1.
    Volontairement simple et déterministe (aucune dépendance NLP lourde
    requise) : suffisant pour un premier résultat business exploitable.
    """

    if not text or not str(text).strip():
        return SentimentResult(label="neutral", score=0.0)

    lowered = str(text).lower()
    words = set(_WORD_PATTERN.findall(lowered))

    positive_hits = len(words & _POSITIVE_WORDS)
    negative_hits = len(words & _NEGATIVE_WORDS)

    if positive_hits == 0 and negative_hits == 0:
        return SentimentResult(label="neutral", score=0.0)

    score = (positive_hits - negative_hits) / (positive_hits + negative_hits)
    if score > 0.2:
        label = "positive"
    elif score < -0.2:
        label = "negative"
    else:
        label = "neutral"
    return SentimentResult(label=label, score=score)


@dataclass(frozen=True, slots=True)
class SentimentAggregate:
    """Agrégation métier sur un ensemble de textes — jamais un résultat par ligne isolée."""

    total_analyzed: int
    positive_count: int
    neutral_count: int
    negative_count: int
    positive_rate: float
    neutral_rate: float
    negative_rate: float
    previous_negative_rate: float | None
    trend: str  # "improving" | "worsening" | "stable"
    top_negative_entities: tuple[str, ...] = field(default_factory=tuple)
    recent_strong_negative_count: int = 0


# Écart de taux négatif (entre première et seconde moitié chronologique)
# au-delà duquel on considère qu'il y a une tendance réelle, pas du bruit.
_TREND_THRESHOLD = 0.05
# Score en dessous duquel un avis négatif est considéré "fort" (insatisfaction marquée).
_STRONG_NEGATIVE_THRESHOLD = -0.5


def aggregate_sentiment(
    rows: Sequence[Mapping[str, Any]],
    text_column: str,
    entity_column: str | None = None,
    timestamp_column: str | None = None,
) -> SentimentAggregate:
    """Agrège le sentiment sur toutes les lignes disposant d'un texte exploitable.

    Va au-delà du score brut : pourcentages positif/neutre/négatif, tendance
    temporelle si une colonne de date est disponible, thèmes/entités les plus
    négatifs si une colonne produit/service est mappable, et nombre de textes
    récents fortement négatifs (insatisfaction marquée).
    """

    analyzed: list[tuple[Mapping[str, Any], SentimentResult]] = []
    for row in rows:
        text = row.get(text_column)
        if text is None or not str(text).strip():
            continue
        analyzed.append((row, classify_text(str(text))))

    total = len(analyzed)
    if total == 0:
        return SentimentAggregate(
            total_analyzed=0,
            positive_count=0,
            neutral_count=0,
            negative_count=0,
            positive_rate=0.0,
            neutral_rate=0.0,
            negative_rate=0.0,
            previous_negative_rate=None,
            trend="stable",
        )

    positive_count = sum(1 for _, result in analyzed if result.label == "positive")
    negative_count = sum(1 for _, result in analyzed if result.label == "negative")
    neutral_count = total - positive_count - negative_count

    # Tendance temporelle : compare la première moitié chronologique à la
    # seconde (repli simple et lisible, sans dépendre d'un horodatage précis).
    previous_negative_rate: float | None = None
    trend = "stable"
    if timestamp_column is not None:
        sortable = [
            (row.get(timestamp_column), result)
            for row, result in analyzed
            if row.get(timestamp_column) is not None
        ]
        if len(sortable) >= 4:
            sortable.sort(key=lambda item: str(item[0]))
            midpoint = len(sortable) // 2
            first_half = sortable[:midpoint]
            second_half = sortable[midpoint:]
            first_negative_rate = sum(1 for _, r in first_half if r.label == "negative") / len(first_half)
            second_negative_rate = sum(1 for _, r in second_half if r.label == "negative") / len(second_half)
            previous_negative_rate = first_negative_rate
            delta = second_negative_rate - first_negative_rate
            if delta > _TREND_THRESHOLD:
                trend = "worsening"
            elif delta < -_TREND_THRESHOLD:
                trend = "improving"

    # Thèmes/entités les plus négatifs, si une colonne produit/service existe.
    top_negative_entities: tuple[str, ...] = tuple()
    if entity_column is not None:
        negative_counts_by_entity: dict[str, int] = {}
        for row, result in analyzed:
            if result.label != "negative":
                continue
            entity_value = row.get(entity_column)
            if entity_value is None:
                continue
            key = str(entity_value)
            negative_counts_by_entity[key] = negative_counts_by_entity.get(key, 0) + 1
        top_negative_entities = tuple(
            entity
            for entity, _ in sorted(
                negative_counts_by_entity.items(), key=lambda item: item[1], reverse=True
            )[:3]
        )

    recent_strong_negative_count = sum(
        1 for _, result in analyzed if result.score <= _STRONG_NEGATIVE_THRESHOLD
    )

    return SentimentAggregate(
        total_analyzed=total,
        positive_count=positive_count,
        neutral_count=neutral_count,
        negative_count=negative_count,
        positive_rate=positive_count / total,
        neutral_rate=neutral_count / total,
        negative_rate=negative_count / total,
        previous_negative_rate=previous_negative_rate,
        trend=trend,
        top_negative_entities=top_negative_entities,
        recent_strong_negative_count=recent_strong_negative_count,
    )
