"""Comparaison de versions — délègue entièrement à `retraining.service.compare_models`.

Aucune métrique, aucun rapport de drift, aucune explication XAI n'est
recalculé ici : `VersionRecord.metrics`/`drift_severity` ont déjà été
capturés une seule fois à l'entraînement (voir `service.record_version`).
Ce module ajoute uniquement l'identification des deux versions comparées
autour du moteur de comparaison déjà validé en Phase 8 — source unique de
vérité pour "qu'est-ce qu'un modèle meilleur qu'un autre".
"""

from __future__ import annotations

from shared.ai_engine.retraining.service import compare_models, should_activate
from shared.ai_engine.retraining.types import RetrainingRulesConfig
from shared.ai_engine.versioning.types import VersionComparisonResult, VersionRecord


def compare_versions(
    version_a: VersionRecord,
    version_b: VersionRecord,
    config: RetrainingRulesConfig | None = None,
) -> VersionComparisonResult:
    """Compare `version_a` (référence) à `version_b` (candidate) — ne lève jamais.

    `version_b` est conventionnellement la version la plus récente des deux,
    mais l'appelant peut comparer deux versions arbitraires (ex. rollback :
    "la version 12 était-elle réellement meilleure que la version 8 ?").
    """

    comparison = compare_models(
        version_b.family,
        version_a.metrics,
        version_b.metrics,
        version_b.drift_severity,
        config,
    )
    return VersionComparisonResult(
        version_a=version_a.version,
        version_b=version_b.version,
        metric_name=comparison.metric_name,
        higher_is_better=comparison.higher_is_better,
        value_a=comparison.previous_value,
        value_b=comparison.candidate_value,
        delta=comparison.delta,
        b_is_better=should_activate(comparison),
        blocked_by_drift=comparison.blocked_by_drift,
    )
