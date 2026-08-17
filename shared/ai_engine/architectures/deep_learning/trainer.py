"""Entraînement des candidats Deep Learning : identique à toutes les familles."""

from shared.ai_engine.core.trainer import Trainer


class DeepLearningTrainer(Trainer):
    """Point d'extension si l'entraînement DL nécessite un jour des callbacks dédiés."""
