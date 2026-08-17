"""Entraînement des candidats OCR : identique à toutes les familles."""

from shared.ai_engine.core.trainer import Trainer


class OCRTrainer(Trainer):
    """Point d'extension si l'entraînement OCR nécessite un jour un pipeline de prétraitement d'image dédié."""
