"""Implémentations statistiques pures — source unique de chaque formule.

Chaque fonction est indépendante de toute notion de "feature"/"prediction"/
"target" : `data_drift.py`/`prediction_drift.py` décident QUAND les appeler,
ce module décide seulement COMMENT les calculer correctement.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.spatial.distance import jensenshannon
from scipy.stats import chisquare, entropy, ks_2samp, wasserstein_distance as _wasserstein_distance

_EPSILON = 1e-6


def kolmogorov_smirnov(reference: np.ndarray, current: np.ndarray) -> tuple[float, float]:
    """Test de Kolmogorov-Smirnov à deux échantillons (variables continues).

    Retourne `(statistique, p_value)`. Une p_value faible indique que les deux
    échantillons proviennent probablement de distributions différentes.
    """

    result = ks_2samp(reference, current)
    return float(result.statistic), float(result.pvalue)


def wasserstein_distance(reference: np.ndarray, current: np.ndarray) -> float:
    """Distance "Earth Mover's" — magnitude du déplacement de la distribution.

    Contrairement au KS/PSI, insensible au choix des bornes/intervalles :
    complément utile pour quantifier l'AMPLEUR d'un drift déjà détecté.
    """

    return float(_wasserstein_distance(reference, current))


def population_stability_index(
    reference: np.ndarray,
    current: np.ndarray,
    bins: int = 10,
) -> float:
    """PSI pour une variable continue, par quantiles de la référence.

    Métrique la plus répandue dans les plateformes Enterprise (SageMaker
    Model Monitor, Azure ML, DataRobot...) pour surveiller le data drift :
    seuils universellement admis (< 0.1 stable, 0.1-0.25 modéré, > 0.25 fort).
    """

    quantile_edges = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))
    if quantile_edges.size < 3:
        # Variable quasi constante : les quantiles ne peuvent pas être découpés.
        return 0.0
    edges = quantile_edges.copy()
    edges[0], edges[-1] = -np.inf, np.inf
    reference_proportions = _bucket_proportions(reference, edges)
    current_proportions = _bucket_proportions(current, edges)
    return _psi_from_proportions(reference_proportions, current_proportions)


def population_stability_index_categorical(
    reference_proportions: np.ndarray,
    current_proportions: np.ndarray,
) -> float:
    """PSI pour une variable catégorielle, à partir de vecteurs de proportions
    déjà alignés sur les mêmes catégories (voir `_category_proportions`)."""

    return _psi_from_proportions(reference_proportions, current_proportions)


def chi_square_test(
    reference_counts: np.ndarray,
    current_counts: np.ndarray,
) -> tuple[float, float]:
    """Test du Chi carré d'indépendance entre deux distributions catégorielles.

    `current_counts` est remis à l'échelle du total de `reference_counts` afin
    que `scipy.stats.chisquare` compare des proportions, pas des volumes bruts
    (le nombre de lignes observées après déploiement diffère naturellement de
    celui de l'entraînement).
    """

    reference_total = reference_counts.sum()
    current_total = current_counts.sum()
    if reference_total == 0 or current_total == 0:
        return 0.0, 1.0
    expected = reference_counts / reference_total * current_total
    expected = np.where(expected == 0, _EPSILON, expected)
    result = chisquare(f_obs=current_counts, f_exp=expected)
    return float(result.statistic), float(result.pvalue)


def jensen_shannon_distance(
    reference_proportions: np.ndarray,
    current_proportions: np.ndarray,
) -> float:
    """Distance de Jensen-Shannon — bornée [0, 1], symétrique.

    Préférée à la divergence KL brute comme métrique PRINCIPALE quand on
    compare deux distributions (prédictions, scores) : plus robuste, ne
    diverge jamais vers l'infini même quand une catégorie n'apparaît que
    d'un seul côté.
    """

    return float(jensenshannon(reference_proportions, current_proportions, base=2))


def kl_divergence(reference_proportions: np.ndarray, current_proportions: np.ndarray) -> float:
    """Divergence de Kullback-Leibler — métrique complémentaire, asymétrique.

    Volontairement utilisée seulement en complément (jamais comme seule
    décision de drift) : non bornée et non symétrique, donc moins robuste que
    PSI/JS en alerting automatique, mais standard pour quantifier finement un
    changement de distribution de scores/probabilités.
    """

    return float(entropy(current_proportions, reference_proportions))


def category_proportions(
    reference: "np.ndarray | list",
    current: "np.ndarray | list",
) -> tuple[np.ndarray, np.ndarray]:
    """Aligne deux échantillons catégoriels sur l'union de leurs catégories.

    Lissage epsilon appliqué pour que chaque proportion reste strictement
    positive (requis par le Chi carré/PSI/JS/KL, qui divisent ou prennent un
    logarithme).
    """

    reference_counts = pd.Series(reference).value_counts()
    current_counts = pd.Series(current).value_counts()
    categories = sorted(set(reference_counts.index) | set(current_counts.index), key=str)
    reference_aligned = np.array([reference_counts.get(category, 0) for category in categories], dtype=float)
    current_aligned = np.array([current_counts.get(category, 0) for category in categories], dtype=float)
    reference_proportions = (reference_aligned + _EPSILON) / (reference_aligned.sum() + _EPSILON * len(categories))
    current_proportions = (current_aligned + _EPSILON) / (current_aligned.sum() + _EPSILON * len(categories))
    return reference_proportions, current_proportions


def _bucket_proportions(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    counts, _ = np.histogram(values, bins=edges)
    return (counts + _EPSILON) / (counts.sum() + _EPSILON * len(counts))


def _psi_from_proportions(reference_proportions: np.ndarray, current_proportions: np.ndarray) -> float:
    return float(
        np.sum((current_proportions - reference_proportions) * np.log(current_proportions / reference_proportions))
    )
