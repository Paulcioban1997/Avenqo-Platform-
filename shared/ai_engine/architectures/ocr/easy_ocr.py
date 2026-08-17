"""Candidat EasyOCR (sera implémenté avec la bibliothèque easyocr)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class EasyOCRModel(UntrainedModel):
    candidate_id = "easy_ocr"
