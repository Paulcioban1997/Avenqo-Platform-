"""Évaluation des candidats Synthetic Data : délègue au service d'évaluation partagé."""

from shared.ai_engine.core.evaluator import Evaluator


class SyntheticDataEvaluator(Evaluator):
    """Point d'extension pour des métriques Synthetic Data dédiées (ex : score de fidélité statistique)."""
