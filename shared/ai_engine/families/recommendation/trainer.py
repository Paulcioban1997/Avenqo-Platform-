"""Entraînement des candidats Recommendation : identique à toutes les familles."""

from shared.ai_engine.core.trainer import Trainer


class RecommendationTrainer(Trainer):
    """Point d'extension si l'entraînement Recommendation nécessite un jour un échantillonnage négatif dédié."""
