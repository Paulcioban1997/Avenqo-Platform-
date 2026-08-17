"""Catalogue OCR : architectures de reconnaissance de texte, réutilisées par la famille OCR
(unique source de vérité).
"""

from shared.ai_engine.architectures.ocr.easy_ocr import EasyOCRModel
from shared.ai_engine.architectures.ocr.paddle_ocr import PaddleOCRModel
from shared.ai_engine.architectures.ocr.tesseract_ocr import TesseractOCRModel
from shared.ai_engine.architectures.ocr.trocr import TrOCRModel

__all__ = ["TrOCRModel", "TesseractOCRModel", "PaddleOCRModel", "EasyOCRModel"]
