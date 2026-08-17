"""Évaluation des candidats OCR : délègue au service d'évaluation partagé."""

from shared.ai_engine.core.evaluator import Evaluator


class OCREvaluator(Evaluator):
    """Point d'extension pour des métriques OCR dédiées (ex : character error rate)."""
