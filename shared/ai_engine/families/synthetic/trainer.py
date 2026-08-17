"""Entraînement des candidats Synthetic Data : identique à toutes les familles."""

from shared.ai_engine.core.trainer import Trainer


class SyntheticDataTrainer(Trainer):
    """Point d'extension si l'entraînement Synthetic Data nécessite un jour des contraintes de confidentialité dédiées."""
