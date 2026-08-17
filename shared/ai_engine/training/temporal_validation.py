"""Découpage temporel strict (backtesting) pour le forecasting.

Jamais de mélange aléatoire (``train_test_split``) : une fenêtre
d'entraînement en expansion, des fenêtres de validation de taille fixe
(``horizon``), puis un test final strictement réservé, jamais utilisé pour
sélectionner un candidat (voir `train_forecaster.py`).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BacktestPlan:
    """Positions (indices) sur l'historique, jamais les valeurs elles-mêmes."""

    windows: tuple[tuple[int, int], ...]  # (train_end_exclusive, val_end_exclusive)
    final_test_start: int
    final_test_end: int


def build_backtest_plan(
    n_observations: int,
    horizon: int,
    *,
    minimum_train_size: int,
    max_windows: int = 3,
) -> BacktestPlan:
    """Construit un plan de backtesting par fenêtre d'expansion.

    Le test final (les ``horizon`` dernières observations) est réservé AVANT
    toute génération de fenêtre de backtesting : il n'apparaît jamais dans
    ``windows``.
    """

    if horizon < 1:
        raise ValueError("horizon must be >= 1")

    final_test_end = n_observations
    final_test_start = max(0, n_observations - horizon)
    history_length = final_test_start

    windows: list[tuple[int, int]] = []
    if history_length >= minimum_train_size + horizon:
        available_for_backtest = history_length - minimum_train_size
        possible_windows = max(1, available_for_backtest // horizon)
        window_count = min(max_windows, possible_windows)
        for index in range(window_count):
            train_end = minimum_train_size + index * horizon
            val_end = min(train_end + horizon, history_length)
            if val_end <= train_end:
                break
            windows.append((train_end, val_end))

    return BacktestPlan(
        windows=tuple(windows),
        final_test_start=final_test_start,
        final_test_end=final_test_end,
    )
