"""Recherche de (p, d, q) par grille + AIC pour ARIMA/SARIMA (statsmodels).

Autorité unique de "recherche d'hyperparamètres" pour les modèles statsmodels de la
famille Forecasting (réutilisée par `arima.py` ET `sarima.py` — zéro duplication de
grille ou de logique de sélection). GridSearchCV/RandomizedSearchCV (scikit-learn) ne
s'appliquent pas directement à `statsmodels.tsa` (API non scikit-learn) : la pratique
standard pour ces modèles — utilisée aussi par des outils de référence comme
`pmdarima.auto_arima` — est de comparer plusieurs ordres candidats via un critère
d'information (AIC) plutôt qu'une validation croisée classique.

Le paramètre de différenciation saisonnière D est volontairement fixé à 0 dans la grille
SARIMA : un test réel a montré qu'une différenciation saisonnière (D=1) sur une série
courte fait diverger l'optimisation du maximum de vraisemblance (prévisions aberrantes de
plusieurs ordres de grandeur). Seuls les termes saisonniers AR/MA (P, Q) sont recherchés.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

import pandas as pd

logger = logging.getLogger(__name__)

NonSeasonalOrder = tuple[int, int, int]
SeasonalOrder = tuple[int, int, int]

_NON_SEASONAL_ORDERS: tuple[NonSeasonalOrder, ...] = (
    (0, 0, 0),
    (1, 0, 0),
    (0, 0, 1),
    (1, 0, 1),
    (1, 1, 0),
    (0, 1, 1),
    (1, 1, 1),
    (2, 1, 1),
    (1, 1, 2),
    (2, 1, 2),
)
_SEASONAL_ORDERS: tuple[SeasonalOrder, ...] = (
    (0, 0, 0),
    (1, 0, 0),
    (0, 0, 1),
    (1, 0, 1),
)


def search_best_arima(
    series: pd.Series, orders: Sequence[NonSeasonalOrder] = _NON_SEASONAL_ORDERS
) -> Any:
    """Ajuste chaque ordre `(p, d, q)` candidat et retourne celui de plus faible AIC."""

    from statsmodels.tsa.arima.model import ARIMA

    best_result = None
    best_aic = float("inf")
    for order in orders:
        try:
            fitted = ARIMA(series, order=order).fit()
        except Exception as exc:  # ordre numériquement instable sur ce dataset : on l'écarte
            logger.debug("ARIMA order=%s a échoué: %s", order, exc)
            continue
        if fitted.aic < best_aic:
            best_aic = fitted.aic
            best_result = fitted

    if best_result is None:
        raise RuntimeError("Aucun ordre ARIMA candidat n'a convergé sur ce dataset.")
    return best_result


def search_best_sarima(
    series: pd.Series,
    seasonal_period: int,
    orders: Sequence[NonSeasonalOrder] = _NON_SEASONAL_ORDERS,
    seasonal_orders: Sequence[SeasonalOrder] = _SEASONAL_ORDERS,
) -> Any:
    """Ajuste chaque combinaison `(p, d, q)` x saisonnier `(P, Q)` et garde le meilleur AIC.

    La composante saisonnière n'est recherchée que si la série contient au moins trois
    cycles complets (`len(series) > 3 * seasonal_period`), sinon un seul ordre non
    saisonnier est essayé — pas assez de données pour estimer une saisonnalité fiable.
    """

    from statsmodels.tsa.statespace.sarimax import SARIMAX

    use_seasonal = seasonal_period > 0 and len(series) > 3 * seasonal_period
    candidate_seasonal_orders = (
        [(p, 0, q, seasonal_period) for p, _, q in seasonal_orders]
        if use_seasonal
        else [(0, 0, 0, 0)]
    )

    best_result = None
    best_aic = float("inf")
    for order in orders:
        for seasonal_order in candidate_seasonal_orders:
            try:
                fitted = SARIMAX(
                    series,
                    order=order,
                    seasonal_order=seasonal_order,
                    enforce_stationarity=False,
                    enforce_invertibility=False,
                ).fit(disp=False, maxiter=200)
            except Exception as exc:  # combinaison numériquement instable : on l'écarte
                logger.debug(
                    "SARIMA order=%s seasonal_order=%s a échoué: %s", order, seasonal_order, exc
                )
                continue
            if fitted.aic < best_aic:
                best_aic = fitted.aic
                best_result = fitted

    if best_result is None:
        raise RuntimeError("Aucune combinaison SARIMA candidate n'a convergé sur ce dataset.")
    return best_result
