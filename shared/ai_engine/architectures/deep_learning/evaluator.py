"""Évaluation des candidats Deep Learning : délègue au service d'évaluation partagé."""

from shared.ai_engine.core.evaluator import Evaluator


class DeepLearningEvaluator(Evaluator):
    """Point d'extension pour des métriques DL dédiées (ex : val_loss, val_accuracy)."""
