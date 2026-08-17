"""Candidat PaddleOCR (sera implémenté avec la bibliothèque paddleocr)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class PaddleOCRModel(UntrainedModel):
    candidate_id = "paddle_ocr"
