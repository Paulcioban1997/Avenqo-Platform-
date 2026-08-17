"""Seuils de sévérité — source unique des constantes de décision du drift.

Isolés dans un module dédié : ajuster la sensibilité du système ne nécessite
de modifier qu'un seul endroit, jamais la logique de calcul elle-même.
"""

from shared.ai_engine.drift.types import DriftSeverity

# PSI : seuils universellement admis dans les plateformes Enterprise
# (SageMaker Model Monitor, Azure ML, DataRobot...).
PSI_WARNING = 0.1
PSI_CRITICAL = 0.25

# Kolmogorov-Smirnov / Chi carré : significativité statistique classique (95%).
P_VALUE_WARNING = 0.05
P_VALUE_CRITICAL = 0.01

# Jensen-Shannon : bornée [0, 1] ; seuils empiriques usuels en monitoring de scores.
JS_WARNING = 0.1
JS_CRITICAL = 0.2

# Concept drift : baisse relative de la métrique de performance principale.
METRIC_DEGRADATION_WARNING = 0.05
METRIC_DEGRADATION_CRITICAL = 0.15


def classify_psi(value: float) -> DriftSeverity:
    if value >= PSI_CRITICAL:
        return DriftSeverity.CRITICAL
    if value >= PSI_WARNING:
        return DriftSeverity.WARNING
    return DriftSeverity.NONE


def classify_p_value(p_value: float) -> DriftSeverity:
    """Une p_value FAIBLE indique un drift : l'échelle est donc inversée."""

    if p_value <= P_VALUE_CRITICAL:
        return DriftSeverity.CRITICAL
    if p_value <= P_VALUE_WARNING:
        return DriftSeverity.WARNING
    return DriftSeverity.NONE


def classify_js(value: float) -> DriftSeverity:
    if value >= JS_CRITICAL:
        return DriftSeverity.CRITICAL
    if value >= JS_WARNING:
        return DriftSeverity.WARNING
    return DriftSeverity.NONE


def classify_metric_degradation(ratio: float) -> DriftSeverity:
    """`ratio` = (référence - actuel) / |référence| ; positif = dégradation."""

    if ratio >= METRIC_DEGRADATION_CRITICAL:
        return DriftSeverity.CRITICAL
    if ratio >= METRIC_DEGRADATION_WARNING:
        return DriftSeverity.WARNING
    return DriftSeverity.NONE
