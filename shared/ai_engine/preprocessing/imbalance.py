"""Détection du déséquilibre de classes et choix automatique du ré-échantillonneur.

Autorité unique pour la classification (ML tabulaire et réseaux denses tabulaires) :
décide s'il faut ré-échantillonner et lequel de SMOTE/SMOTENC/SMOTEN utiliser, sans
dupliquer cette logique ailleurs. Utilisé uniquement par `training/train_classifier.py`
et `training/train_neural_network.py` (task_type="classification").

Jamais appelé pour la régression, le clustering, les séries temporelles/forecasting,
ni les modèles non supervisés/génératifs (AutoEncoder, GAN/CTGAN/TVAE, VAE, GNN/
GraphSAGE/GAT, NLP) : ces familles n'ont pas de notion de classes déséquilibrées ou
n'ont simplement pas de cible de classification, donc n'importent pas ce module.
"""

from dataclasses import dataclass
from typing import Any

import pandas as pd

from shared.ai_engine.preprocessing.tabular import FeatureColumns


@dataclass(frozen=True, slots=True)
class ImbalanceReport:
    """Résultat de l'analyse de déséquilibre d'une cible de classification."""

    ratio: float
    minority_class_count: int
    is_imbalanced: bool


def analyze_class_balance(target: pd.Series, threshold: float = 1.5) -> ImbalanceReport:
    """Ratio = effectif de la classe majoritaire / effectif de la classe minoritaire.

    Déséquilibré si ce ratio dépasse `threshold` (1.5 par défaut : la classe
    majoritaire a au moins 50% d'échantillons de plus que la minoritaire).
    """

    counts = pd.Series(target).value_counts()
    if len(counts) < 2:
        return ImbalanceReport(
            ratio=1.0,
            minority_class_count=int(counts.min()) if len(counts) else 0,
            is_imbalanced=False,
        )
    ratio = float(counts.max() / counts.min())
    return ImbalanceReport(
        ratio=ratio,
        minority_class_count=int(counts.min()),
        is_imbalanced=ratio > threshold,
    )


def build_resampler(
    columns: FeatureColumns,
    report: ImbalanceReport,
    random_seed: int = 42,
    cv_folds: int = 1,
) -> Any | None:
    """Choisit SMOTE (numérique pur), SMOTENC (mixte) ou SMOTEN (catégoriel pur).

    `cv_folds` (>1 si le ré-échantillonnage sera exécuté à l'intérieur d'une
    cross-validation à `cv_folds` plis) réduit prudemment `k_neighbors` : chaque
    pli d'entraînement ne conserve statistiquement qu'une fraction
    `(cv_folds-1)/cv_folds` des échantillons minoritaires, donc utiliser le
    `k_neighbors` calculé sur l'effectif total ferait planter SMOTE sur des plis
    plus petits.

    Retourne `None` si aucun ré-échantillonnage n'est pertinent : pas de
    déséquilibre détecté, ou classe minoritaire (une fois réduite par la CV) trop
    petite pour calculer des voisins (moins de 2 échantillons).
    """

    if not report.is_imbalanced or report.minority_class_count < 2:
        return None

    from imblearn.over_sampling import SMOTE, SMOTEN, SMOTENC

    usable_minority = report.minority_class_count
    if cv_folds > 1:
        usable_minority = max(1, (report.minority_class_count * (cv_folds - 1)) // cv_folds)
    if usable_minority < 2:
        return None

    k_neighbors = max(1, min(5, usable_minority - 1))
    if columns.categorical and columns.numerical:
        categorical_indices = list(
            range(len(columns.numerical), len(columns.numerical) + len(columns.categorical))
        )
        return SMOTENC(
            categorical_features=categorical_indices,
            k_neighbors=k_neighbors,
            random_state=random_seed,
        )
    if columns.categorical and not columns.numerical:
        return SMOTEN(k_neighbors=k_neighbors, random_state=random_seed)
    return SMOTE(k_neighbors=k_neighbors, random_state=random_seed)
