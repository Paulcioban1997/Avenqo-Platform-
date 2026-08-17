"""Candidat Tesseract (sera implémenté avec pytesseract)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class TesseractOCRModel(UntrainedModel):
    candidate_id = "tesseract_ocr"
