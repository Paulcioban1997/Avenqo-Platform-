"""Stratégie d'exécution OCR : branche le catalogue OCR sur l'algorithme générique."""

from shared.ai_engine.core.execution_domain import ExecutionDomain
from shared.ai_engine.core.generic_strategy import TrainEvaluateSelectStrategy
from shared.ai_engine.core.optimizer import HyperparameterOptimizer
from shared.ai_engine.evaluation.service import EvaluationService
from shared.ai_engine.families.ocr.evaluator import OCREvaluator
from shared.ai_engine.families.ocr.optimizer import OCRHyperparameterOptimizer
from shared.ai_engine.families.ocr.registry import build_ocr_registry
from shared.ai_engine.families.ocr.trainer import OCRTrainer
from shared.ai_engine.model_selection.service import ModelSelector


class OCRStrategy(TrainEvaluateSelectStrategy):
    """Entraîne, évalue et sélectionne le meilleur candidat OCR."""

    def __init__(
        self,
        evaluator: EvaluationService,
        selector: ModelSelector | None = None,
        optimizer: HyperparameterOptimizer | None = None,
    ) -> None:
        super().__init__(
            domain=ExecutionDomain.OCR,
            candidate_registry=build_ocr_registry(),
            evaluator=OCREvaluator(evaluator),
            trainer=OCRTrainer(),
            optimizer=optimizer or OCRHyperparameterOptimizer(),
            selector=selector,
        )
