"""Entraînement des candidats Vision : identique à toutes les familles."""

from shared.ai_engine.core.trainer import Trainer


class VisionTrainer(Trainer):
    """Point d'extension si l'entraînement Vision nécessite un jour un pipeline d'augmentation dédié."""
