"""Catalogue des modèles OCR : entièrement réutilisé depuis `architectures/ocr`,
unique source de vérité (aucun modèle propre à cette famille).
"""

from shared.ai_engine.architectures.ocr.easy_ocr import EasyOCRModel
from shared.ai_engine.architectures.ocr.paddle_ocr import PaddleOCRModel
from shared.ai_engine.architectures.ocr.tesseract_ocr import TesseractOCRModel
from shared.ai_engine.architectures.ocr.trocr import TrOCRModel
from shared.ai_engine.core.model_candidate_registry import ModelCandidateRegistry


def build_ocr_registry() -> ModelCandidateRegistry:
    registry = ModelCandidateRegistry()
    registry.register("tesseract_ocr", TesseractOCRModel)
    registry.register("trocr", TrOCRModel)
    registry.register("paddle_ocr", PaddleOCRModel)
    registry.register("easy_ocr", EasyOCRModel)
    return registry
