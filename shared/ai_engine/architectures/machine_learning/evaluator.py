"""Évaluation des candidats Machine Learning : délègue au service d'évaluation partagé."""

from shared.ai_engine.core.evaluator import Evaluator


class MachineLearningEvaluator(Evaluator):
    """Point d'extension pour des métriques ML dédiées (ex : accuracy, F1)."""
