"""Concept Drift — baisse des performances réelles du modèle.

Ne recalcule AUCUNE métrique : réutilise celles déjà produites par
`evaluation/sklearn_metrics.py`/`evaluation/neural_metrics.py` (passées en
paramètre), pour rester l'unique source de vérité des métriques de
performance. Ce module ne fait que COMPARER une valeur de référence à une
valeur actuelle et classifier la sévérité de l'écart.
"""

from __future__ import annotations

from typing import Literal, Mapping

from shared.ai_engine.drift.thresholds import classify_metric_degradation
from shared.ai_engine.drift.types import ConceptDriftReport, DriftSeverity

# Une seule métrique "primaire" par type de tâche : la même que celle utilisée
# pour la sélection du meilleur modèle pendant l'entraînement (voir
# `architectures/machine_learning/optimizer.py`), pour rester cohérent.
_PRIMARY_METRIC: Mapping[str, str] = {"classification": "accuracy", "regression": "r2"}


def detect_concept_drift(
    reference_metrics: Mapping[str, float],
    current_metrics: Mapping[str, float] | None,
    task_type: Literal["classification", "regression"],
) -> ConceptDriftReport:
    """Compare la performance réelle actuelle à celle mesurée à l'entraînement.

    `current_metrics` n'est disponible que lorsque des vérités terrain
    récentes existent (label de classe/valeur réelle connue) — sinon
    `available=False` : le concept drift reste alors simplement "non mesurable
    pour l'instant", jamais faussement à `False`/"pas de drift".
    """

    metric_name = _PRIMARY_METRIC[task_type]
    reference_value = reference_metrics.get(metric_name)
    current_value = (current_metrics or {}).get(metric_name)
    if reference_value is None or current_value is None:
        return ConceptDriftReport(
            available=False,
            metric_name=metric_name,
            reference_value=reference_value,
            current_value=current_value,
            degradation_ratio=None,
            severity=DriftSeverity.NONE,
            drifted=False,
        )

    degradation_ratio = (
        (reference_value - current_value) / abs(reference_value) if reference_value else 0.0
    )
    severity = classify_metric_degradation(degradation_ratio)
    return ConceptDriftReport(
        available=True,
        metric_name=metric_name,
        reference_value=reference_value,
        current_value=current_value,
        degradation_ratio=degradation_ratio,
        severity=severity,
        drifted=severity != DriftSeverity.NONE,
    )
