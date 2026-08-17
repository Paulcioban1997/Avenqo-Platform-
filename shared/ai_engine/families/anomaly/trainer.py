"""Entraînement des candidats Anomaly Detection : identique à toutes les familles."""

from shared.ai_engine.core.trainer import Trainer


class AnomalyDetectionTrainer(Trainer):
    """Point d'extension si l'entraînement Anomaly Detection nécessite un jour un rééquilibrage dédié."""
