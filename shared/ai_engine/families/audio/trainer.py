"""Entraînement des candidats Audio : identique à toutes les familles."""

from shared.ai_engine.core.trainer import Trainer


class AudioTrainer(Trainer):
    """Point d'extension si l'entraînement Audio nécessite un jour un pipeline de featurisation spectrale dédié."""
