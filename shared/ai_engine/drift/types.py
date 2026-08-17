"""Types partagés de la couche Drift Detection (usage interne uniquement).

Comme la couche d'explicabilité (Phase 6), ces objets ne sont jamais exposés
à l'utilisateur final : consommés uniquement par le backend, les API
internes/admin et les futures phases (Auto Retraining, Monitoring, Alerting).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Literal, Mapping

import numpy as np
import pandas as pd


class DriftSeverity(IntEnum):
    """Sévérité croissante — `IntEnum` pour permettre `max()` directement."""

    NONE = 0
    WARNING = 1
    CRITICAL = 2


def max_severity(*severities: DriftSeverity) -> DriftSeverity:
    """Agrège plusieurs sévérités : la plus grave l'emporte toujours."""

    return max(severities) if severities else DriftSeverity.NONE


@dataclass(frozen=True, slots=True)
class FeatureDriftResult:
    """Résultat du/des test(s) statistique(s) appliqués à une variable."""

    feature: str
    tests: Mapping[str, float]
    severity: DriftSeverity
    drifted: bool


@dataclass(frozen=True, slots=True)
class DataDriftReport:
    """Agrège le drift de toutes les variables d'entrée du modèle."""

    features: tuple[FeatureDriftResult, ...]
    drifted_feature_ratio: float
    overall_severity: DriftSeverity


@dataclass(frozen=True, slots=True)
class PredictionDriftReport:
    """Changement de distribution des prédictions du modèle."""

    tests: Mapping[str, float]
    severity: DriftSeverity
    drifted: bool


@dataclass(frozen=True, slots=True)
class ConceptDriftReport:
    """Baisse des performances réelles du modèle (nécessite des vérités terrain)."""

    available: bool
    metric_name: str | None
    reference_value: float | None
    current_value: float | None
    degradation_ratio: float | None
    severity: DriftSeverity
    drifted: bool


@dataclass(frozen=True, slots=True)
class DriftReport:
    """Rapport complet : data drift + prediction drift + target drift + concept drift."""

    model_name: str
    task_type: Literal["classification", "regression"]
    data_drift: DataDriftReport
    prediction_drift: PredictionDriftReport | None
    target_drift: FeatureDriftResult | None
    concept_drift: ConceptDriftReport
    overall_severity: DriftSeverity
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True, slots=True)
class ReferenceBaseline:
    """Baseline statistique capturée à l'entraînement, utilisée comme référence.

    Un échantillon borné (jamais le jeu de données complet) des variables, des
    prédictions et de la cible du split de test — suffisant pour rejouer des
    tests statistiques à deux échantillons (KS, PSI, Wasserstein...) plus tard,
    sans stocker indéfiniment des données brutes volumineuses.
    """

    model_name: str
    task_type: Literal["classification", "regression"]
    features: pd.DataFrame
    predictions: np.ndarray | None
    target: pd.Series | None
    metrics: Mapping[str, float]
    numerical_columns: tuple[str, ...]
    categorical_columns: tuple[str, ...]
    captured_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
