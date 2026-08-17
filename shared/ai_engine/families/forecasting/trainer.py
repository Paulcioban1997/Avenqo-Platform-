"""Entraînement des candidats Forecasting : identique à toutes les familles."""

from shared.ai_engine.core.trainer import Trainer


class ForecastingTrainer(Trainer):
    """Point d'extension si l'entraînement Forecasting nécessite un jour un découpage temporel dédié."""
