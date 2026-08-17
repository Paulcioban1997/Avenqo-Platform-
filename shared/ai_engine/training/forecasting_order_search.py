"""Recherche d'ordres ARIMA/SARIMA par AIC — implémentation propre à la couche active.

Inspirée dans son principe (grille d'ordres + sélection par AIC) de
`shared/ai_engine/families/forecasting/models/_order_search.py` (moteur
orphelin), mais réécrite indépendamment ici : ce fichier n'importe RIEN de
`shared.ai_engine.core`/`shared.ai_engine.families`, afin de garantir zéro
arête de dépendance depuis le runtime actif vers l'arbre orphelin (voir
`test_no_second_ai_engine_is_used_by_active_training_path`). La grille est
volontairement plus modeste que celle du moteur orphelin : elle est
recalculée à CHAQUE fenêtre de backtesting (plusieurs fois par entraînement),
donc doit rester rapide sur de petites séries.
"""

from __future__ import annotations

import warnings

import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.statespace.sarimax import SARIMAX

_NON_SEASONAL_ORDERS: tuple[tuple[int, int, int], ...] = (
    (0, 0, 0),
    (1, 0, 0),
    (0, 1, 1),
    (1, 1, 0),
    (1, 1, 1),
)
_SEASONAL_ORDERS: tuple[tuple[int, int, int], ...] = (
    (0, 0, 0),
    (1, 0, 0),
    (0, 0, 1),
)


def search_best_arima(series: pd.Series):
    """Sélectionne l'ordre (p, d, q) minimisant l'AIC sur une petite grille."""

    best_result = None
    best_aic = float("inf")
    for order in _NON_SEASONAL_ORDERS:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fitted = ARIMA(series, order=order).fit()
        except Exception:
            continue
        if fitted.aic < best_aic:
            best_aic = fitted.aic
            best_result = fitted
    if best_result is None:
        raise ValueError("Aucun modèle ARIMA n'a pu être ajusté sur cette série.")
    return best_result


def search_best_sarima(series: pd.Series, *, seasonal_period: int):
    """Sélectionne (p, d, q)(P, D, Q, s) minimisant l'AIC sur une petite grille.

    La composante saisonnière n'est recherchée que si la série contient au
    moins 3 cycles complets (sinon SARIMAX devient numériquement instable) :
    dans ce cas, cette fonction se replie sur une recherche ARIMA classique.
    """

    if seasonal_period < 2 or len(series) < 3 * seasonal_period:
        return search_best_arima(series)

    best_result = None
    best_aic = float("inf")
    for order in _NON_SEASONAL_ORDERS:
        for seasonal_order in _SEASONAL_ORDERS:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    fitted = SARIMAX(
                        series,
                        order=order,
                        seasonal_order=(*seasonal_order, seasonal_period),
                        enforce_stationarity=False,
                        enforce_invertibility=False,
                    ).fit(disp=False, maxiter=100)
            except Exception:
                continue
            if fitted.aic < best_aic:
                best_aic = fitted.aic
                best_result = fitted
    if best_result is None:
        return search_best_arima(series)
    return best_result
