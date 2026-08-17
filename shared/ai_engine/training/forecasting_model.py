"""Modèle de prévision entraîné, sérialisable, consommé par le Prediction Runtime.

Enveloppe unifiée pour des candidats forecasting hétérogènes (naïf, naïf
saisonnier, ARIMA, SARIMA, gradient boosting avec lags) : chacun expose la
même interface `.forecast(horizon)` côté inférence, quel que soit son moteur
interne. Sérialisé directement via `joblib` (pas via
`shared/ai_engine/training/model_saver.py`, qui suppose un `Pipeline` sklearn
avec une étape "preprocessor" nommée — non pertinent ici). Ne dépend
d'aucun composant de `shared.ai_engine.core`/`families`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from shared.ai_engine.training.forecasting_features import build_next_step_features

_STATSMODELS_FAMILIES = ("arima", "sarima")


@dataclass(slots=True)
class ForecastingModel:
    """Représentation unique et sérialisable d'un modèle de prévision entraîné."""

    family: str
    frequency: str
    last_timestamp: pd.Timestamp
    history: list[float]
    seasonal_period: int = 1
    fitted_model: Any = None  # objet statsmodels (arima/sarima) ou pipeline sklearn (gbm)
    lag_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def forecast(self, horizon: int) -> list[dict[str, Any]]:
        """Prévoit ``horizon`` pas dans le futur, business-friendly (horodatage + valeur)."""

        if horizon < 1:
            raise ValueError("horizon must be >= 1")

        confidence_intervals: list[tuple[float, float] | None] = [None] * horizon
        if self.family == "naive":
            values = [float(self.history[-1])] * horizon
        elif self.family == "seasonal_naive":
            values = self._seasonal_naive_forecast(horizon)
        elif self.family in _STATSMODELS_FAMILIES:
            values, confidence_intervals = self._statsmodels_forecast(horizon)
        elif self.family == "gradient_boosting_lags":
            values = self._recursive_lag_forecast(horizon)
        else:
            raise ValueError(f"Famille forecasting inconnue: {self.family}")

        timestamps = pd.date_range(start=self.last_timestamp, periods=horizon + 1, freq=self.frequency)[1:]
        points = []
        for timestamp, value, interval in zip(timestamps, values, confidence_intervals):
            point: dict[str, Any] = {"timestamp": timestamp.isoformat(), "prediction": float(value)}
            if interval is not None:
                point["confidence_interval"] = {"lower": float(interval[0]), "upper": float(interval[1])}
            points.append(point)
        return points

    def _seasonal_naive_forecast(self, horizon: int) -> list[float]:
        history = list(self.history)
        if not history:
            return [0.0] * horizon
        period = max(1, self.seasonal_period)
        values: list[float] = []
        for step in range(horizon):
            index = len(history) - period + (step % period)
            values.append(float(history[index]) if 0 <= index < len(history) else float(history[-1]))
        return values

    def _statsmodels_forecast(self, horizon: int) -> tuple[list[float], list[tuple[float, float] | None]]:
        try:
            result = self.fitted_model.get_forecast(steps=horizon)
            values = [float(value) for value in result.predicted_mean]
            conf_int = result.conf_int()
            intervals = [(float(row[0]), float(row[1])) for row in np.asarray(conf_int)]
            return values, intervals
        except Exception:
            values = [float(value) for value in self.fitted_model.forecast(steps=horizon)]
            return values, [None] * horizon

    def _recursive_lag_forecast(self, horizon: int) -> list[float]:
        history = list(self.history)
        values: list[float] = []
        for _ in range(horizon):
            features = build_next_step_features(history, self.lag_count)
            prediction = float(self.fitted_model.predict(pd.DataFrame([features]))[0])
            values.append(prediction)
            history.append(prediction)
        return values
