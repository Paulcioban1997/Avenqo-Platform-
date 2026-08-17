"""Entraînement des candidats Machine Learning : identique à toutes les familles."""

from shared.ai_engine.core.trainer import Trainer


class MachineLearningTrainer(Trainer):
    """Point d'extension si l'entraînement ML nécessite un jour une étape spécifique."""
